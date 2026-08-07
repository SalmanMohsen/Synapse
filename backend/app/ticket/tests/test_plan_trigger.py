import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from app.ticket.service import TicketService
from app.ticket.models import TicketStatus
from app.agent_run.models import AgentRunStatus
from datetime import datetime, timezone


class FakeTicket:
    def __init__(self, **kwargs):
        # Set default values for all fields expected by TicketRead
        self.id = kwargs.get("id", "ticket-123")
        self.channel_id = kwargs.get("channel_id", "channel-123")
        self.status = kwargs.get("status", "in_discussion")
        self.title = kwargs.get("title", "Test Ticket Title")
        self.description = kwargs.get("description", "Test Description")
        self.source = kwargs.get("source", "synapse")
        self.priority = kwargs.get("priority", "medium")
        self.creator_id = kwargs.get("creator_id", None)
        self.github_issue_number = kwargs.get("github_issue_number", None)
        self.github_author_login = kwargs.get("github_author_login", None)
        self.github_pr_number = kwargs.get("github_pr_number", None)
        self.parent_ticket_id = kwargs.get("parent_ticket_id", None)
        self.created_at = kwargs.get("created_at", datetime.now(timezone.utc))
        self.updated_at = kwargs.get("updated_at", datetime.now(timezone.utc))
        
        # Override or set any explicitly passed parameters
        for k, v in kwargs.items():
            setattr(self, k, v)

class FakeChannel:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class FakeProject:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class FakeWorkspaceMember:
    def __init__(self, is_owner=False):
        self.is_owner = is_owner

class FakeProjectMember:
    def __init__(self, role):
        self.role = role

class FakeSkillAssignment:
    def __init__(self, specialty_file_id=None, technology_file_id=None):
        self.specialty_file_id = specialty_file_id
        self.technology_file_id = technology_file_id

class FakeAgentRun:
    def __init__(self, id, status):
        self.id = id
        self.status = status

class FakeTicketRepository:
    def __init__(self):
        self.tickets = {}

    async def get_by_id(self, ticket_id: str):
        return self.tickets.get(ticket_id)

    async def update(self, ticket, **kwargs):
        for k, v in kwargs.items():
            setattr(ticket, k, v)
        return ticket

class FakeChannelRepository:
    def __init__(self):
        self.channels = {}

    async def get_by_id(self, channel_id: str):
        return self.channels.get(channel_id)

class FakeProjectRepository:
    def __init__(self):
        self.projects = {}

    async def get_by_id(self, project_id: str):
        return self.projects.get(project_id)

class FakeWorkspaceMemberRepository:
    def __init__(self):
        self.members = {}

    async def get_by_workspace_and_user(self, workspace_id, user_id):
        return self.members.get((workspace_id, user_id))

class FakeProjectMemberRepository:
    def __init__(self):
        self.members = {}

    async def get_by_project_and_user(self, project_id, user_id):
        return self.members.get((project_id, user_id))

class FakeChannelMemberRepository:
    def __init__(self):
        self.leads = {}

    async def is_channel_lead(self, channel_id, user_id):
        return self.leads.get((channel_id, user_id), False)

class FakeAgentRunRepository:
    def __init__(self):
        self.active_runs = {}
        self.raise_integrity_error = False

    async def get_active_by_ticket(self, ticket_id: str):
        return self.active_runs.get(ticket_id)

    async def create(self, ticket_id, status):
        if self.raise_integrity_error:
            raise IntegrityError(statement=None, params=None, orig=Exception("Unique constraint violation"))
        run = FakeAgentRun(id="run-123", status=status)
        self.active_runs[ticket_id] = run
        return run

class FakeSkillRepository:
    def __init__(self):
        self.assignments = {}

    async def get_assignment_by_channel(self, channel_id: str):
        return self.assignments.get(channel_id)
    
class FakeMessage:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "msg-123")
        self.ticket_id = kwargs.get("ticket_id", "ticket-123")
        self.author_id = kwargs.get("author_id", None)
        self.author = kwargs.get("author", None)
        self.content = kwargs.get("content", "system plan generation message")
        self.type = kwargs.get("type", "system")
        self.metadata_json = kwargs.get("metadata_json", {})
        self.deleted_at = kwargs.get("deleted_at", None)
        self.edited_at = kwargs.get("edited_at", None)
        self.created_at = kwargs.get("created_at", datetime.now(timezone.utc))
        self.updated_at = kwargs.get("updated_at", datetime.now(timezone.utc))

class FakeMessageRepository:
    async def create(self, **kwargs):
        # Passes any arguments cleanly to our standard Python object
        return FakeMessage(**kwargs)

class FakeUserRepository:
    async def get_by_id(self, user_id: str):
        user = MagicMock()
        user.display_name = "Jane Doe"
        return user

