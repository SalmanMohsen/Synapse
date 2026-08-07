import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from arq import Retry
from app.worker import generate_plan_job
from app.agent.validation import FileGroundingValidationError


@pytest.mark.asyncio
@patch("app.worker.get_connection")
async def test_generate_plan_job_retries_on_transient_db_setup_error(mock_get_connection):
    # Simulate DB connection drop during context load
    mock_get_connection.side_effect = Exception("Postgres connection timeout.")

    ctx = {
        "llm_client": AsyncMock(),
        "llm_model_name": "qwen-7b",
        "count_tokens_fn": lambda x: len(x),
        "redis": AsyncMock(),
        "job_try": 1  # First attempt
    }

    # Should bubble a transient backoff Retry command up to the arq runner
    with pytest.raises(Retry) as exc_info:
        await generate_plan_job(ctx, ticket_id="ticket-123", agent_run_id="run-123")
    
    assert exc_info.value.defer_score == 60000


@pytest.mark.asyncio
@patch("app.worker.get_connection")
async def test_generate_plan_job_escalates_on_terminal_technical_failure(mock_get_connection):
    mock_get_connection.side_effect = Exception("Database is permanently corrupted.")
    redis_mock = AsyncMock()

    ctx = {
        "llm_client": AsyncMock(),
        "llm_model_name": "qwen-7b",
        "count_tokens_fn": lambda x: len(x),
        "redis": redis_mock,
        "job_try": 3  # Last attempt exhausted
    }

    # Under maximum attempts, job does not retry. It executes fallback termination.
    await generate_plan_job(ctx, ticket_id="ticket-123", agent_run_id="run-123")
    
    # Should revert ticket status, mark run failed, post system message and notify users
    assert mock_get_connection.call_count > 0
    assert redis_mock.publish.call_count == 2


@pytest.mark.asyncio
@patch("app.worker.get_connection")
@patch("app.worker.run_planning_pipeline")
async def test_generate_plan_job_file_grounding_validation_failure_rollbacks(
    mock_pipeline, mock_get_connection
):
    # Mock planning pipeline raising grounding validation error
    mock_pipeline.side_effect = FileGroundingValidationError(
        "Attempted to modify missing_file.py which does not exist in code index.",
        step_number=2,
        file_path="missing_file.py"
    )

    # Establish mock connections
    conn_mock = AsyncMock()
    # Mocking rows returned by query sequences
    conn_mock.execute.side_effect = [
        MagicMock(mappings=MagicMock(return_value=MagicMock(first=lambda: {"id": "run-123", "status": "pending"}))), # agent run status check
        MagicMock(), # update run status to running
        MagicMock(mappings=MagicMock(return_value=MagicMock(first=lambda: {"id": "ticket-123", "channel_id": "chan-123", "title": "Test Title", "description": "desc"}))), # ticket details
        MagicMock(mappings=MagicMock(return_value=MagicMock(first=lambda: {"id": "chan-123", "project_id": "proj-123"}))), # channel details
        MagicMock(all=lambda: [("Message 1",)]), # thread messages
        MagicMock(mappings=MagicMock(return_value=MagicMock(first=lambda: {"specialty_file_id": "sf-1", "technology_file_id": "tf-1"}))), # assignments
        MagicMock(first=lambda: ("Specialty text",)), # specialty content
        MagicMock(first=lambda: ("Tech text",)), # tech content
        MagicMock(), # Revert Ticket to consensus_reached on fail block
        MagicMock(), # Revert AgentRun to failed on fail block
        MagicMock(), # insert fail system message card
    ]
    
    mock_get_connection.return_value.__aenter__.return_value = conn_mock

    redis_mock = AsyncMock()
    ctx = {
        "llm_client": AsyncMock(),
        "llm_model_name": "qwen-7b",
        "count_tokens_fn": lambda x: len(x),
        "redis": redis_mock,
        "job_try": 1
    }

    # When FileGroundingValidationError occurs, it immediately transitions states to failed
    # and posts warning cards, skipping any arq backoff retries.
    await generate_plan_job(ctx, ticket_id="ticket-123", agent_run_id="run-123")

    # Assert websocket event notifications were dispatched
    assert redis_mock.publish.call_count == 2