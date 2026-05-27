"""
Unit tests for app.project.service.ProjectService
──────────────────────────────────────────────────
All DB I/O is replaced by the fake repos / UoW from conftest.py.

Coverage:
  create_project    — restricted policy (owner ok, member blocked),
                      open policy (any member ok), workspace not found,
                      commits UoW, creator becomes team_lead
  list_projects     — workspace owner sees all, member sees only own,
                      non-workspace-member forbidden, workspace not found
  get_project       — project member can get, workspace owner can get,
                      non-member forbidden, project not found
  update_project    — team lead updates, workspace owner updates,
                      non-lead member blocked, project not found, commits
  delete_project    — workspace owner deletes, team lead (non-owner) blocked,
                      project not found, commits
  list_members      — project member can list, non-member forbidden
  add_member        — team lead adds workspace member, workspace owner adds,
                      target not in workspace blocked, already a member blocked,
                      non-lead member blocked, commits
  update_member_role — team lead promotes member, demotes non-last lead ok,
                       last team lead demotion blocked, member not found,
                       non-lead blocked
  remove_member     — team lead removes member, removes non-last lead ok,
                      last team lead removal blocked, member not found,
                      non-lead blocked, commits
"""
import uuid

import pytest
from fastapi import HTTPException

from app.project.models import ProjectRole
from app.project.schemas import (
    ProjectCreate,
    ProjectMemberAdd,
    ProjectMemberUpdate,
    ProjectUpdate,
)
from app.project.tests.helpers import make_project, make_project_member
from app.workspace.models import ProjectCreationPolicy
from app.workspace.tests.helpers import make_workspace, make_workspace_member


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

def _seed_workspace(fake_uow, workspace_id: str, *, policy=ProjectCreationPolicy.restricted):
    ws = make_workspace(id=workspace_id, project_creation_policy=policy)
    fake_uow.workspaces.seed(ws)
    return ws


def _seed_ws_member(fake_uow, workspace_id: str, user_id: str, *, is_owner=False):
    m = make_workspace_member(workspace_id=workspace_id, user_id=user_id, is_owner=is_owner)
    fake_uow.workspace_members.seed(m)
    return m


def _seed_project(fake_uow, project_id: str, workspace_id: str, *, name="Test Project"):
    p = make_project(id=project_id, workspace_id=workspace_id, name=name)
    fake_uow.projects.seed(p)
    return p


def _seed_project_member(fake_uow, project_id: str, user_id: str, *, role=ProjectRole.member):
    m = make_project_member(project_id=project_id, user_id=user_id, role=role)
    fake_uow.project_members.seed(m)
    return m


# ════════════════════════════════════════════════════════════════════════════
# create_project
# ════════════════════════════════════════════════════════════════════════════

