"""
Unit tests for app.workspace.service.WorkspaceService
──────────────────────────────────────────────────────
All DB I/O is replaced by the fake repos / UoW from conftest.py.

Coverage:
  create_workspace  — happy path, creator becomes owner + member, commits
  get_workspace     — happy path, not found, non-member forbidden
  update_workspace  — owner updates, non-owner forbidden, not found
  delete_workspace  — owner deletes, non-owner forbidden, not found
  list_members      — happy path, non-member forbidden, not found
  add_owner         — happy path, non-owner forbidden, target not member,
                      target already owner
  remove_member     — happy path, non-owner forbidden, member not found,
                      last owner blocked, second owner removal succeeds,
                      cascade cleans project and channel memberships (Fix #5),
                      self-removal allowed without being owner
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.workspace.models import ProjectCreationPolicy
from app.workspace.schemas import WorkspaceCreate, WorkspaceUpdate
from app.workspace.tests.helpers import make_workspace, make_workspace_member


def _make_project(workspace_id: str, project_id: str | None = None) -> MagicMock:
    p = MagicMock()
    p.id = project_id or str(uuid.uuid4())
    p.workspace_id = workspace_id
    return p


def _make_project_member(project_id: str, user_id: str) -> MagicMock:
    m = MagicMock()
    m.project_id = project_id
    m.user_id = user_id
    return m


def _make_channel(project_id: str, channel_id: str | None = None) -> MagicMock:
    c = MagicMock()
    c.id = channel_id or str(uuid.uuid4())
    c.project_id = project_id
    return c


def _make_channel_member(channel_id: str, user_id: str) -> MagicMock:
    m = MagicMock()
    m.channel_id = channel_id
    m.user_id = user_id
    return m


# ════════════════════════════════════════════════════════════════════════════
# create_workspace
# ════════════════════════════════════════════════════════════════════════════


class TestCreateWorkspace:
    @pytest.mark.asyncio
    async def test_returns_workspace_read(self, workspace_service):
        result = await workspace_service.create_workspace("user-1", WorkspaceCreate(name="Acme"))
        assert result.name == "Acme"
        assert result.id is not None

    @pytest.mark.asyncio
    async def test_creator_is_added_as_owner_member(self, workspace_service, member_repo):
        result = await workspace_service.create_workspace("user-1", WorkspaceCreate(name="Acme"))
        member = await member_repo.get_by_workspace_and_user(result.id, "user-1")
        assert member is not None
        assert member.is_owner is True

    @pytest.mark.asyncio
    async def test_default_policy_is_restricted(self, workspace_service):
        result = await workspace_service.create_workspace("user-1", WorkspaceCreate(name="Acme"))
        assert result.project_creation_policy == ProjectCreationPolicy.restricted

    @pytest.mark.asyncio
    async def test_commits_uow(self, workspace_service, fake_uow):
        await workspace_service.create_workspace("user-1", WorkspaceCreate(name="Xr"))
        assert fake_uow.committed is True


# ════════════════════════════════════════════════════════════════════════════
# get_workspace
# ════════════════════════════════════════════════════════════════════════════


class TestGetWorkspace:
    @pytest.mark.asyncio
    async def test_member_can_get_workspace(self, workspace_service, workspace_repo, member_repo):
        ws = make_workspace(id="ws-1", name="My WS")
        workspace_repo.seed(ws)
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="user-1"))
        result = await workspace_service.get_workspace("ws-1", "user-1")
        assert result.id == "ws-1"
        assert result.name == "My WS"

    @pytest.mark.asyncio
    async def test_unknown_workspace_raises_404(self, workspace_service):
        with pytest.raises(HTTPException) as exc_info:
            await workspace_service.get_workspace("does-not-exist", "user-1")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_non_member_raises_403(self, workspace_service, workspace_repo):
        workspace_repo.seed(make_workspace(id="ws-1"))
        with pytest.raises(HTTPException) as exc_info:
            await workspace_service.get_workspace("ws-1", "outsider")
        assert exc_info.value.status_code == 403


# ════════════════════════════════════════════════════════════════════════════
# update_workspace
# ════════════════════════════════════════════════════════════════════════════


class TestUpdateWorkspace:
    @pytest.mark.asyncio
    async def test_owner_can_update_name(self, workspace_service, workspace_repo, member_repo):
        workspace_repo.seed(make_workspace(id="ws-1", name="Old Name"))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="owner-1", is_owner=True))
        result = await workspace_service.update_workspace("ws-1", WorkspaceUpdate(name="New Name"), "owner-1")
        assert result.name == "New Name"

    @pytest.mark.asyncio
    async def test_owner_can_update_policy(self, workspace_service, workspace_repo, member_repo):
        workspace_repo.seed(make_workspace(id="ws-1"))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="owner-1", is_owner=True))
        result = await workspace_service.update_workspace(
            "ws-1",
            WorkspaceUpdate(project_creation_policy=ProjectCreationPolicy.open),
            "owner-1",
        )
        assert result.project_creation_policy == ProjectCreationPolicy.open

    @pytest.mark.asyncio
    async def test_non_owner_raises_403(self, workspace_service, workspace_repo, member_repo):
        workspace_repo.seed(make_workspace(id="ws-1"))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="member-1", is_owner=False))
        with pytest.raises(HTTPException) as exc_info:
            await workspace_service.update_workspace("ws-1", WorkspaceUpdate(name="Xr"), "member-1")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_unknown_workspace_raises_404(self, workspace_service):
        with pytest.raises(HTTPException) as exc_info:
            await workspace_service.update_workspace("ghost", WorkspaceUpdate(name="Xr"), "user-1")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_commits_uow(self, workspace_service, workspace_repo, member_repo, fake_uow):
        workspace_repo.seed(make_workspace(id="ws-1"))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="owner-1", is_owner=True))
        await workspace_service.update_workspace("ws-1", WorkspaceUpdate(name="Yr"), "owner-1")
        assert fake_uow.committed is True


# ════════════════════════════════════════════════════════════════════════════
# delete_workspace
# ════════════════════════════════════════════════════════════════════════════


class TestDeleteWorkspace:
    @pytest.mark.asyncio
    async def test_owner_can_delete(self, workspace_service, workspace_repo, member_repo):
        workspace_repo.seed(make_workspace(id="ws-1"))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="owner-1", is_owner=True))
        await workspace_service.delete_workspace("ws-1", "owner-1")
        assert await workspace_repo.get_by_id("ws-1") is None

    @pytest.mark.asyncio
    async def test_non_owner_raises_403(self, workspace_service, workspace_repo, member_repo):
        workspace_repo.seed(make_workspace(id="ws-1"))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="member-1", is_owner=False))
        with pytest.raises(HTTPException) as exc_info:
            await workspace_service.delete_workspace("ws-1", "member-1")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_unknown_workspace_raises_404(self, workspace_service):
        with pytest.raises(HTTPException) as exc_info:
            await workspace_service.delete_workspace("ghost", "user-1")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_commits_uow(self, workspace_service, workspace_repo, member_repo, fake_uow):
        workspace_repo.seed(make_workspace(id="ws-1"))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="owner-1", is_owner=True))
        await workspace_service.delete_workspace("ws-1", "owner-1")
        assert fake_uow.committed is True


# ════════════════════════════════════════════════════════════════════════════
# list_members
# ════════════════════════════════════════════════════════════════════════════


class TestListMembers:
    @pytest.mark.asyncio
    async def test_member_can_list(self, workspace_service, workspace_repo, member_repo):
        workspace_repo.seed(make_workspace(id="ws-1"))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="user-1", is_owner=True))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="user-2"))
        result = await workspace_service.list_members("ws-1", "user-1")
        assert len(result) == 2
        assert {"user-1", "user-2"} == {m.user_id for m in result}

    @pytest.mark.asyncio
    async def test_non_member_raises_403(self, workspace_service, workspace_repo):
        workspace_repo.seed(make_workspace(id="ws-1"))
        with pytest.raises(HTTPException) as exc_info:
            await workspace_service.list_members("ws-1", "outsider")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_unknown_workspace_raises_404(self, workspace_service):
        with pytest.raises(HTTPException) as exc_info:
            await workspace_service.list_members("ghost", "user-1")
        assert exc_info.value.status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# add_owner
# ════════════════════════════════════════════════════════════════════════════


class TestAddOwner:
    @pytest.mark.asyncio
    async def test_owner_promotes_member_to_owner(self, workspace_service, workspace_repo, member_repo):
        workspace_repo.seed(make_workspace(id="ws-1"))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="owner-1", is_owner=True))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="member-1", is_owner=False))
        result = await workspace_service.add_owner("ws-1", "member-1", "owner-1")
        assert result.is_owner is True
        assert result.user_id == "member-1"

    @pytest.mark.asyncio
    async def test_non_owner_raises_403(self, workspace_service, workspace_repo, member_repo):
        workspace_repo.seed(make_workspace(id="ws-1"))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="member-1", is_owner=False))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="member-2", is_owner=False))
        with pytest.raises(HTTPException) as exc_info:
            await workspace_service.add_owner("ws-1", "member-2", "member-1")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_target_not_in_workspace_raises_404(self, workspace_service, workspace_repo, member_repo):
        workspace_repo.seed(make_workspace(id="ws-1"))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="owner-1", is_owner=True))
        with pytest.raises(HTTPException) as exc_info:
            await workspace_service.add_owner("ws-1", "ghost-user", "owner-1")
        assert exc_info.value.status_code == 404
        assert "not a member" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_target_already_owner_raises_409(self, workspace_service, workspace_repo, member_repo):
        workspace_repo.seed(make_workspace(id="ws-1"))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="owner-1", is_owner=True))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="owner-2", is_owner=True))
        with pytest.raises(HTTPException) as exc_info:
            await workspace_service.add_owner("ws-1", "owner-2", "owner-1")
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_unknown_workspace_raises_404(self, workspace_service):
        with pytest.raises(HTTPException) as exc_info:
            await workspace_service.add_owner("ghost", "user-1", "user-2")
        assert exc_info.value.status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# remove_member
# ════════════════════════════════════════════════════════════════════════════


class TestRemoveMember:
    @pytest.mark.asyncio
    async def test_owner_removes_regular_member(self, workspace_service, workspace_repo, member_repo):
        workspace_repo.seed(make_workspace(id="ws-1"))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="owner-1", is_owner=True))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="member-1", is_owner=False))
        await workspace_service.remove_member("ws-1", "member-1", "owner-1")
        assert await member_repo.get_by_workspace_and_user("ws-1", "member-1") is None

    @pytest.mark.asyncio
    async def test_non_owner_cannot_remove_another_member(
        self, workspace_service, workspace_repo, member_repo
    ):
        workspace_repo.seed(make_workspace(id="ws-1"))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="member-1", is_owner=False))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="member-2", is_owner=False))
        with pytest.raises(HTTPException) as exc_info:
            await workspace_service.remove_member("ws-1", "member-2", "member-1")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_member_can_remove_themselves(
        self, workspace_service, workspace_repo, member_repo
    ):
        """Self-removal is always allowed regardless of role."""
        workspace_repo.seed(make_workspace(id="ws-1"))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="owner-1", is_owner=True))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="member-1", is_owner=False))
        await workspace_service.remove_member("ws-1", "member-1", "member-1")
        assert await member_repo.get_by_workspace_and_user("ws-1", "member-1") is None

    @pytest.mark.asyncio
    async def test_target_not_found_raises_404(self, workspace_service, workspace_repo, member_repo):
        workspace_repo.seed(make_workspace(id="ws-1"))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="owner-1", is_owner=True))
        with pytest.raises(HTTPException) as exc_info:
            await workspace_service.remove_member("ws-1", "ghost", "owner-1")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_removing_last_owner_raises_400(self, workspace_service, workspace_repo, member_repo):
        workspace_repo.seed(make_workspace(id="ws-1"))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="owner-1", is_owner=True))
        with pytest.raises(HTTPException) as exc_info:
            await workspace_service.remove_member("ws-1", "owner-1", "owner-1")
        assert exc_info.value.status_code == 400
        assert "last owner" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_owner_can_remove_second_owner(self, workspace_service, workspace_repo, member_repo):
        workspace_repo.seed(make_workspace(id="ws-1"))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="owner-1", is_owner=True))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="owner-2", is_owner=True))
        await workspace_service.remove_member("ws-1", "owner-2", "owner-1")
        assert await member_repo.get_by_workspace_and_user("ws-1", "owner-2") is None

    @pytest.mark.asyncio
    async def test_cascade_removes_project_membership(
        self,
        workspace_service,
        workspace_repo,
        member_repo,
        project_repo,
        project_member_repo,
    ):
        """Fix #5: removing a workspace member must also remove their project memberships."""
        workspace_repo.seed(make_workspace(id="ws-1"))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="owner-1", is_owner=True))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="user-1"))

        project = _make_project("ws-1", "proj-1")
        project_repo.seed(project)
        pm = _make_project_member("proj-1", "user-1")
        project_member_repo.seed(pm)

        await workspace_service.remove_member("ws-1", "user-1", "owner-1")

        assert await project_member_repo.get_by_project_and_user("proj-1", "user-1") is None

    @pytest.mark.asyncio
    async def test_cascade_removes_channel_membership(
        self,
        workspace_service,
        workspace_repo,
        member_repo,
        project_repo,
        project_member_repo,
        channel_repo,
        channel_member_repo,
    ):
        """Fix #5: removing a workspace member must also remove their channel memberships."""
        workspace_repo.seed(make_workspace(id="ws-1"))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="owner-1", is_owner=True))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="user-1"))

        project = _make_project("ws-1", "proj-1")
        project_repo.seed(project)
        pm = _make_project_member("proj-1", "user-1")
        project_member_repo.seed(pm)

        channel = _make_channel("proj-1", "chan-1")
        channel_repo.seed(channel)
        cm = _make_channel_member("chan-1", "user-1")
        channel_member_repo.seed(cm)

        await workspace_service.remove_member("ws-1", "user-1", "owner-1")

        assert await channel_member_repo.get_by_channel_and_user("chan-1", "user-1") is None
        assert await project_member_repo.get_by_project_and_user("proj-1", "user-1") is None

    @pytest.mark.asyncio
    async def test_commits_uow(self, workspace_service, workspace_repo, member_repo, fake_uow):
        workspace_repo.seed(make_workspace(id="ws-1"))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="owner-1", is_owner=True))
        member_repo.seed(make_workspace_member(workspace_id="ws-1", user_id="member-1", is_owner=False))
        await workspace_service.remove_member("ws-1", "member-1", "owner-1")
        assert fake_uow.committed is True