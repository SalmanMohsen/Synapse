import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from app.message.service import MessageService
from app.message.models import Message, MessageType
from app.ticket.models import Ticket, TicketStatus
from app.channel.models import Channel, ChannelMember, ChannelMemberRole
from app.project.models import Project, ProjectMember, ProjectRole
from app.workspace.models import WorkspaceMember
from app.auth.models import User
from app.message.schemas import MessageCreate, MessageUpdate


class FakeUser:
    def __init__(self, id, display_name, avatar_url=None):
        self.id = id
        self.display_name = display_name
        self.avatar_url = avatar_url


class FakeWorkspaceMember:
    def __init__(self, workspace_id, user_id, is_owner=False):
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.is_owner = is_owner


class FakeProject:
    def __init__(self, id, workspace_id):
        self.id = id
        self.workspace_id = workspace_id


class FakeProjectMember:
    def __init__(self, project_id, user_id, role):
        self.project_id = project_id
        self.user_id = user_id
        self.role = role


class FakeChannel:
    def __init__(self, id, project_id, is_leads_channel=False, name="General"):
        self.id = id
        self.project_id = project_id
        self.is_leads_channel = is_leads_channel
        self.name = name


class FakeChannelMember:
    def __init__(self, channel_id, user_id, role):
        self.channel_id = channel_id
        self.user_id = user_id
        self.role = role


class FakeTicket:
    def __init__(self, id, channel_id, status):
        self.id = id
        self.channel_id = channel_id
        self.status = status


class FakeMessage:
    def __init__(self, id, ticket_id, author_id, content, type=MessageType.human, deleted_at=None, edited_at=None):
        self.id = id
        self.ticket_id = ticket_id
        self.author_id = author_id
        self.content = content
        self.type = type
        self.deleted_at = deleted_at
        self.edited_at = edited_at
        self.metadata_json = None
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


class FakeMessageRepository:
    def __init__(self):
        self.messages = {}
        self.users = {}

    async def create(self, **kwargs):
        m_id = str(uuid.uuid4())
        msg = FakeMessage(
            id=m_id,
            ticket_id=kwargs["ticket_id"],
            author_id=kwargs.get("author_id"),
            content=kwargs["content"],
            type=kwargs.get("type", MessageType.human)
        )
        self.messages[m_id] = msg
        return msg

    async def get_by_id_with_author(self, message_id):
        msg = self.messages.get(message_id)
        if not msg:
            return None
        author = self.users.get(msg.author_id) if msg.author_id else None
        return (msg, author)

    async def list_by_ticket_paginated_with_authors(self, ticket_id, before_id=None, limit=50):
        ticket_msgs = [m for m in self.messages.values() if m.ticket_id == ticket_id]
        ticket_msgs.sort(key=lambda x: x.created_at, reverse=True)
        if before_id:
            anchor = next((i for i, m in enumerate(ticket_msgs) if m.id == before_id), None)
            if anchor is not None:
                ticket_msgs = ticket_msgs[anchor + 1:]

        has_more = len(ticket_msgs) > limit
        page = ticket_msgs[:limit]
        page.reverse()

        rows = []
        for m in page:
            u = self.users.get(m.author_id) if m.author_id else None
            rows.append((m, u))
        return rows, has_more

    async def update(self, message, **kwargs):
        for k, v in kwargs.items():
            setattr(message, k, v)
        return message


class FakeTicketRepository:
    def __init__(self):
        self.tickets = {}

    async def get_by_id(self, ticket_id):
        return self.tickets.get(ticket_id)

    async def update(self, ticket, **kwargs):
        for k, v in kwargs.items():
            setattr(ticket, k, v)
        return ticket


class FakeChannelRepository:
    def __init__(self):
        self.channels = {}

    async def get_by_id(self, channel_id):
        return self.channels.get(channel_id)


class FakeChannelMemberRepository:
    def __init__(self):
        self.members = {}

    async def get_by_channel_and_user(self, channel_id, user_id):
        return self.members.get((channel_id, user_id))

    async def is_channel_lead(self, channel_id, user_id):
        member = self.members.get((channel_id, user_id))
        return member is not None and member.role == ChannelMemberRole.channel_lead


class FakeProjectRepository:
    def __init__(self):
        self.projects = {}

    async def get_by_id(self, project_id):
        return self.projects.get(project_id)


class FakeProjectMemberRepository:
    def __init__(self):
        self.members = {}

    async def get_by_project_and_user(self, project_id, user_id):
        return self.members.get((project_id, user_id))


class FakeWorkspaceMemberRepository:
    def __init__(self):
        self.members = {}

    async def get_by_workspace_and_user(self, workspace_id, user_id):
        return self.members.get((workspace_id, user_id))


class FakeUserRepository:
    def __init__(self):
        self.users = {}

    async def get_by_id(self, user_id):
        return self.users.get(user_id)


class FakeMessageUnitOfWork:
    def __init__(self):
        self.messages = FakeMessageRepository()
        self.tickets = FakeTicketRepository()
        self.channels = FakeChannelRepository()
        self.channel_members = FakeChannelMemberRepository()
        self.projects = FakeProjectRepository()
        self.project_members = FakeProjectMemberRepository()
        self.workspace_members = FakeWorkspaceMemberRepository()
        self.users = FakeUserRepository()
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rolled_back = True

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