class FakeTicketUnitOfWork:
    def __init__(self):
        self.tickets = FakeTicketRepository()
        self.channels = FakeChannelRepository()
        self.projects = FakeProjectRepository()
        self.workspace_members = FakeWorkspaceMemberRepository()
        self.project_members = FakeProjectMemberRepository()
        self.channel_members = FakeChannelMemberRepository()
        self.agent_runs = FakeAgentRunRepository()
        self.skills = FakeSkillRepository()
        self.messages = FakeMessageRepository()
        self.users = FakeUserRepository()
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def commit(self):
        self.committed = True


#@pytest.mark.asyncio
#@patch("app.ticket.service.get_arq_pool") 
#async def test_generate_plan_missing_skills(mock_get_arq_pool):
#    mock_pool = AsyncMock()
#    mock_get_arq_pool.return_value = mock_pool
#
#    uow = FakeTicketUnitOfWork()
#    service = TicketService(uow, redis=AsyncMock())
#
#    # Setup permissions and dependencies
#    uow.tickets.tickets["ticket-1"] = FakeTicket(id="ticket-1", channel_id="channel-1", status=TicketStatus.in_discussion)
#    uow.channels.channels["channel-1"] = FakeChannel(id="channel-1", project_id="project-1")
#    uow.projects.projects["project-1"] = FakeProject(id="project-1", workspace_id="ws-1")
#    uow.workspace_members.members[("ws-1", "user-lead")] = FakeWorkspaceMember(is_owner=True)
#
#    # Missing skill assignment in database completely
#    with pytest.raises(HTTPException) as exc_info:
#        await service.generate_plan("ticket-1", "user-lead")
#    assert exc_info.value.status_code == 400
#    assert "missing a skill assignment" in exc_info.value.detail


@pytest.mark.asyncio
async def test_generate_plan_concurrency_check():
    uow = FakeTicketUnitOfWork()
    service = TicketService(uow, redis=AsyncMock())

    uow.tickets.tickets["ticket-1"] = FakeTicket(id="ticket-1", channel_id="channel-1", status=TicketStatus.in_discussion)
    uow.channels.channels["channel-1"] = FakeChannel(id="channel-1", project_id="project-1")
    uow.projects.projects["project-1"] = FakeProject(id="project-1", workspace_id="ws-1")
    uow.workspace_members.members[("ws-1", "user-lead")] = FakeWorkspaceMember(is_owner=True)
    uow.skills.assignments["channel-1"] = FakeSkillAssignment(specialty_file_id="s-1", technology_file_id="t-1")

    # Simulate an active run exists
    uow.agent_runs.active_runs["ticket-1"] = FakeAgentRun(id="run-active", status=AgentRunStatus.running)

    with pytest.raises(HTTPException) as exc_info:
        await service.generate_plan("ticket-1", "user-lead")
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
@patch("app.ticket.service.get_arq_pool")
async def test_generate_plan_concurrency_race_condition_database_constraint(mock_get_arq_pool):
    uow = FakeTicketUnitOfWork()
    service = TicketService(uow, redis=AsyncMock())

    uow.tickets.tickets["ticket-1"] = FakeTicket(id="ticket-1", channel_id="channel-1", status=TicketStatus.in_discussion)
    uow.channels.channels["channel-1"] = FakeChannel(id="channel-1", project_id="project-1")
    uow.projects.projects["project-1"] = FakeProject(id="project-1", workspace_id="ws-1")
    uow.workspace_members.members[("ws-1", "user-lead")] = FakeWorkspaceMember(is_owner=True)
    uow.skills.assignments["channel-1"] = FakeSkillAssignment(specialty_file_id="s-1", technology_file_id="t-1")

    # Simulate database-level partial unique constraint race-condition on concurrent creation
    uow.agent_runs.raise_integrity_error = True

    with pytest.raises(HTTPException) as exc_info:
        await service.generate_plan("ticket-1", "user-lead")
    assert exc_info.value.status_code == 409
    assert "already being generated" in exc_info.value.detail


@pytest.mark.asyncio
@patch("app.ticket.service.get_arq_pool")
async def test_generate_plan_success_triggers_job(mock_get_arq_pool):
    mock_pool = AsyncMock()
    mock_get_arq_pool.return_value = mock_pool

    uow = FakeTicketUnitOfWork()
    redis_mock = AsyncMock()
    service = TicketService(uow, redis=redis_mock)

    ticket = FakeTicket(id="ticket-1", channel_id="channel-1", status=TicketStatus.in_discussion)
    uow.tickets.tickets["ticket-1"] = ticket
    uow.channels.channels["channel-1"] = FakeChannel(id="channel-1", project_id="project-1")
    uow.projects.projects["project-1"] = FakeProject(id="project-1", workspace_id="ws-1")
    uow.workspace_members.members[("ws-1", "user-lead")] = FakeWorkspaceMember(is_owner=True)
    uow.skills.assignments["channel-1"] = FakeSkillAssignment(specialty_file_id="s-1", technology_file_id="t-1")

    result = await service.generate_plan("ticket-1", "user-lead")

    assert ticket.status == TicketStatus.consensus_reached
    assert uow.committed is True
    mock_pool.enqueue_job.assert_called_once_with(
        "generate_plan", ticket_id="ticket-1", agent_run_id="run-123"
    )
    assert redis_mock.publish.call_count == 2