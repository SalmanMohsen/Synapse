import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.auth.dependencies import get_current_user
from app.workspace.dependencies import get_workspace_service
from app.workspace.schemas import WorkspaceRead, WorkspaceMemberRead
from app.workspace.models import ProjectCreationPolicy


def _fake_workspace_read(**overrides):
    return {
        "id": overrides.get("id", "ws-1"),
        "name": overrides.get("name", "Workspace 1"),
        "project_creation_policy": overrides.get("project_creation_policy", ProjectCreationPolicy.restricted),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _fake_workspace_member_read(**overrides):
    return {
        "id": overrides.get("id", "member-1"),
        "workspace_id": overrides.get("workspace_id", "ws-1"),
        "user_id": overrides.get("user_id", "user-1"),
        "is_owner": overrides.get("is_owner", False),
        "joined_at": datetime.now(timezone.utc).isoformat(),
    }


class TestWorkspaceRouter:
    @pytest.fixture(autouse=True)
    def setup_overrides(self):
        self.mock_service = AsyncMock()
        self.mock_user = MagicMock()
        self.mock_user.id = "user-1"

        app.dependency_overrides[get_workspace_service] = lambda: self.mock_service
        app.dependency_overrides[get_current_user] = lambda: self.mock_user
        yield
        app.dependency_overrides.clear()

    def test_create_workspace(self):
        client = TestClient(app)
        fake_res = WorkspaceRead(**_fake_workspace_read())
        self.mock_service.create_workspace.return_value = fake_res

        resp = client.post("/api/v1/workspaces", json={"name": "Workspace 1"})
        assert resp.status_code == 201
        assert resp.json()["name"] == "Workspace 1"
        self.mock_service.create_workspace.assert_awaited_once()

    def test_get_workspace(self):
        client = TestClient(app)
        fake_res = WorkspaceRead(**_fake_workspace_read())
        self.mock_service.get_workspace.return_value = fake_res

        resp = client.get("/api/v1/workspaces/ws-1")
        assert resp.status_code == 200
        assert resp.json()["id"] == "ws-1"
        self.mock_service.get_workspace.assert_awaited_once_with("ws-1", "user-1")

    def test_update_workspace(self):
        client = TestClient(app)
        fake_res = WorkspaceRead(**_fake_workspace_read(name="New Name"))
        self.mock_service.update_workspace.return_value = fake_res

        resp = client.patch(
            "/api/v1/workspaces/ws-1",
            json={"name": "New Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"
        self.mock_service.update_workspace.assert_awaited_once()

    def test_list_workspaces(self):
        client = TestClient(app)
        fake_res = [WorkspaceRead(**_fake_workspace_read())]
        self.mock_service.list_workspaces.return_value = fake_res

        resp = client.get("/api/v1/workspaces")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        self.mock_service.list_workspaces.assert_awaited_once_with("user-1")

    def test_delete_workspace(self):
        client = TestClient(app)
        self.mock_service.delete_workspace.return_value = None

        resp = client.delete("/api/v1/workspaces/ws-1")
        assert resp.status_code == 204
        self.mock_service.delete_workspace.assert_awaited_once_with("ws-1", "user-1")

    def test_list_members(self):
        client = TestClient(app)
        fake_res = [WorkspaceMemberRead(**_fake_workspace_member_read())]
        self.mock_service.list_members.return_value = fake_res

        resp = client.get("/api/v1/workspaces/ws-1/members")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        self.mock_service.list_members.assert_awaited_once_with("ws-1", "user-1")

    def test_add_owner(self):
        client = TestClient(app)
        fake_res = WorkspaceMemberRead(**_fake_workspace_member_read(user_id="user-2", is_owner=True))
        self.mock_service.add_owner.return_value = fake_res

        resp = client.post("/api/v1/workspaces/ws-1/members/user-2/promote")
        assert resp.status_code == 200
        assert resp.json()["is_owner"] is True
        self.mock_service.add_owner.assert_awaited_once_with("ws-1", "user-2", "user-1")

    def test_remove_member(self):
        client = TestClient(app)
        self.mock_service.remove_member.return_value = None

        resp = client.delete("/api/v1/workspaces/ws-1/members/user-2")
        assert resp.status_code == 204
        self.mock_service.remove_member.assert_awaited_once_with("ws-1", "user-2", "user-1")