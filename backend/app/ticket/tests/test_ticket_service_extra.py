import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException
from app.ticket.service import TicketService
from app.ticket.models import TicketStatus, TicketSource, TicketPriority


class FakeWorkspaceMember:
    def __init__(self, is_owner=False):
        self.is_owner = is_owner


class FakeProjectMember:
    def __init__(self, role):
        self.role = role


class FakeChannelMember:
    def __init__(self, role):
        self.role = role


class FakeTicket:
    def __init__(self, id, channel_id, status=TicketStatus.active):
        self.id = id
        self.channel_id = channel_id
        self.status = status
        self.title = "Test Ticket"
        self.description = "Desc"
        self.creator_id = "user-1"
        self.source = TicketSource.synapse
        self.priority = TicketPriority.medium
        self.parent_ticket_id = None
        self.github_issue_number = None
        self.github_author_login = None
        self.github_pr_number = None
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


class FakeChannel:
    def __init__(self, id, project_id, is_leads_channel=False, name="general"):
        self.id = id
        self.project_id = project_id
        self.is_leads_channel = is_leads_channel
        self.name = name


class FakeProject:
    def __init__(self, id, workspace_id):
        self.id = id
        self.workspace_id = workspace_id


class FakeMessage:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "msg-1")
        self.ticket_id = kwargs.get("ticket_id", "ticket-1")
        self.author_id = kwargs.get("author_id", None)
        self.content = kwargs.get("content", "system message")
        self.type = kwargs.get("type", "system")
        self.metadata_json = kwargs.get("metadata_json", {})
        self.deleted_at = kwargs.get("deleted_at", None)
        self.edited_at = kwargs.get("edited_at", None)
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


class FakeTicketUnitOfWork:
    def __init__(self):
        self.tickets = AsyncMock()
        self.channels = AsyncMock()
        self.projects = AsyncMock()
        self.workspace_members = AsyncMock()
        self.project_members = AsyncMock()
        self.channel_members = AsyncMock()
        self.messages = AsyncMock()
        self.messages.create = AsyncMock(side_effect=lambda **kwargs: FakeMessage(**kwargs))
        self.users = AsyncMock()
        self.thread_states = AsyncMock()
        self.inbox_items = AsyncMock()
        self.skills = AsyncMock()
        self.agent_runs = AsyncMock()
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def commit(self):
        self.committed = True


class TestTicketServiceExtra:
    @pytest.mark.asyncio
    async def test_activate_ticket_non_lead_forbidden(self):
        uow = FakeTicketUnitOfWork()
        service = TicketService(uow, redis=AsyncMock())

        ticket = FakeTicket("ticket-1", "channel-1", status=TicketStatus.routed)
        channel = FakeChannel("channel-1", "project-1")
        project = FakeProject("project-1", "ws-1")

        uow.tickets.get_by_id.return_value = ticket
        uow.channels.get_by_id.return_value = channel
        uow.projects.get_by_id.return_value = project
        uow.channel_members.is_channel_lead.return_value = False

        with pytest.raises(HTTPException) as exc_info:
            await service.activate_ticket("ticket-1", "user-member")
        assert exc_info.value.status_code == 403
        assert "Only the Channel Lead" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_activate_ticket_success(self):
        uow = FakeTicketUnitOfWork()
        service = TicketService(uow, redis=AsyncMock())

        ticket = FakeTicket("ticket-1", "channel-1", status=TicketStatus.routed)
        channel = FakeChannel("channel-1", "project-1")
        project = FakeProject("project-1", "ws-1")

        uow.tickets.get_by_id.return_value = ticket
        uow.channels.get_by_id.return_value = channel
        uow.projects.get_by_id.return_value = project
        uow.channel_members.is_channel_lead.return_value = True
        uow.tickets.update.return_value = ticket
        uow.users.get_by_id.return_value = MagicMock(display_name="Lead")

        result = await service.activate_ticket("ticket-1", "user-lead")
        assert result is not None
        assert uow.thread_states.create.call_count == 1
        assert uow.committed is True

    @pytest.mark.asyncio
    async def test_close_ticket_success(self):
        uow = FakeTicketUnitOfWork()
        service = TicketService(uow, redis=AsyncMock())

        ticket = FakeTicket("ticket-1", "channel-1", status=TicketStatus.active)
        channel = FakeChannel("channel-1", "project-1")
        project = FakeProject("project-1", "ws-1")

        uow.tickets.get_by_id.return_value = ticket
        uow.channels.get_by_id.return_value = channel
        uow.projects.get_by_id.return_value = project
        uow.workspace_members.get_by_workspace_and_user.return_value = FakeWorkspaceMember(is_owner=True)
        uow.tickets.update.return_value = ticket

        result = await service.close_ticket("ticket-1", "user-owner")
        assert result is not None
        assert uow.committed is True