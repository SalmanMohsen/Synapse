import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.pipeline import run_planning_pipeline
from app.agent.planner import ScopeGateRejected
from app.agent.validation import FileGroundingValidationError


@pytest.mark.asyncio
@patch("app.pipeline.run_scope_gate", new_callable=AsyncMock)
@patch("app.pipeline.embed_query")
@patch("app.pipeline.retrieve_chunks", new_callable=AsyncMock)
@patch("app.pipeline.generate_development_plan", new_callable=AsyncMock)
@patch("app.pipeline.validate_development_plan_grounding", new_callable=AsyncMock)
@patch("app.pipeline.create_agent_run_step", new_callable=AsyncMock)
@patch("app.pipeline.complete_agent_run_step", new_callable=AsyncMock)
@patch("app.pipeline.fail_agent_run_step", new_callable=AsyncMock)
async def test_run_planning_pipeline_happy_path(
    mock_fail_step, mock_complete_step, mock_create_step,
    mock_validate_grounding, mock_generate_plan, mock_retrieve_chunks,
    mock_embed_query, mock_run_scope_gate
):
    # Setup mock returns
    mock_embed_query.return_value = [0.1] * 256
    mock_retrieve_chunks.return_value = [("app/auth.py", "def login(): pass")]
    
    mock_plan = MagicMock()
    mock_generate_plan.return_value = mock_plan
    mock_create_step.return_value = "step-id"

    client = AsyncMock()
    step_counter = [1]

    result = await run_planning_pipeline(
        client=client,
        model_name="qwen-coder",
        count_tokens_fn=lambda x: len(x),
        ticket_title="Auth Ticket",
        ticket_description="Create route",
        thread_messages=["Message 1"],
        specialty_skill="Format carefully",
        technology_skill="Use SQL",
        project_id="proj-1",
        agent_run_id="run-1",
        job_try=1,
        step_counter=step_counter
    )

    # 1. Verify Scope Gate executed first
    mock_run_scope_gate.assert_called_once_with(
        client=client,
        model_name="qwen-coder",
        ticket_title="Auth Ticket",
        ticket_description="Create route",
        thread_messages=["Message 1"],
        agent_run_id="run-1",
        job_try=1
    )

    # 2. Verify RAG retrieval was executed
    mock_embed_query.assert_called_once()
    mock_retrieve_chunks.assert_called_once_with("proj-1", mock_embed_query.return_value, limit=8)

    # 3. Verify Plan generation was executed
    mock_generate_plan.assert_called_once()

    # 4. Verify grounding validation was performed
    mock_validate_grounding.assert_called_once_with("proj-1", mock_plan)
    assert result == mock_plan


@pytest.mark.asyncio
@patch("app.pipeline.run_scope_gate", new_callable=AsyncMock)
async def test_run_planning_pipeline_scope_gate_rejection_bubbles_up(mock_run_scope_gate):
    # Simulate a scope gate rejection
    mock_run_scope_gate.side_effect = ScopeGateRejected("Not actionable")

    client = AsyncMock()
    step_counter = [1]

    # Rejections bubble up to the caller without running RAG or drafting
    with pytest.raises(ScopeGateRejected) as exc_info:
        await run_planning_pipeline(
            client=client,
            model_name="qwen-coder",
            count_tokens_fn=lambda x: len(x),
            ticket_title="Off-topic Ticket",
            ticket_description="Write a cake recipe",
            thread_messages=[],
            specialty_skill="",
            technology_skill="",
            project_id="proj-1",
            agent_run_id="run-1",
            job_try=1,
            step_counter=step_counter
        )
    assert exc_info.value.reason == "Not actionable"