@pytest.fixture
def message_uow():
    return FakeMessageUnitOfWork()


@pytest.fixture
def message_service(message_uow):
    return MessageService(uow=message_uow, redis=AsyncMock())


@pytest.mark.asyncio
async def test_create_message_happy_path(message_service, message_uow):
    # Setup context
    message_uow.tickets.tickets["t-1"] = FakeTicket("t-1", "ch-1", TicketStatus.active)
    message_uow.channels.channels["ch-1"] = FakeChannel("ch-1", "p-1")
    message_uow.projects.projects["p-1"] = FakeProject("p-1", "ws-1")
    message_uow.project_members.members[("p-1", "u-1")] = FakeProjectMember("p-1", "u-1", ProjectRole.member)
    message_uow.channel_members.members[("ch-1", "u-1")] = FakeChannelMember("ch-1", "u-1", ChannelMemberRole.member)
    message_uow.users.users["u-1"] = FakeUser("u-1", "User One")

    data = MessageCreate(content="Hello World")
    result = await message_service.create_message("t-1", "u-1", data)

    assert result.content == "Hello World"
    assert message_uow.committed is True
    # Verify auto-transition was fired
    assert message_uow.tickets.tickets["t-1"].status == TicketStatus.in_discussion


@pytest.mark.asyncio
async def test_create_message_viewer_blocked(message_service, message_uow):
    message_uow.tickets.tickets["t-1"] = FakeTicket("t-1", "ch-1", TicketStatus.active)
    message_uow.channels.channels["ch-1"] = FakeChannel("ch-1", "p-1")
    message_uow.projects.projects["p-1"] = FakeProject("p-1", "ws-1")
    message_uow.project_members.members[("p-1", "u-1")] = FakeProjectMember("p-1", "u-1", ProjectRole.viewer)
    message_uow.channel_members.members[("ch-1", "u-1")] = FakeChannelMember("ch-1", "u-1", ChannelMemberRole.member)

    data = MessageCreate(content="Illegal Post")
    with pytest.raises(HTTPException) as exc_info:
        await message_service.create_message("t-1", "u-1", data)

    assert exc_info.value.status_code == 403
    assert "Viewers cannot post" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_message_locked_on_unactivated_discipline_ticket(message_service, message_uow):
    # Backlog status represents an unactivated state
    message_uow.tickets.tickets["t-1"] = FakeTicket("t-1", "ch-1", TicketStatus.backlog)
    message_uow.channels.channels["ch-1"] = FakeChannel("ch-1", "p-1", is_leads_channel=False)
    message_uow.projects.projects["p-1"] = FakeProject("p-1", "ws-1")
    message_uow.project_members.members[("p-1", "u-1")] = FakeProjectMember("p-1", "u-1", ProjectRole.member)
    message_uow.channel_members.members[("ch-1", "u-1")] = FakeChannelMember("ch-1", "u-1", ChannelMemberRole.member)

    data = MessageCreate(content="Blocked")
    with pytest.raises(HTTPException) as exc_info:
        await message_service.create_message("t-1", "u-1", data)

    assert exc_info.value.status_code == 400
    assert "thread is locked" in exc_info.value.detail


@pytest.mark.asyncio
async def test_edit_message_unauthorized(message_service, message_uow):
    message_uow.tickets.tickets["t-1"] = FakeTicket("t-1", "ch-1", TicketStatus.active)
    message_uow.channels.channels["ch-1"] = FakeChannel("ch-1", "p-1")
    message_uow.projects.projects["p-1"] = FakeProject("p-1", "ws-1")
    message_uow.project_members.members[("p-1", "u-1")] = FakeProjectMember("p-1", "u-1", ProjectRole.member)
    message_uow.channel_members.members[("ch-1", "u-1")] = FakeChannelMember("ch-1", "u-1", ChannelMemberRole.member)
    
    # Message owned by u-2
    msg = FakeMessage("m-1", "t-1", "u-2", "Original Text")
    message_uow.messages.messages["m-1"] = msg

    data = MessageUpdate(content="Attempted Hack")
    with pytest.raises(HTTPException) as exc_info:
        await message_service.edit_message("t-1", "m-1", "u-1", data)

    assert exc_info.value.status_code == 403
    assert "Only the message author can edit" in exc_info.value.detail


@pytest.mark.asyncio
async def test_delete_message_role_based_permissions(message_service, message_uow):
    message_uow.tickets.tickets["t-1"] = FakeTicket("t-1", "ch-1", TicketStatus.active)
    message_uow.channels.channels["ch-1"] = FakeChannel("ch-1", "p-1")
    message_uow.projects.projects["p-1"] = FakeProject("p-1", "ws-1")
    message_uow.project_members.members[("p-1", "u-lead")] = FakeProjectMember("p-1", "u-lead", ProjectRole.member)
    message_uow.channel_members.members[("ch-1", "u-lead")] = FakeChannelMember("ch-1", "u-lead", ChannelMemberRole.channel_lead)
    
    msg = FakeMessage("m-1", "t-1", "u-author", "Delete me")
    message_uow.messages.messages["m-1"] = msg

    # Channel lead u-lead should be permitted to delete u-author's message
    result = await message_service.delete_message("t-1", "m-1", "u-lead")
    assert result.deleted_at is not None
    assert message_uow.committed is True