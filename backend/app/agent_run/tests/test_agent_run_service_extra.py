import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException
from app.agent_run.service import AgentRunService
from app.agent_run.models import AgentRunStatus


class FakeWorkspaceMember:
    def __init__(self, is_owner=False):
        self.is_owner = is_owner


class FakeProjectMember:
    def __init__(self, role):
        self.role = role


class FakeTicket:
    def __init__(self, id, channel_id):
        self.id = id
        self.channel_id = channel_id


class FakeChannel:
    def __init__(self, id, project_id):
        self.id = id
        self.project_id = project_id


class FakeProject:
    def __init__(self, id, workspace_id):
        self.id = id
        self.workspace_id = workspace_id


class FakeAgentRun:
    def __init__(self, id, ticket_id, status):
        self.id = id
        self.ticket_id = ticket_id
        self.status = status


class FakeAgentRunUnitOfWork:
    def __init__(self):
        self.agent_runs = AsyncMock()
        self.tickets = AsyncMock()
        self.channels = AsyncMock()
        self.projects = AsyncMock()
        self.workspace_members = AsyncMock()
        self.project_members = AsyncMock()
        self.users = AsyncMock()
        self.messages = AsyncMock()
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def commit(self):
        self.committed = True


class TestAgentRunServiceExtra:
    @pytest.mark.asyncio
    async def test_get_run_success(self):
        uow = FakeAgentRunUnitOfWork()
        service = AgentRunService(uow, redis=AsyncMock())

        run = FakeAgentRun("run-1", "ticket-1", AgentRunStatus.awaiting_review)
        ticket = FakeTicket("ticket-1", "channel-1")
        channel = FakeChannel("channel-1", "project-1")
        project = FakeProject("project-1", "ws-1")

        uow.agent_runs.get_by_id.return_value = run
        uow.tickets.get_by_id.return_value = ticket
        uow.channels.get_by_id.return_value = channel
        uow.projects.get_by_id.return_value = project
        uow.workspace_members.get_by_workspace_and_user.return_value = FakeWorkspaceMember(is_owner=True)

        result = await service.get_run("run-1", "user-owner")
        assert result is run

    @pytest.mark.asyncio
    async def test_get_run_forbidden(self):
        uow = FakeAgentRunUnitOfWork()
        service = AgentRunService(uow, redis=AsyncMock())

        run = FakeAgentRun("run-1", "ticket-1", AgentRunStatus.awaiting_review)
        ticket = FakeTicket("ticket-1", "channel-1")
        channel = FakeChannel("channel-1", "project-1")
        project = FakeProject("project-1", "ws-1")

        uow.agent_runs.get_by_id.return_value = run
        uow.tickets.get_by_id.return_value = ticket
        uow.channels.get_by_id.return_value = channel
        uow.projects.get_by_id.return_value = project
        uow.workspace_members.get_by_workspace_and_user.return_value = None
        uow.project_members.get_by_project_and_user.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.get_run("run-1", "outsider")
        assert exc_info.value.status_code == 403