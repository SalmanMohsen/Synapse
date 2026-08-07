import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.auth.dependencies import get_current_user
from app.project.dependencies import get_project_service
from app.project.schemas import ProjectRead, ProjectMemberRead
from app.project.models import ProjectRole


def _fake_project_read(**overrides):
    return {
        "id": overrides.get("id", "project-1"),
        "workspace_id": overrides.get("workspace_id", "ws-1"),
        "name": overrides.get("name", "Project 1"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _fake_project_member_read(**overrides):
    return {
        "id": overrides.get("id", "member-1"),
        "project_id": overrides.get("project_id", "project-1"),
        "user_id": overrides.get("user_id", "user-1"),
        "role": overrides.get("role", ProjectRole.member),
        "joined_at": datetime.now(timezone.utc).isoformat(),
    }


class TestProjectRouter:
    @pytest.fixture(autouse=True)
    def setup_overrides(self):
        self.mock_service = AsyncMock()
        self.mock_user = MagicMock()
        self.mock_user.id = "user-1"

        app.dependency_overrides[get_project_service] = lambda: self.mock_service
        app.dependency_overrides[get_current_user] = lambda: self.mock_user
        yield
        app.dependency_overrides.clear()

    def test_create_project(self):
        client = TestClient(app)
        fake_res = ProjectRead(**_fake_project_read())
        self.mock_service.create_project.return_value = fake_res

        resp = client.post(
            "/api/v1/workspaces/ws-1/projects",
            json={"name": "Project 1"},
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Project 1"
        self.mock_service.create_project.assert_awaited_once()

    def test_list_projects(self):
        client = TestClient(app)
        fake_res = [ProjectRead(**_fake_project_read())]
        self.mock_service.list_projects.return_value = fake_res

        resp = client.get("/api/v1/workspaces/ws-1/projects")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        self.mock_service.list_projects.assert_awaited_once_with("ws-1", "user-1")

    def test_get_project(self):
        client = TestClient(app)
        fake_res = ProjectRead(**_fake_project_read())
        self.mock_service.get_project.return_value = fake_res

        resp = client.get("/api/v1/projects/project-1")
        assert resp.status_code == 200
        assert resp.json()["id"] == "project-1"
        self.mock_service.get_project.assert_awaited_once_with("project-1", "user-1")

    def test_update_project(self):
        client = TestClient(app)
        fake_res = ProjectRead(**_fake_project_read(name="New Name"))
        self.mock_service.update_project.return_value = fake_res

        resp = client.patch(
            "/api/v1/projects/project-1",
            json={"name": "New Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"
        self.mock_service.update_project.assert_awaited_once()

    def test_delete_project(self):
        client = TestClient(app)
        self.mock_service.delete_project.return_value = None

        resp = client.delete("/api/v1/projects/project-1")
        assert resp.status_code == 204
        self.mock_service.delete_project.assert_awaited_once_with("project-1", "user-1")

    def test_list_members(self):
        client = TestClient(app)
        fake_res = [ProjectMemberRead(**_fake_project_member_read())]
        self.mock_service.list_members.return_value = fake_res

        resp = client.get("/api/v1/projects/project-1/members")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        self.mock_service.list_members.assert_awaited_once_with("project-1", "user-1")

    def test_add_member(self):
        client = TestClient(app)
        fake_res = ProjectMemberRead(**_fake_project_member_read(user_id="user-2"))
        self.mock_service.add_member.return_value = fake_res

        resp = client.post(
            "/api/v1/projects/project-1/members",
            json={"user_id": "user-2", "role": "member"},
        )
        assert resp.status_code == 201
        assert resp.json()["user_id"] == "user-2"
        self.mock_service.add_member.assert_awaited_once()

    def test_update_member_role(self):
        client = TestClient(app)
        fake_res = ProjectMemberRead(**_fake_project_member_read(user_id="user-2", role=ProjectRole.team_lead))
        self.mock_service.update_member_role.return_value = fake_res

        resp = client.patch(
            "/api/v1/projects/project-1/members/user-2",
            json={"role": "team_lead"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "team_lead"
        self.mock_service.update_member_role.assert_awaited_once()

    def test_remove_member(self):
        client = TestClient(app)
        self.mock_service.remove_member.return_value = None

        resp = client.delete("/api/v1/projects/project-1/members/user-2")
        assert resp.status_code == 204
        self.mock_service.remove_member.assert_awaited_once_with("project-1", "user-1", "user-2")