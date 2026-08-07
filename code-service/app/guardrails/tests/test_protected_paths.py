import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from app.guardrails.protected_paths import (
    ProtectedPathSubscriber,
    is_migration_path,
    is_protected_ci_path,
)
from app.guardrails.context import RunContext
from app.openhands.events import AgentEvent, AgentEventKind


def test_migration_and_ci_paths_matching():
    # Valid migrations
    assert is_migration_path("backend/migrations/versions/123a_migration.py") is True
    assert is_migration_path("alembic/versions/999b_migration.py") is True
    # Safe code non-match
    assert is_migration_path("src/utils/migration_helper.py") is False

    # Valid CI/CD files
    assert is_protected_ci_path(".github/workflows/deploy.yml") is True
    assert is_protected_ci_path(".gitlab-ci.yml") is True
    assert is_protected_ci_path("Jenkinsfile") is True
    # Safe matching
    assert is_protected_ci_path("docs/github_workflows.md") is False


@pytest.mark.asyncio
async def test_protected_path_subscriber_flags_step_for_human_review():
    main_loop = asyncio.get_running_loop()
    ctx = RunContext(
        agent_run_id="run-1",
        project_id="proj-1",
        ticket_id="ticket-1",
        channel_id="chan-1",
        repo_full_name="org/repo",
        branch="dev",
        main_loop=main_loop
    )
    ctx.current_step_record_id = "step-1"

    subscriber = ProtectedPathSubscriber(ctx)
    event = AgentEvent(
        kind=AgentEventKind.OBSERVATION,
        touched_paths=["src/main.py", ".github/workflows/ci.yml"]
    )

    with patch("app.guardrails.protected_paths.flag_requires_human_review", new_callable=AsyncMock) as mock_flag:
        subscriber.handle(event)
        
        # Let the event loop execute scheduled callbacks
        await asyncio.sleep(0.1)

        # Verify that flag_requires_human_review was executed thread-safely via main loop
        mock_flag.assert_called_once_with("step-1")