"""
Unit tests for ChannelService.

All tests run against fake in-memory repos — no database, no FastAPI app.
Fixtures come from conftest.py in this package.
"""
import pytest
from fastapi import HTTPException

from app.channel.models import (
    ApprovalPolicy,
    ChannelDiscipline,
    ChannelMemberRole,
)
from app.channel.schemas import (
    ChannelCreate,
    ChannelMemberAdd,
    ChannelMemberUpdate,
    ChannelUpdate,
)
from app.channel.tests.helpers import make_channel, make_channel_member
from app.project.models import ProjectRole
from app.project.tests.helpers import make_project_member
from app.workspace.tests.helpers import make_workspace_member


# ================================================================== #
# create_channel                                                       #
# ================================================================== #


class TestCreateChannel:
    async def test_team_lead_creates_channel(self, channel_service, world):
        data = ChannelCreate(name="Backend", discipline=ChannelDiscipline.backend)
        channel = await channel_service.create_channel(
            world["project"].id, world["team_lead_id"], data
        )
        assert channel.name == "Backend"
        assert channel.discipline == ChannelDiscipline.backend
        assert channel.is_leads_channel is False

    async def test_owner_creates_channel(self, channel_service, world):
        data = ChannelCreate(name="Frontend", discipline=ChannelDiscipline.frontend)
        channel = await channel_service.create_channel(
            world["project"].id, world["owner_id"], data
        )
        assert channel.discipline == ChannelDiscipline.frontend

    async def test_plain_member_cannot_create_channel(self, channel_service, world):
        data = ChannelCreate(name="DevOps", discipline=ChannelDiscipline.devops)
        with pytest.raises(HTTPException) as exc_info:
            await channel_service.create_channel(
                world["project"].id, world["member_id"], data
            )
        assert exc_info.value.status_code == 403

    async def test_duplicate_discipline_rejected(
        self, channel_service, world, channel_repo
    ):
        existing = make_channel(
            project_id=world["project"].id, discipline=ChannelDiscipline.backend
        )
        channel_repo.seed(existing)

        data = ChannelCreate(name="Backend 2", discipline=ChannelDiscipline.backend)
        with pytest.raises(HTTPException) as exc_info:
            await channel_service.create_channel(
                world["project"].id, world["team_lead_id"], data
            )
        assert exc_info.value.status_code == 409

    async def test_different_disciplines_can_coexist(
        self, channel_service, world, channel_repo
    ):
        existing = make_channel(
            project_id=world["project"].id, discipline=ChannelDiscipline.backend
        )
        channel_repo.seed(existing)

        data = ChannelCreate(name="Frontend", discipline=ChannelDiscipline.frontend)
        channel = await channel_service.create_channel(
            world["project"].id, world["team_lead_id"], data
        )
        assert channel.discipline == ChannelDiscipline.frontend

    async def test_unknown_project_raises_404(self, channel_service, world):
        data = ChannelCreate(name="Backend", discipline=ChannelDiscipline.backend)
        with pytest.raises(HTTPException) as exc_info:
            await channel_service.create_channel(
                "nonexistent-project-id", world["team_lead_id"], data
            )
        assert exc_info.value.status_code == 404

    async def test_approval_policy_stored(self, channel_service, world):
        data = ChannelCreate(
            name="QA",
            discipline=ChannelDiscipline.qa_testing,
            approval_policy=ApprovalPolicy.any_member,
        )
        channel = await channel_service.create_channel(
            world["project"].id, world["team_lead_id"], data
        )
        assert channel.approval_policy == ApprovalPolicy.any_member

    async def test_commit_called_on_success(self, fake_uow, channel_service, world):
        data = ChannelCreate(name="Mobile", discipline=ChannelDiscipline.mobile)
        await channel_service.create_channel(
            world["project"].id, world["team_lead_id"], data
        )
        assert fake_uow.committed is True


