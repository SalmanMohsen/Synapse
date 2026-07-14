import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException
from app.agent_run.service import AgentRunService
from app.agent_run.models import AgentRunStatus
from app.ticket.models import TicketStatus

class FakeWorkspaceMember:
    def __init__(self, is_owner=False):
        self.is_owner = is_owner

class FakeProjectMember:
    def __init__(self, role):
        self.role = role

class FakeUser:
    def __init__(self, display_name):
        self.display_name = display_name

class FakeTicket:
    def __init__(self, id, channel_id, status):
        self.id = id
        self.channel_id = channel_id
        self.status = status

class FakeChannel:
    def __init__(self, id, project_id):
        self.id = id
        self.project_id = project_id

class FakeProject:
    def __init__(self, id, workspace_id):
        self.id = id
        self.workspace_id = workspace_id

class FakeAgentRun:
    def __init__(self, id, ticket_id, status, plan_json=None):
        self.id = id
        self.ticket_id = ticket_id
        self.status = status
        self.plan_json = plan_json
        self.edited_by_user_id = None
        self.edited_at = None
        self.updated_at = None

class FakeAgentRunRepository:
    def __init__(self):
        self.runs = {}

    async def get_by_id(self, run_id: str):
        return self.runs.get(run_id)

    async def update(self, run, **fields):
        for k, v in fields.items():
            setattr(run, k, v)
        return run

class FakeTicketRepository:
    def __init__(self):
        self.tickets = {}

    async def get_by_id(self, ticket_id: str):
        return self.tickets.get(ticket_id)

    async def update(self, ticket, **fields):
        for k, v in fields.items():
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

class FakeUserRepository:
    def __init__(self):
        self.users = {}

    async def get_by_id(self, user_id: str):
        return self.users.get(user_id)

class FakeMessageRepository:
    def __init__(self):
        self.created_messages = []

    async def create(self, **kwargs):
        self.created_messages.append(kwargs)
        return MagicMock()

class FakeAgentRunUnitOfWork:
    def __init__(self):
        self.agent_runs = FakeAgentRunRepository()
        self.tickets = FakeTicketRepository()
        self.channels = FakeChannelRepository()
        self.projects = FakeProjectRepository()
        self.workspace_members = FakeWorkspaceMemberRepository()
        self.project_members = FakeProjectMemberRepository()
        self.users = FakeUserRepository()
        self.messages = FakeMessageRepository()
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_approve_plan_non_lead_rejected():
    uow = FakeAgentRunUnitOfWork()
    service = AgentRunService(uow, redis=AsyncMock())

    # Mock DB Setup
    uow.agent_runs.runs["run-1"] = FakeAgentRun("run-1", "ticket-1", AgentRunStatus.awaiting_review)
    uow.tickets.tickets["ticket-1"] = FakeTicket("ticket-1", "channel-1", TicketStatus.plan_review)
    uow.channels.channels["channel-1"] = FakeChannel("channel-1", "project-1")
    uow.projects.projects["project-1"] = FakeProject("project-1", "ws-1")
    
    # Requester is a standard project member, not a Team Lead or Workspace Owner
    uow.project_members.members[("project-1", "user-member")] = FakeProjectMember(role="member")

    with pytest.raises(HTTPException) as exc_info:
        await service.approve_plan("run-1", "user-member")
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_approve_plan_success_triggers_handoff():
    uow = FakeAgentRunUnitOfWork()
    redis_mock = AsyncMock()
    service = AgentRunService(uow, redis=redis_mock)

    run = FakeAgentRun("run-1", "ticket-1", AgentRunStatus.awaiting_review)
    ticket = FakeTicket("ticket-1", "channel-1", TicketStatus.plan_review)
    
    uow.agent_runs.runs["run-1"] = run
    uow.tickets.tickets["ticket-1"] = ticket
    uow.channels.channels["channel-1"] = FakeChannel("channel-1", "project-1")
    uow.projects.projects["project-1"] = FakeProject("project-1", "ws-1")
    uow.workspace_members.members[("ws-1", "user-owner")] = FakeWorkspaceMember(is_owner=True)
    uow.users.users["user-owner"] = FakeUser("Alice Owner")

    await service.approve_plan("run-1", "user-owner")

    assert run.status == AgentRunStatus.approved
    assert ticket.status == TicketStatus.agent_working
    assert uow.committed is True
    assert len(uow.messages.created_messages) == 1
    assert "approved by Team Lead" in uow.messages.created_messages[0]["content"]
    assert redis_mock.publish.call_count == 1


