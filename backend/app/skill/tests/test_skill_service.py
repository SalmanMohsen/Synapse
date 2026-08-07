import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
from datetime import datetime, timezone

from app.skill.service import SkillService
from app.skill.models import SkillDimension, SkillFile, SkillAssignment
from app.channel.models import Channel, ChannelDiscipline
from app.project.models import Project, ProjectMember, ProjectRole
from app.workspace.models import WorkspaceMember
from app.skill.schemas import SkillFileCreate, SkillAssignmentAssignTech


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
    def __init__(self, id, project_id):
        self.id = id
        self.project_id = project_id


class FakeSkillFile:
    def __init__(self, id, workspace_id, name, dimension, file_content, discipline=None):
        self.id = id
        self.workspace_id = workspace_id
        self.name = name
        self.dimension = dimension
        self.discipline = discipline
        self.file_content = file_content
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


class FakeSkillAssignment:
    def __init__(self, id, channel_id, specialty_file_id=None, technology_file_id=None):
        self.id = id
        self.channel_id = channel_id
        self.specialty_file_id = specialty_file_id
        self.technology_file_id = technology_file_id
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


class FakeSkillRepository:
    def __init__(self):
        self.files = {}
        self.assignments = {}

    async def create_file(self, **kwargs):
        f_id = str(uuid.uuid4())
        sf = FakeSkillFile(
            id=f_id,
            workspace_id=kwargs["workspace_id"],
            name=kwargs["name"],
            dimension=kwargs["dimension"],
            discipline=kwargs.get("discipline"),
            file_content=kwargs["file_content"]
        )
        self.files[f_id] = sf
        return sf

    async def get_file_by_id(self, file_id):
        return self.files.get(file_id)

    async def get_assignment_by_channel(self, channel_id):
        return self.assignments.get(channel_id)

    async def create_assignment(self, **kwargs):
        a_id = str(uuid.uuid4())
        sa = FakeSkillAssignment(
            id=a_id,
            channel_id=kwargs["channel_id"],
            specialty_file_id=kwargs.get("specialty_file_id"),
            technology_file_id=kwargs.get("technology_file_id")
        )
        self.assignments[kwargs["channel_id"]] = sa
        return sa

    async def update_assignment(self, assignment, **kwargs):
        for k, v in kwargs.items():
            setattr(assignment, k, v)
        return assignment


class FakeChannelRepository:
    def __init__(self):
        self.channels = {}

    async def get_by_id(self, channel_id):
        return self.channels.get(channel_id)


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


class FakeSkillUnitOfWork:
    def __init__(self):
        self.skills = FakeSkillRepository()
        self.channels = FakeChannelRepository()
        self.projects = FakeProjectRepository()
        self.project_members = FakeProjectMemberRepository()
        self.workspace_members = FakeWorkspaceMemberRepository()
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
def skill_uow():
    return FakeSkillUnitOfWork()


@pytest.fixture
def skill_service(skill_uow):
    return SkillService(uow=skill_uow)


@pytest.mark.asyncio
async def test_create_skill_file_success(skill_service, skill_uow):
    skill_uow.workspace_members.members[("ws-1", "user-owner")] = FakeWorkspaceMember("ws-1", "user-owner", is_owner=True)
    
    data = SkillFileCreate(
        name="Backend Guidelines",
        dimension=SkillDimension.specialty,
        discipline=ChannelDiscipline.backend,
        file_content="Coding Rules"
    )

    result = await skill_service.create_skill_file("ws-1", "user-owner", data)

    assert result.name == "Backend Guidelines"
    assert result.discipline == ChannelDiscipline.backend
    assert skill_uow.committed is True


@pytest.mark.asyncio
async def test_create_skill_file_non_owner_forbidden(skill_service, skill_uow):
    # User is not workspace owner
    skill_uow.workspace_members.members[("ws-1", "user-member")] = FakeWorkspaceMember("ws-1", "user-member", is_owner=False)

    data = SkillFileCreate(
        name="General Tech",
        dimension=SkillDimension.technology,
        file_content="Stack Config"
    )

    with pytest.raises(HTTPException) as exc_info:
        await skill_service.create_skill_file("ws-1", "user-member", data)

    assert exc_info.value.status_code == 403
    assert "Only workspace owners" in exc_info.value.detail


@pytest.mark.asyncio
async def test_assign_technology_file_team_lead_success(skill_service, skill_uow):
    # Setup databases
    skill_uow.channels.channels["ch-1"] = FakeChannel("ch-1", "p-1")
    skill_uow.projects.projects["p-1"] = FakeProject("p-1", "ws-1")
    skill_uow.project_members.members[("p-1", "user-lead")] = FakeProjectMember("p-1", "user-lead", ProjectRole.team_lead)
    
    # Pre-add the technology file belonging to the same workspace
    sf = FakeSkillFile("tf-1", "ws-1", "Postgres Profile", SkillDimension.technology, "DB Tuning")
    skill_uow.skills.files["tf-1"] = sf

    data = SkillAssignmentAssignTech(technology_file_id="tf-1")
    result = await skill_service.assign_technology_file("ch-1", "user-lead", data)

    assert result.technology_file_id == "tf-1"
    assert skill_uow.committed is True


@pytest.mark.asyncio
async def test_assign_technology_file_mismatched_workspace_rejected(skill_service, skill_uow):
    skill_uow.channels.channels["ch-1"] = FakeChannel("ch-1", "p-1")
    skill_uow.projects.projects["p-1"] = FakeProject("p-1", "ws-1")
    skill_uow.project_members.members[("p-1", "user-lead")] = FakeProjectMember("p-1", "user-lead", ProjectRole.team_lead)
    
    # Technology file belongs to a different workspace (ws-other)
    sf = FakeSkillFile("tf-1", "ws-other", "Postgres Profile", SkillDimension.technology, "DB Tuning")
    skill_uow.skills.files["tf-1"] = sf

    data = SkillAssignmentAssignTech(technology_file_id="tf-1")
    with pytest.raises(HTTPException) as exc_info:
        await skill_service.assign_technology_file("ch-1", "user-lead", data)

    assert exc_info.value.status_code == 400
    assert "valid tech matrix profile file within this workspace" in exc_info.value.detail