# ================================================================== #
# create_leads_channel                                                 #
# ================================================================== #


class TestCreateLeadsChannel:
    async def test_team_lead_creates_leads_channel(self, channel_service, world):
        channel = await channel_service.create_leads_channel(
            world["project"].id, world["team_lead_id"]
        )
        assert channel.is_leads_channel is True
        assert channel.discipline is None
        assert channel.approval_policy == ApprovalPolicy.lead_only

    async def test_second_leads_channel_rejected(
        self, channel_service, world, channel_repo
    ):
        existing = make_channel(
            project_id=world["project"].id,
            is_leads_channel=True,
            discipline=None,
        )
        channel_repo.seed(existing)

        with pytest.raises(HTTPException) as exc_info:
            await channel_service.create_leads_channel(
                world["project"].id, world["team_lead_id"]
            )
        assert exc_info.value.status_code == 409

    async def test_plain_member_cannot_create_leads_channel(
        self, channel_service, world
    ):
        with pytest.raises(HTTPException) as exc_info:
            await channel_service.create_leads_channel(
                world["project"].id, world["member_id"]
            )
        assert exc_info.value.status_code == 403


# ================================================================== #
# list_channels                                                        #
# ================================================================== #


class TestListChannels:
    async def test_team_lead_sees_all_channels(
        self, channel_service, world, channel_repo
    ):
        for discipline in (ChannelDiscipline.backend, ChannelDiscipline.frontend):
            channel_repo.seed(
                make_channel(project_id=world["project"].id, discipline=discipline)
            )

        channels = await channel_service.list_channels(
            world["project"].id, world["team_lead_id"]
        )
        assert len(channels) == 2

    async def test_plain_member_can_list_channels(
        self, channel_service, world, channel_repo
    ):
        channel_repo.seed(
            make_channel(
                project_id=world["project"].id, discipline=ChannelDiscipline.backend
            )
        )
        channels = await channel_service.list_channels(
            world["project"].id, world["member_id"]
        )
        assert len(channels) == 1

    async def test_outsider_cannot_list_channels(self, channel_service, world):
        import uuid

        outsider_id = str(uuid.uuid4())
        with pytest.raises(HTTPException) as exc_info:
            await channel_service.list_channels(world["project"].id, outsider_id)
        assert exc_info.value.status_code == 403

    async def test_empty_project_returns_empty_list(
        self, channel_service, world
    ):
        channels = await channel_service.list_channels(
            world["project"].id, world["team_lead_id"]
        )
        assert channels == []


# ================================================================== #
# get_channel                                                          #
# ================================================================== #


class TestGetChannel:
    async def test_project_member_can_get_channel(
        self, channel_service, world, channel_repo
    ):
        channel = make_channel(project_id=world["project"].id)
        channel_repo.seed(channel)

        result = await channel_service.get_channel(channel.id, world["member_id"])
        assert result.id == channel.id

    async def test_unknown_channel_raises_404(self, channel_service, world):
        with pytest.raises(HTTPException) as exc_info:
            await channel_service.get_channel("no-such-channel", world["team_lead_id"])
        assert exc_info.value.status_code == 404

    async def test_outsider_cannot_get_channel(
        self, channel_service, world, channel_repo
    ):
        import uuid

        channel = make_channel(project_id=world["project"].id)
        channel_repo.seed(channel)

        outsider_id = str(uuid.uuid4())
        with pytest.raises(HTTPException) as exc_info:
            await channel_service.get_channel(channel.id, outsider_id)
        assert exc_info.value.status_code == 403


# ================================================================== #
# update_channel                                                       #
# ================================================================== #