@pytest.mark.asyncio
async def test_reject_plan_success_reverts_ticket():
    uow = FakeAgentRunUnitOfWork()
    redis_mock = AsyncMock()
    service = AgentRunService(uow, redis=redis_mock)

    run = FakeAgentRun("run-1", "ticket-1", AgentRunStatus.awaiting_review)
    ticket = FakeTicket("ticket-1", "channel-1", TicketStatus.plan_review)

    uow.agent_runs.runs["run-1"] = run
    uow.tickets.tickets["ticket-1"] = ticket
    uow.channels.channels["channel-1"] = FakeChannel("channel-1", "project-1")
    uow.projects.projects["project-1"] = FakeProject("project-1", "ws-1")
    uow.workspace_members.members[("ws-1", "user-owner")] = FakeWorkspaceMember(is_owner=True)
    uow.users.users["user-owner"] = FakeUser("Alice Owner")

    await service.reject_plan("run-1", "user-owner")

    assert run.status == AgentRunStatus.rejected
    # Reverts explicitly back to consensus_reached for re-triggering, never all the way to in_discussion
    assert ticket.status == TicketStatus.consensus_reached
    assert uow.committed is True
    assert redis_mock.publish.call_count == 1


@pytest.mark.asyncio
@patch("app.agent_run.service.AgentRunService._file_exists_in_chunks")
async def test_edit_plan_failing_grounding_rejection(mock_exists):
    # Mock grounding validation returning false on modified file targets
    mock_exists.return_value = False

    uow = FakeAgentRunUnitOfWork()
    service = AgentRunService(uow, redis=AsyncMock())

    run = FakeAgentRun("run-1", "ticket-1", AgentRunStatus.awaiting_review, plan_json={"steps": []})
    ticket = FakeTicket("ticket-1", "channel-1", TicketStatus.plan_review)

    uow.agent_runs.runs["run-1"] = run
    uow.tickets.tickets["ticket-1"] = ticket
    uow.channels.channels["channel-1"] = FakeChannel("channel-1", "project-1")
    uow.projects.projects["project-1"] = FakeProject("project-1", "ws-1")
    uow.workspace_members.members[("ws-1", "user-owner")] = FakeWorkspaceMember(is_owner=True)

    edited_plan_json = {
        "steps": [
            {
                "step_number": 1,
                "description": "Modify main routing logic",
                "action_type": "modify",
                "target_file_path": "missing_router.py"
            }
        ]
    }

    with pytest.raises(HTTPException) as exc_info:
        await service.edit_plan("run-1", edited_plan_json, "user-owner")
    assert exc_info.value.status_code == 400
    assert "Grounding validation failed" in exc_info.value.detail
    assert uow.committed is False


@pytest.mark.asyncio
@patch("app.agent_run.service.AgentRunService._file_exists_in_chunks")
async def test_edit_plan_success_updates_attribution(mock_exists):
    mock_exists.return_value = True # modified target exists successfully

    uow = FakeAgentRunUnitOfWork()
    service = AgentRunService(uow, redis=AsyncMock())

    run = FakeAgentRun("run-1", "ticket-1", AgentRunStatus.awaiting_review, plan_json={"steps": []})
    ticket = FakeTicket("ticket-1", "channel-1", TicketStatus.plan_review)

    uow.agent_runs.runs["run-1"] = run
    uow.tickets.tickets["ticket-1"] = ticket
    uow.channels.channels["channel-1"] = FakeChannel("channel-1", "project-1")
    uow.projects.projects["project-1"] = FakeProject("project-1", "ws-1")
    uow.workspace_members.members[("ws-1", "user-owner")] = FakeWorkspaceMember(is_owner=True)
    uow.users.users["user-owner"] = FakeUser("Alice Owner")

    edited_plan_json = {
        "steps": [
            {
                "step_number": 1,
                "description": "Modify main routing logic",
                "action_type": "modify",
                "target_file_path": "existing_router.py"
            }
        ]
    }

    result = await service.edit_plan("run-1", edited_plan_json, "user-owner")

    assert result == edited_plan_json
    assert run.edited_by_user_id == "user-owner"
    assert run.edited_at is not None
    assert uow.committed is True