class TestCreateProject:
    @pytest.mark.asyncio
    async def test_workspace_owner_creates_project_in_restricted_workspace(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1", policy=ProjectCreationPolicy.restricted)
        _seed_ws_member(fake_uow, "ws-1", "owner-1", is_owner=True)

        result = await project_service.create_project(
            "ws-1", "owner-1", ProjectCreate(name="Alpha")
        )

        assert result.name == "Alpha"
        assert result.workspace_id == "ws-1"

    @pytest.mark.asyncio
    async def test_non_owner_blocked_in_restricted_workspace(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1", policy=ProjectCreationPolicy.restricted)
        _seed_ws_member(fake_uow, "ws-1", "member-1", is_owner=False)

        with pytest.raises(HTTPException) as exc_info:
            await project_service.create_project(
                "ws-1", "member-1", ProjectCreate(name="Blocked")
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_any_member_can_create_in_open_workspace(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1", policy=ProjectCreationPolicy.open)
        _seed_ws_member(fake_uow, "ws-1", "member-1", is_owner=False)

        result = await project_service.create_project(
            "ws-1", "member-1", ProjectCreate(name="Open Project")
        )

        assert result.name == "Open Project"

    @pytest.mark.asyncio
    async def test_creator_is_added_as_team_lead(self, project_service, fake_uow):
        _seed_workspace(fake_uow, "ws-1", policy=ProjectCreationPolicy.open)
        _seed_ws_member(fake_uow, "ws-1", "user-1")

        result = await project_service.create_project(
            "ws-1", "user-1", ProjectCreate(name="P1")
        )

        member = await fake_uow.project_members.get_by_project_and_user(
            result.id, "user-1"
        )
        assert member is not None
        assert member.role == ProjectRole.team_lead

    @pytest.mark.asyncio
    async def test_workspace_not_found_raises_404(self, project_service):
        with pytest.raises(HTTPException) as exc_info:
            await project_service.create_project(
                "ghost-ws", "user-1", ProjectCreate(name="P1")
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_non_workspace_member_raises_403(self, project_service, fake_uow):
        _seed_workspace(fake_uow, "ws-1", policy=ProjectCreationPolicy.open)

        with pytest.raises(HTTPException) as exc_info:
            await project_service.create_project(
                "ws-1", "outsider", ProjectCreate(name="P1")
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_commits_uow(self, project_service, fake_uow):
        _seed_workspace(fake_uow, "ws-1", policy=ProjectCreationPolicy.open)
        _seed_ws_member(fake_uow, "ws-1", "user-1")

        await project_service.create_project(
            "ws-1", "user-1", ProjectCreate(name="P1")
        )

        assert fake_uow.committed is True

    @pytest.mark.asyncio
    async def test_default_branch_stored(self, project_service, fake_uow):
        _seed_workspace(fake_uow, "ws-1", policy=ProjectCreationPolicy.open)
        _seed_ws_member(fake_uow, "ws-1", "user-1")

        result = await project_service.create_project(
            "ws-1", "user-1", ProjectCreate(name="P1", default_branch="develop")
        )

        assert result.default_branch == "develop"


# ════════════════════════════════════════════════════════════════════════════
# list_projects
# ════════════════════════════════════════════════════════════════════════════

class TestListProjects:
    @pytest.mark.asyncio
    async def test_workspace_owner_sees_all_projects(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")
        _seed_ws_member(fake_uow, "ws-1", "owner-1", is_owner=True)
        _seed_project(fake_uow, "p-1", "ws-1", name="Alpha")
        _seed_project(fake_uow, "p-2", "ws-1", name="Beta")
        # owner-1 is not a project member of either — should still see both

        result = await project_service.list_projects("ws-1", "owner-1")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_regular_member_sees_only_own_projects(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")
        _seed_ws_member(fake_uow, "ws-1", "member-1")
        _seed_project(fake_uow, "p-1", "ws-1", name="Mine")
        _seed_project(fake_uow, "p-2", "ws-1", name="Not Mine")
        _seed_project_member(fake_uow, "p-1", "member-1", role=ProjectRole.member)

        result = await project_service.list_projects("ws-1", "member-1")

        assert len(result) == 1
        assert result[0].id == "p-1"

    @pytest.mark.asyncio
    async def test_member_with_no_projects_gets_empty_list(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")
        _seed_ws_member(fake_uow, "ws-1", "member-1")
        _seed_project(fake_uow, "p-1", "ws-1")

        result = await project_service.list_projects("ws-1", "member-1")

        assert result == []

    @pytest.mark.asyncio
    async def test_non_workspace_member_raises_403(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")

        with pytest.raises(HTTPException) as exc_info:
            await project_service.list_projects("ws-1", "outsider")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_workspace_not_found_raises_404(self, project_service):
        with pytest.raises(HTTPException) as exc_info:
            await project_service.list_projects("ghost", "user-1")
        assert exc_info.value.status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# get_project
# ════════════════════════════════════════════════════════════════════════════

class TestGetProject:
    @pytest.mark.asyncio
    async def test_project_member_can_get_project(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")
        _seed_project(fake_uow, "p-1", "ws-1", name="Alpha")
        _seed_project_member(fake_uow, "p-1", "user-1")

        result = await project_service.get_project("p-1", "user-1")

        assert result.id == "p-1"
        assert result.name == "Alpha"

    @pytest.mark.asyncio
    async def test_workspace_owner_can_get_project_without_being_member(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")
        _seed_ws_member(fake_uow, "ws-1", "owner-1", is_owner=True)
        _seed_project(fake_uow, "p-1", "ws-1")

        result = await project_service.get_project("p-1", "owner-1")

        assert result.id == "p-1"

    @pytest.mark.asyncio
    async def test_non_member_raises_403(self, project_service, fake_uow):
        _seed_workspace(fake_uow, "ws-1")
        _seed_ws_member(fake_uow, "ws-1", "outsider")
        _seed_project(fake_uow, "p-1", "ws-1")

        with pytest.raises(HTTPException) as exc_info:
            await project_service.get_project("p-1", "outsider")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_project_not_found_raises_404(self, project_service):
        with pytest.raises(HTTPException) as exc_info:
            await project_service.get_project("ghost-project", "user-1")
        assert exc_info.value.status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# update_project
# ════════════════════════════════════════════════════════════════════════════

class TestUpdateProject:
    @pytest.mark.asyncio
    async def test_team_lead_can_update_name(self, project_service, fake_uow):
        _seed_workspace(fake_uow, "ws-1")
        _seed_project(fake_uow, "p-1", "ws-1", name="Old")
        _seed_project_member(fake_uow, "p-1", "lead-1", role=ProjectRole.team_lead)

        result = await project_service.update_project(
            "p-1", "lead-1", ProjectUpdate(name="New")
        )

        assert result.name == "New"

    @pytest.mark.asyncio
    async def test_team_lead_can_update_default_branch(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "lead-1", role=ProjectRole.team_lead)

        result = await project_service.update_project(
            "p-1", "lead-1", ProjectUpdate(default_branch="release")
        )

        assert result.default_branch == "release"

    @pytest.mark.asyncio
    async def test_workspace_owner_can_update_without_project_membership(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")
        _seed_ws_member(fake_uow, "ws-1", "owner-1", is_owner=True)
        _seed_project(fake_uow, "p-1", "ws-1", name="Old")

        result = await project_service.update_project(
            "p-1", "owner-1", ProjectUpdate(name="Updated")
        )

        assert result.name == "Updated"

    @pytest.mark.asyncio
    async def test_regular_member_raises_403(self, project_service, fake_uow):
        _seed_workspace(fake_uow, "ws-1")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "member-1", role=ProjectRole.member)

        with pytest.raises(HTTPException) as exc_info:
            await project_service.update_project(
                "p-1", "member-1", ProjectUpdate(name="Hack")
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_project_not_found_raises_404(self, project_service):
        with pytest.raises(HTTPException) as exc_info:
            await project_service.update_project(
                "ghost", "user-1", ProjectUpdate(name="X1")
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_commits_uow(self, project_service, fake_uow):
        _seed_workspace(fake_uow, "ws-1")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "lead-1", role=ProjectRole.team_lead)

        await project_service.update_project(
            "p-1", "lead-1", ProjectUpdate(name="Updated")
        )

        assert fake_uow.committed is True


# ════════════════════════════════════════════════════════════════════════════
# delete_project
# ════════════════════════════════════════════════════════════════════════════

class TestDeleteProject:
    @pytest.mark.asyncio
    async def test_workspace_owner_can_delete(self, project_service, fake_uow):
        _seed_workspace(fake_uow, "ws-1")
        _seed_ws_member(fake_uow, "ws-1", "owner-1", is_owner=True)
        _seed_project(fake_uow, "p-1", "ws-1")

        await project_service.delete_project("p-1", "owner-1")

        assert await fake_uow.projects.get_by_id("p-1") is None

    @pytest.mark.asyncio
    async def test_team_lead_who_is_not_workspace_owner_is_blocked(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")
        _seed_ws_member(fake_uow, "ws-1", "lead-1", is_owner=False)
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "lead-1", role=ProjectRole.team_lead)

        with pytest.raises(HTTPException) as exc_info:
            await project_service.delete_project("p-1", "lead-1")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_project_not_found_raises_404(self, project_service):
        with pytest.raises(HTTPException) as exc_info:
            await project_service.delete_project("ghost", "user-1")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_commits_uow(self, project_service, fake_uow):
        _seed_workspace(fake_uow, "ws-1")
        _seed_ws_member(fake_uow, "ws-1", "owner-1", is_owner=True)
        _seed_project(fake_uow, "p-1", "ws-1")

        await project_service.delete_project("p-1", "owner-1")

        assert fake_uow.committed is True


# ════════════════════════════════════════════════════════════════════════════
# list_members
# ════════════════════════════════════════════════════════════════════════════

class TestListMembers:
    @pytest.mark.asyncio
    async def test_project_member_can_list(self, project_service, fake_uow):
        _seed_workspace(fake_uow, "ws-1")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "user-1", role=ProjectRole.team_lead)
        _seed_project_member(fake_uow, "p-1", "user-2", role=ProjectRole.member)

        result = await project_service.list_members("p-1", "user-1")

        assert len(result) == 2
        user_ids = {m.user_id for m in result}
        assert "user-1" in user_ids
        assert "user-2" in user_ids

    @pytest.mark.asyncio
    async def test_workspace_owner_can_list_without_project_membership(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")
        _seed_ws_member(fake_uow, "ws-1", "owner-1", is_owner=True)
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "user-1")

        result = await project_service.list_members("p-1", "owner-1")

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_non_member_raises_403(self, project_service, fake_uow):
        _seed_workspace(fake_uow, "ws-1")
        _seed_ws_member(fake_uow, "ws-1", "outsider")
        _seed_project(fake_uow, "p-1", "ws-1")

        with pytest.raises(HTTPException) as exc_info:
            await project_service.list_members("p-1", "outsider")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_project_not_found_raises_404(self, project_service):
        with pytest.raises(HTTPException) as exc_info:
            await project_service.list_members("ghost", "user-1")
        assert exc_info.value.status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# add_member
# ════════════════════════════════════════════════════════════════════════════

class TestAddMember:
    @pytest.mark.asyncio
    async def test_team_lead_adds_workspace_member(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")
        _seed_ws_member(fake_uow, "ws-1", "new-user")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "lead-1", role=ProjectRole.team_lead)

        result = await project_service.add_member(
            "p-1", "lead-1", ProjectMemberAdd(user_id="new-user", role=ProjectRole.member)
        )

        assert result.user_id == "new-user"
        assert result.role == ProjectRole.member

    @pytest.mark.asyncio
    async def test_workspace_owner_can_add_without_project_membership(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")
        _seed_ws_member(fake_uow, "ws-1", "owner-1", is_owner=True)
        _seed_ws_member(fake_uow, "ws-1", "new-user")
        _seed_project(fake_uow, "p-1", "ws-1")

        result = await project_service.add_member(
            "p-1", "owner-1", ProjectMemberAdd(user_id="new-user")
        )

        assert result.user_id == "new-user"

    @pytest.mark.asyncio
    async def test_target_not_in_workspace_raises_400(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "lead-1", role=ProjectRole.team_lead)
        # "external-user" is NOT a workspace member

        with pytest.raises(HTTPException) as exc_info:
            await project_service.add_member(
                "p-1", "lead-1", ProjectMemberAdd(user_id="external-user")
            )
        assert exc_info.value.status_code == 400
        assert "workspace member" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_already_a_project_member_raises_409(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")
        _seed_ws_member(fake_uow, "ws-1", "user-2")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "lead-1", role=ProjectRole.team_lead)
        _seed_project_member(fake_uow, "p-1", "user-2", role=ProjectRole.member)

        with pytest.raises(HTTPException) as exc_info:
            await project_service.add_member(
                "p-1", "lead-1", ProjectMemberAdd(user_id="user-2")
            )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_regular_member_cannot_add(self, project_service, fake_uow):
        _seed_workspace(fake_uow, "ws-1")
        _seed_ws_member(fake_uow, "ws-1", "new-user")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "member-1", role=ProjectRole.member)

        with pytest.raises(HTTPException) as exc_info:
            await project_service.add_member(
                "p-1", "member-1", ProjectMemberAdd(user_id="new-user")
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_can_add_as_team_lead_role(self, project_service, fake_uow):
        _seed_workspace(fake_uow, "ws-1")
        _seed_ws_member(fake_uow, "ws-1", "new-lead")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "lead-1", role=ProjectRole.team_lead)

        result = await project_service.add_member(
            "p-1", "lead-1", ProjectMemberAdd(user_id="new-lead", role=ProjectRole.team_lead)
        )

        assert result.role == ProjectRole.team_lead

    @pytest.mark.asyncio
    async def test_commits_uow(self, project_service, fake_uow):
        _seed_workspace(fake_uow, "ws-1")
        _seed_ws_member(fake_uow, "ws-1", "new-user")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "lead-1", role=ProjectRole.team_lead)

        await project_service.add_member(
            "p-1", "lead-1", ProjectMemberAdd(user_id="new-user")
        )

        assert fake_uow.committed is True


# ════════════════════════════════════════════════════════════════════════════
# update_member_role
# ════════════════════════════════════════════════════════════════════════════

class TestUpdateMemberRole:
    @pytest.mark.asyncio
    async def test_team_lead_promotes_member_to_lead(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "lead-1", role=ProjectRole.team_lead)
        _seed_project_member(fake_uow, "p-1", "member-1", role=ProjectRole.member)

        result = await project_service.update_member_role(
            "p-1", "lead-1", "member-1", ProjectMemberUpdate(role=ProjectRole.team_lead)
        )

        assert result.role == ProjectRole.team_lead

    @pytest.mark.asyncio
    async def test_demoting_one_of_two_leads_is_allowed(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "lead-1", role=ProjectRole.team_lead)
        _seed_project_member(fake_uow, "p-1", "lead-2", role=ProjectRole.team_lead)

        result = await project_service.update_member_role(
            "p-1", "lead-1", "lead-2", ProjectMemberUpdate(role=ProjectRole.advisor)
        )

        assert result.role == ProjectRole.advisor

    @pytest.mark.asyncio
    async def test_demoting_last_team_lead_raises_400(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "lead-1", role=ProjectRole.team_lead)

        with pytest.raises(HTTPException) as exc_info:
            await project_service.update_member_role(
                "p-1", "lead-1", "lead-1", ProjectMemberUpdate(role=ProjectRole.member)
            )
        assert exc_info.value.status_code == 400
        assert "last Team Lead" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_member_not_found_raises_404(self, project_service, fake_uow):
        _seed_workspace(fake_uow, "ws-1")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "lead-1", role=ProjectRole.team_lead)

        with pytest.raises(HTTPException) as exc_info:
            await project_service.update_member_role(
                "p-1", "lead-1", "ghost-user", ProjectMemberUpdate(role=ProjectRole.member)
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_regular_member_cannot_change_roles(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "member-1", role=ProjectRole.member)
        _seed_project_member(fake_uow, "p-1", "member-2", role=ProjectRole.member)

        with pytest.raises(HTTPException) as exc_info:
            await project_service.update_member_role(
                "p-1", "member-1", "member-2", ProjectMemberUpdate(role=ProjectRole.advisor)
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_commits_uow(self, project_service, fake_uow):
        _seed_workspace(fake_uow, "ws-1")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "lead-1", role=ProjectRole.team_lead)
        _seed_project_member(fake_uow, "p-1", "member-1", role=ProjectRole.member)

        await project_service.update_member_role(
            "p-1", "lead-1", "member-1", ProjectMemberUpdate(role=ProjectRole.advisor)
        )

        assert fake_uow.committed is True


# ════════════════════════════════════════════════════════════════════════════
# remove_member
# ════════════════════════════════════════════════════════════════════════════

class TestRemoveMember:
    @pytest.mark.asyncio
    async def test_team_lead_removes_regular_member(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "lead-1", role=ProjectRole.team_lead)
        _seed_project_member(fake_uow, "p-1", "member-1", role=ProjectRole.member)

        await project_service.remove_member("p-1", "lead-1", "member-1")

        assert (
            await fake_uow.project_members.get_by_project_and_user("p-1", "member-1")
        ) is None

    @pytest.mark.asyncio
    async def test_can_remove_second_team_lead(self, project_service, fake_uow):
        _seed_workspace(fake_uow, "ws-1")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "lead-1", role=ProjectRole.team_lead)
        _seed_project_member(fake_uow, "p-1", "lead-2", role=ProjectRole.team_lead)

        await project_service.remove_member("p-1", "lead-1", "lead-2")

        assert (
            await fake_uow.project_members.get_by_project_and_user("p-1", "lead-2")
        ) is None

    @pytest.mark.asyncio
    async def test_removing_last_team_lead_raises_400(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "lead-1", role=ProjectRole.team_lead)

        with pytest.raises(HTTPException) as exc_info:
            await project_service.remove_member("p-1", "lead-1", "lead-1")
        assert exc_info.value.status_code == 400
        assert "last Team Lead" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_member_not_found_raises_404(self, project_service, fake_uow):
        _seed_workspace(fake_uow, "ws-1")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "lead-1", role=ProjectRole.team_lead)

        with pytest.raises(HTTPException) as exc_info:
            await project_service.remove_member("p-1", "lead-1", "ghost-user")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_regular_member_cannot_remove_others(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "member-1", role=ProjectRole.member)
        _seed_project_member(fake_uow, "p-1", "member-2", role=ProjectRole.member)

        with pytest.raises(HTTPException) as exc_info:
            await project_service.remove_member("p-1", "member-1", "member-2")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_workspace_owner_can_remove_without_project_membership(
        self, project_service, fake_uow
    ):
        _seed_workspace(fake_uow, "ws-1")
        _seed_ws_member(fake_uow, "ws-1", "owner-1", is_owner=True)
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "lead-1", role=ProjectRole.team_lead)
        _seed_project_member(fake_uow, "p-1", "member-1", role=ProjectRole.member)

        await project_service.remove_member("p-1", "owner-1", "member-1")

        assert (
            await fake_uow.project_members.get_by_project_and_user("p-1", "member-1")
        ) is None

    @pytest.mark.asyncio
    async def test_commits_uow(self, project_service, fake_uow):
        _seed_workspace(fake_uow, "ws-1")
        _seed_project(fake_uow, "p-1", "ws-1")
        _seed_project_member(fake_uow, "p-1", "lead-1", role=ProjectRole.team_lead)
        _seed_project_member(fake_uow, "p-1", "member-1", role=ProjectRole.member)

        await project_service.remove_member("p-1", "lead-1", "member-1")

        assert fake_uow.committed is True