class TestUpdateChannel:
    async def test_team_lead_updates_name(
        self, channel_service, world, channel_repo
    ):
        channel = make_channel(project_id=world["project"].id, name="old-name")
        channel_repo.seed(channel)

        result = await channel_service.update_channel(
            channel.id, world["team_lead_id"], ChannelUpdate(name="new-name")
        )
        assert result.name == "new-name"

    async def test_team_lead_updates_approval_policy(
        self, channel_service, world, channel_repo
    ):
        channel = make_channel(
            project_id=world["project"].id,
            approval_policy=ApprovalPolicy.lead_only,
        )
        channel_repo.seed(channel)

        result = await channel_service.update_channel(
            channel.id,
            world["team_lead_id"],
            ChannelUpdate(approval_policy=ApprovalPolicy.any_member),
        )
        assert result.approval_policy == ApprovalPolicy.any_member

    async def test_plain_member_cannot_update(
        self, channel_service, world, channel_repo
    ):
        channel = make_channel(project_id=world["project"].id)
        channel_repo.seed(channel)

        with pytest.raises(HTTPException) as exc_info:
            await channel_service.update_channel(
                channel.id, world["member_id"], ChannelUpdate(name="sneaky")
            )
        assert exc_info.value.status_code == 403

    async def test_empty_update_is_a_noop(
        self, channel_service, world, channel_repo, fake_uow
    ):
        channel = make_channel(project_id=world["project"].id, name="stable")
        channel_repo.seed(channel)

        result = await channel_service.update_channel(
            channel.id, world["team_lead_id"], ChannelUpdate()
        )
        assert result.name == "stable"
        assert fake_uow.committed is True


# ================================================================== #
# delete_channel                                                       #
# ================================================================== #


class TestDeleteChannel:
    async def test_team_lead_deletes_channel(
        self, channel_service, world, channel_repo
    ):
        channel = make_channel(project_id=world["project"].id)
        channel_repo.seed(channel)

        await channel_service.delete_channel(channel.id, world["team_lead_id"])
        assert await channel_repo.get_by_id(channel.id) is None

    async def test_leads_channel_cannot_be_deleted(
        self, channel_service, world, channel_repo
    ):
        leads = make_channel(
            project_id=world["project"].id, is_leads_channel=True, discipline=None
        )
        channel_repo.seed(leads)

        with pytest.raises(HTTPException) as exc_info:
            await channel_service.delete_channel(leads.id, world["team_lead_id"])
        assert exc_info.value.status_code == 400

    async def test_plain_member_cannot_delete(
        self, channel_service, world, channel_repo
    ):
        channel = make_channel(project_id=world["project"].id)
        channel_repo.seed(channel)

        with pytest.raises(HTTPException) as exc_info:
            await channel_service.delete_channel(channel.id, world["member_id"])
        assert exc_info.value.status_code == 403

    async def test_unknown_channel_raises_404(self, channel_service, world):
        with pytest.raises(HTTPException) as exc_info:
            await channel_service.delete_channel(
                "ghost-channel", world["team_lead_id"]
            )
        assert exc_info.value.status_code == 404


# ================================================================== #
# add_member                                                           #
# ================================================================== #


