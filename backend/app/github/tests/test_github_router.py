import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.auth.dependencies import get_current_user
from app.github.dependencies import get_git_integration_service
from app.github.schemas import GitIntegrationRead, GitInstallUrlResponse


def _fake_integration_read(**overrides):
    return {
        "id": overrides.get("id", "int-1"),
        "project_id": overrides.get("project_id", "project-1"),
        "github_app_installation_id": overrides.get("github_app_installation_id", "12345"),
        "repo_full_name": overrides.get("repo_full_name", "org/repo"),
        "default_branch": overrides.get("default_branch", "main"),
        "created_at": "2026-08-07T12:00:00Z",
        "updated_at": "2026-08-07T12:00:00Z",
    }


class TestGithubRouter:
    @pytest.fixture(autouse=True)
    def setup_overrides(self):
        self.mock_service = AsyncMock()
        self.mock_user = MagicMock()
        self.mock_user.id = "user-1"

        app.dependency_overrides[get_git_integration_service] = lambda: self.mock_service
        app.dependency_overrides[get_current_user] = lambda: self.mock_user
        yield
        app.dependency_overrides.clear()

    def test_initiate_github_app_install(self):
        client = TestClient(app)
        self.mock_service.get_install_url.return_value = GitInstallUrlResponse(install_url="https://github.com/install")

        resp = client.get("/api/v1/projects/project-1/github/install")
        assert resp.status_code == 200
        assert resp.json()["install_url"] == "https://github.com/install"
        assert "pending_github_project_id" in resp.cookies
        self.mock_service.get_install_url.assert_awaited_once_with("project-1", "user-1")

    def test_github_app_callback(self):
        client = TestClient(app)
        self.mock_service.handle_callback.return_value = None

        resp = client.get("/api/v1/github/app/callback?installation_id=12345&state=state_tok")
        assert resp.status_code == 200
        assert "github_install_success" in resp.text
        self.mock_service.handle_callback.assert_awaited_once_with("12345", "state_tok", None)

    def test_get_github_integration(self):
        client = TestClient(app)
        fake_res = GitIntegrationRead(**_fake_integration_read())
        self.mock_service.get_integration.return_value = fake_res

        resp = client.get("/api/v1/projects/project-1/github")
        assert resp.status_code == 200
        assert resp.json()["repo_full_name"] == "org/repo"
        self.mock_service.get_integration.assert_awaited_once_with("project-1", "user-1")

    def test_delete_github_integration(self):
        client = TestClient(app)
        self.mock_service.delete_integration.return_value = None

        resp = client.delete("/api/v1/projects/project-1/github")
        assert resp.status_code == 204
        self.mock_service.delete_integration.assert_awaited_once_with("project-1", "user-1")

    def test_handle_github_webhook(self):
        client = TestClient(app)
        self.mock_service.handle_webhook.return_value = "delivery-123"

        resp = client.post(
            "/api/v1/webhooks/github",
            headers={"X-Hub-Signature-256": "sha256=xxx", "X-GitHub-Delivery": "delivery-123"},
            json={"action": "opened"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        self.mock_service.handle_webhook.assert_awaited_once()