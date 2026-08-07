import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from app.github.service import GitIntegrationService


class FakeProject:
    def __init__(self, id, workspace_id):
        self.id = id
        self.workspace_id = workspace_id


class FakeWorkspaceMember:
    def __init__(self, is_owner=False):
        self.is_owner = is_owner


class FakeProjectMember:
    def __init__(self, role):
        self.role = role


class FakeGitIntegration:
    def __init__(self, id, project_id):
        self.id = id
        self.project_id = project_id
        self.github_app_installation_id = "12345"
        self.repo_full_name = "org/repo"
        self.default_branch = "main"
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


class FakeGitIntegrationUnitOfWork:
    def __init__(self):
        self.projects = AsyncMock()
        self.workspace_members = AsyncMock()
        self.project_members = AsyncMock()
        self.git_integrations = AsyncMock()
        self.webhook_events = AsyncMock()
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def commit(self):
        self.committed = True


class TestGithubService:
    @pytest.mark.asyncio
    async def test_get_install_url_forbidden(self):
        uow = FakeGitIntegrationUnitOfWork()
        service = GitIntegrationService(uow, redis=AsyncMock())

        project = FakeProject("project-1", "ws-1")
        uow.projects.get_by_id.return_value = project
        uow.workspace_members.get_by_workspace_and_user.return_value = None
        uow.project_members.get_by_project_and_user.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.get_install_url("project-1", "outsider")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_get_install_url_success(self):
        uow = FakeGitIntegrationUnitOfWork()
        redis_mock = AsyncMock()
        service = GitIntegrationService(uow, redis=redis_mock)

        project = FakeProject("project-1", "ws-1")
        uow.projects.get_by_id.return_value = project
        uow.workspace_members.get_by_workspace_and_user.return_value = FakeWorkspaceMember(is_owner=True)

        result = await service.get_install_url("project-1", "user-owner")
        assert result.install_url is not None
        assert redis_mock.setex.call_count == 1

    @pytest.mark.asyncio
    async def test_get_integration_success(self):
        uow = FakeGitIntegrationUnitOfWork()
        service = GitIntegrationService(uow, redis=AsyncMock())

        project = FakeProject("project-1", "ws-1")
        integration = FakeGitIntegration("int-1", "project-1")

        uow.projects.get_by_id.return_value = project
        uow.workspace_members.get_by_workspace_and_user.return_value = FakeWorkspaceMember(is_owner=True)
        uow.git_integrations.get_by_project_id.return_value = integration

        result = await service.get_integration("project-1", "user-owner")
        assert result.repo_full_name == "org/repo"

    @pytest.mark.asyncio
    async def test_delete_integration_success(self):
        uow = FakeGitIntegrationUnitOfWork()
        service = GitIntegrationService(uow, redis=AsyncMock())

        project = FakeProject("project-1", "ws-1")
        integration = FakeGitIntegration("int-1", "project-1")

        uow.projects.get_by_id.return_value = project
        uow.workspace_members.get_by_workspace_and_user.return_value = FakeWorkspaceMember(is_owner=True)
        uow.git_integrations.get_by_project_id.return_value = integration

        await service.delete_integration("project-1", "user-owner")
        uow.git_integrations.delete.assert_called_once_with(integration)
        assert uow.committed is True