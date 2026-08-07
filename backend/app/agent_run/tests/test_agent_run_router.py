import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.auth.dependencies import get_current_user
from app.agent_run.dependencies import get_agent_run_service
from app.agent_run.schemas import AgentRunRead
from app.agent_run.models import AgentRunStatus


def _fake_agent_run_read(**overrides):
    return {
        "id": overrides.get("id", "run-1"),
        "ticket_id": overrides.get("ticket_id", "ticket-1"),
        "status": overrides.get("status", AgentRunStatus.awaiting_review),
        "plan_json": overrides.get("plan_json", {"steps": []}),
        "attempt_count": overrides.get("attempt_count", 0),
        "edited_by_user_id": overrides.get("edited_by_user_id", None),
        "edited_at": overrides.get("edited_at", None),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


class TestAgentRunRouter:
    @pytest.fixture(autouse=True)
    def setup_overrides(self):
        self.mock_service = AsyncMock()
        self.mock_user = MagicMock()
        self.mock_user.id = "user-1"

        app.dependency_overrides[get_agent_run_service] = lambda: self.mock_service
        app.dependency_overrides[get_current_user] = lambda: self.mock_user
        yield
        app.dependency_overrides.clear()

    def test_get_agent_run(self):
        client = TestClient(app)
        fake_res = AgentRunRead(**_fake_agent_run_read())
        self.mock_service.get_run.return_value = fake_res

        resp = client.get("/api/v1/agent-runs/run-1")
        assert resp.status_code == 200
        assert resp.json()["id"] == "run-1"
        self.mock_service.get_run.assert_awaited_once_with("run-1", "user-1")

    def test_approve_agent_run_plan(self):
        client = TestClient(app)
        self.mock_service.approve_plan.return_value = None

        resp = client.post("/api/v1/agent-runs/run-1/approve")
        assert resp.status_code == 204
        self.mock_service.approve_plan.assert_awaited_once_with("run-1", "user-1")

    def test_reject_agent_run_plan(self):
        client = TestClient(app)
        self.mock_service.reject_plan.return_value = None

        resp = client.post("/api/v1/agent-runs/run-1/reject")
        assert resp.status_code == 204
        self.mock_service.reject_plan.assert_awaited_once_with("run-1", "user-1")

    def test_edit_agent_run_plan(self):
        client = TestClient(app)
        fake_plan = {"steps": [{"step_number": 1, "description": "Modified task"}]}
        self.mock_service.edit_plan.return_value = fake_plan

        resp = client.patch(
            "/api/v1/agent-runs/run-1",
            json={"plan_json": fake_plan},
        )
        assert resp.status_code == 200
        assert resp.json()["steps"][0]["description"] == "Modified task"
        self.mock_service.edit_plan.assert_awaited_once_with("run-1", fake_plan, "user-1")