class TestAddMember:
    async def test_team_lead_adds_member(
        self, channel_service, world, channel_repo
    ):
        channel = make_channel(project_id=world["project"].id)
        channel_repo.seed(channel)

        result = await channel_service.add_member(
            channel.id,
            world["team_lead_id"],
            ChannelMemberAdd(user_id=world["member_id"]),
        )
        assert result.user_id == world["member_id"]
        assert result.role == ChannelMemberRole.member

    async def test_channel_lead_adds_member(
        self,
        channel_service,
        world,
        channel_repo,
        channel_member_repo,
        project_member_repo,
    ):
        import uuid

        channel = make_channel(project_id=world["project"].id)
        channel_repo.seed(channel)

        channel_lead_id = str(uuid.uuid4())
        # channel lead must also be a project member
        project_member_repo.seed(
            make_project_member(
                project_id=world["project"].id,
                user_id=channel_lead_id,
                role=ProjectRole.member,
            )
        )
        channel_member_repo.seed(
            make_channel_member(
                channel_id=channel.id,
                user_id=channel_lead_id,
                role=ChannelMemberRole.channel_lead,
            )
        )

        new_member_id = str(uuid.uuid4())
        project_member_repo.seed(
            make_project_member(
                project_id=world["project"].id,
                user_id=new_member_id,
                role=ProjectRole.member,
            )
        )

        result = await channel_service.add_member(
            channel.id,
            channel_lead_id,
            ChannelMemberAdd(user_id=new_member_id),
        )
        assert result.user_id == new_member_id

    async def test_plain_member_cannot_add(
        self, channel_service, world, channel_repo
    ):
        channel = make_channel(project_id=world["project"].id)
        channel_repo.seed(channel)

        with pytest.raises(HTTPException) as exc_info:
            await channel_service.add_member(
                channel.id,
                world["member_id"],
                ChannelMemberAdd(user_id=world["team_lead_id"]),
            )
        assert exc_info.value.status_code == 403

    async def test_non_project_member_cannot_be_added(
        self, channel_service, world, channel_repo
    ):
        import uuid

        channel = make_channel(project_id=world["project"].id)
        channel_repo.seed(channel)

        outsider_id = str(uuid.uuid4())
        with pytest.raises(HTTPException) as exc_info:
            await channel_service.add_member(
                channel.id,
                world["team_lead_id"],
                ChannelMemberAdd(user_id=outsider_id),
            )
        assert exc_info.value.status_code == 400

    async def test_duplicate_member_rejected(
        self, channel_service, world, channel_repo, channel_member_repo
    ):
        channel = make_channel(project_id=world["project"].id)
        channel_repo.seed(channel)
        channel_member_repo.seed(
            make_channel_member(
                channel_id=channel.id, user_id=world["member_id"]
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await channel_service.add_member(
                channel.id,
                world["team_lead_id"],
                ChannelMemberAdd(user_id=world["member_id"]),
            )
        assert exc_info.value.status_code == 409

    async def test_add_as_channel_lead(
        self, channel_service, world, channel_repo
    ):
        channel = make_channel(project_id=world["project"].id)
        channel_repo.seed(channel)

        result = await channel_service.add_member(
            channel.id,
            world["team_lead_id"],
            ChannelMemberAdd(
                user_id=world["member_id"], role=ChannelMemberRole.channel_lead
            ),
        )
        assert result.role == ChannelMemberRole.channel_lead


# ================================================================== #
# update_member_role                                                   #
# ================================================================== #


class TestUpdateMemberRole:
    async def test_team_lead_promotes_to_channel_lead(
        self, channel_service, world, channel_repo, channel_member_repo
    ):
        channel = make_channel(project_id=world["project"].id)
        channel_repo.seed(channel)
        channel_member_repo.seed(
            make_channel_member(
                channel_id=channel.id,
                user_id=world["member_id"],
                role=ChannelMemberRole.member,
            )
        )

        result = await channel_service.update_member_role(
            channel.id,
            world["team_lead_id"],
            world["member_id"],
            ChannelMemberUpdate(role=ChannelMemberRole.channel_lead),
        )
        assert result.role == ChannelMemberRole.channel_lead

    async def test_unknown_member_raises_404(
        self, channel_service, world, channel_repo
    ):
        import uuid

        channel = make_channel(project_id=world["project"].id)
        channel_repo.seed(channel)

        with pytest.raises(HTTPException) as exc_info:
            await channel_service.update_member_role(
                channel.id,
                world["team_lead_id"],
                str(uuid.uuid4()),
                ChannelMemberUpdate(role=ChannelMemberRole.channel_lead),
            )
        assert exc_info.value.status_code == 404

    async def test_plain_member_cannot_update_roles(
        self, channel_service, world, channel_repo, channel_member_repo
    ):
        channel = make_channel(project_id=world["project"].id)
        channel_repo.seed(channel)
        channel_member_repo.seed(
            make_channel_member(
                channel_id=channel.id,
                user_id=world["member_id"],
                role=ChannelMemberRole.member,
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await channel_service.update_member_role(
                channel.id,
                world["member_id"],
                world["member_id"],
                ChannelMemberUpdate(role=ChannelMemberRole.channel_lead),
            )
        assert exc_info.value.status_code == 403


# ================================================================== #
# remove_member                                                        #
# ================================================================== #


class TestRemoveMember:
    async def test_team_lead_removes_member(
        self, channel_service, world, channel_repo, channel_member_repo
    ):
        channel = make_channel(project_id=world["project"].id)
        channel_repo.seed(channel)
        channel_member_repo.seed(
            make_channel_member(
                channel_id=channel.id, user_id=world["member_id"]
            )
        )

        await channel_service.remove_member(
            channel.id, world["team_lead_id"], world["member_id"]
        )
        assert (
            await channel_member_repo.get_by_channel_and_user(
                channel.id, world["member_id"]
            )
            is None
        )

    async def test_channel_lead_removes_member(
        self,
        channel_service,
        world,
        channel_repo,
        channel_member_repo,
        project_member_repo,
    ):
        import uuid

        channel = make_channel(project_id=world["project"].id)
        channel_repo.seed(channel)

        channel_lead_id = str(uuid.uuid4())
        project_member_repo.seed(
            make_project_member(
                project_id=world["project"].id,
                user_id=channel_lead_id,
                role=ProjectRole.member,
            )
        )
        channel_member_repo.seed(
            make_channel_member(
                channel_id=channel.id,
                user_id=channel_lead_id,
                role=ChannelMemberRole.channel_lead,
            )
        )
        channel_member_repo.seed(
            make_channel_member(
                channel_id=channel.id,
                user_id=world["member_id"],
                role=ChannelMemberRole.member,
            )
        )

        await channel_service.remove_member(
            channel.id, channel_lead_id, world["member_id"]
        )
        assert (
            await channel_member_repo.get_by_channel_and_user(
                channel.id, world["member_id"]
            )
            is None
        )

    async def test_plain_member_cannot_remove(
        self, channel_service, world, channel_repo, channel_member_repo
    ):
        channel = make_channel(project_id=world["project"].id)
        channel_repo.seed(channel)
        channel_member_repo.seed(
            make_channel_member(
                channel_id=channel.id, user_id=world["member_id"]
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await channel_service.remove_member(
                channel.id, world["member_id"], world["member_id"]
            )
        assert exc_info.value.status_code == 403

    async def test_unknown_member_raises_404(
        self, channel_service, world, channel_repo
    ):
        import uuid

        channel = make_channel(project_id=world["project"].id)
        channel_repo.seed(channel)

        with pytest.raises(HTTPException) as exc_info:
            await channel_service.remove_member(
                channel.id, world["team_lead_id"], str(uuid.uuid4())
            )
        assert exc_info.value.status_code == 404


# ================================================================== #
# list_members                                                         #
# ================================================================== #


class TestListMembers:
    async def test_returns_all_channel_members(
        self, channel_service, world, channel_repo, channel_member_repo
    ):
        channel = make_channel(project_id=world["project"].id)
        channel_repo.seed(channel)
        channel_member_repo.seed(
            make_channel_member(channel_id=channel.id, user_id=world["member_id"])
        )
        channel_member_repo.seed(
            make_channel_member(channel_id=channel.id, user_id=world["team_lead_id"])
        )

        members = await channel_service.list_members(
            channel.id, world["team_lead_id"]
        )
        assert len(members) == 2

    async def test_outsider_cannot_list_members(
        self, channel_service, world, channel_repo
    ):
        import uuid

        channel = make_channel(project_id=world["project"].id)
        channel_repo.seed(channel)

        with pytest.raises(HTTPException) as exc_info:
            await channel_service.list_members(channel.id, str(uuid.uuid4()))
        assert exc_info.value.status_code == 403