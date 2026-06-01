"""
Unit tests for app.inbox.service.InboxService
──────────────────────────────────────────────
Coverage:
  list_inbox            — happy path, lazy expire of stale invites
  send_workspace_invite — happy path, non-owner blocked, target not found,
                          target already a member, duplicate invite blocked
  send_project_invite   — happy path, target not in workspace blocked (Fix #1),
                          non-lead blocked, target already a project member,
                          duplicate invite blocked
  send_channel_invite   — happy path, target not in project blocked,
                          advisor blocked (Fix #6), viewer blocked (Fix #6),
                          leads channel blocked, non-lead blocked,
                          duplicate invite blocked
  accept_invite         — workspace invite creates membership,
                          project invite verifies workspace membership at
                          acceptance time (Fix #1),
                          channel invite verifies project membership,
                          advisor cannot accept channel invite (Fix #6),
                          expired invite rejected, already accepted rejected,
                          notification items cannot be accepted
  decline_invite        — happy path, non-pending blocked
  mark_read             — unread → read, idempotent on already-read
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.inbox.models import InboxItemStatus, InboxItemType
from app.project.models import ProjectRole

from .conftest import (
    make_channel,
    make_channel_member,
    make_item,
    make_project,
    make_project_member,
    make_user,
    make_ws_member,
)


def _seed_workspace(ws_repo, ws_member_repo, workspace_id="ws-1", owner_id="owner-1"):
    ws = make_project("_", workspace_id)  # reuse make_project — same shape
    ws.id = workspace_id
    ws.name = "Test WS"
    ws_repo.seed(ws)
    ws_member_repo.seed(make_ws_member(workspace_id, owner_id, is_owner=True))
    return ws


def _seed_project(project_repo, project_member_repo, workspace_id="ws-1", project_id="proj-1", lead_id="lead-1"):
    project = make_project(workspace_id, project_id)
    project_repo.seed(project)
    project_member_repo.seed(make_project_member(project_id, lead_id, role="team_lead"))
    return project


def _seed_channel(channel_repo, project_id="proj-1", channel_id="chan-1", is_leads=False):
    channel = make_channel(project_id, channel_id, is_leads_channel=is_leads)
    channel_repo.seed(channel)
    return channel


# ════════════════════════════════════════════════════════════════════════════
# list_inbox
# ════════════════════════════════════════════════════════════════════════════


class TestListInbox:
    @pytest.mark.asyncio
    async def test_returns_items_for_user(self, inbox_service, inbox_repo):
        inbox_repo.seed(make_item(id="item-1", user_id="user-1"))
        inbox_repo.seed(make_item(id="item-2", user_id="user-2"))
        result = await inbox_service.list_inbox("user-1")
        assert len(result) == 1
        assert result[0].id == "item-1"

    @pytest.mark.asyncio
    async def test_expired_pending_invite_is_lazily_marked(self, inbox_service, inbox_repo, fake_uow):
        item = make_item(
            id="item-stale",
            user_id="user-1",
            status=InboxItemStatus.pending,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        inbox_repo.seed(item)
        await inbox_service.list_inbox("user-1")
        assert item.status == InboxItemStatus.expired
        assert fake_uow.committed is True

    @pytest.mark.asyncio
    async def test_non_expired_item_not_touched(self, inbox_service, inbox_repo, fake_uow):
        item = make_item(
            id="item-ok",
            user_id="user-1",
            status=InboxItemStatus.pending,
            expires_at=datetime.now(timezone.utc) + timedelta(days=5),
        )
        inbox_repo.seed(item)
        await inbox_service.list_inbox("user-1")
        assert item.status == InboxItemStatus.pending


# ════════════════════════════════════════════════════════════════════════════
# send_workspace_invite
# ════════════════════════════════════════════════════════════════════════════


class TestSendWorkspaceInvite:
    @pytest.mark.asyncio
    async def test_owner_sends_invite_to_platform_user(
        self, inbox_service, ws_repo, ws_member_repo, user_repo, inbox_repo
    ):
        _seed_workspace(ws_repo, ws_member_repo, "ws-1", "owner-1")
        user_repo.seed(make_user("target-1"))

        result = await inbox_service.send_workspace_invite("ws-1", "target-1", "member", "owner-1")

        assert result.type == InboxItemType.workspace_invite
        assert result.user_id == "target-1"
        assert result.role == "member"
        assert result.workspace_id == "ws-1"
        assert result.expires_at is not None

    @pytest.mark.asyncio
    async def test_non_owner_raises_403(
        self, inbox_service, ws_repo, ws_member_repo, user_repo
    ):
        _seed_workspace(ws_repo, ws_member_repo, "ws-1", "owner-1")
        ws_member_repo.seed(make_ws_member("ws-1", "member-1", is_owner=False))
        user_repo.seed(make_user("target-1"))

        with pytest.raises(HTTPException) as exc_info:
            await inbox_service.send_workspace_invite("ws-1", "target-1", "member", "member-1")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_target_not_found_raises_404(
        self, inbox_service, ws_repo, ws_member_repo
    ):
        _seed_workspace(ws_repo, ws_member_repo, "ws-1", "owner-1")

        with pytest.raises(HTTPException) as exc_info:
            await inbox_service.send_workspace_invite("ws-1", "ghost", "member", "owner-1")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_target_already_member_raises_409(
        self, inbox_service, ws_repo, ws_member_repo, user_repo
    ):
        _seed_workspace(ws_repo, ws_member_repo, "ws-1", "owner-1")
        user_repo.seed(make_user("existing"))
        ws_member_repo.seed(make_ws_member("ws-1", "existing"))

        with pytest.raises(HTTPException) as exc_info:
            await inbox_service.send_workspace_invite("ws-1", "existing", "member", "owner-1")
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_duplicate_pending_invite_raises_409(
        self, inbox_service, ws_repo, ws_member_repo, user_repo, inbox_repo
    ):
        _seed_workspace(ws_repo, ws_member_repo, "ws-1", "owner-1")
        user_repo.seed(make_user("target-1"))
        inbox_repo.seed(make_item(
            user_id="target-1",
            type=InboxItemType.workspace_invite,
            status=InboxItemStatus.pending,
            workspace_id="ws-1",
        ))

        with pytest.raises(HTTPException) as exc_info:
            await inbox_service.send_workspace_invite("ws-1", "target-1", "member", "owner-1")
        assert exc_info.value.status_code == 409


# ════════════════════════════════════════════════════════════════════════════
# send_project_invite  (Fix #1: target must be workspace member)
# ════════════════════════════════════════════════════════════════════════════


class TestSendProjectInvite:
    @pytest.mark.asyncio
    async def test_team_lead_sends_project_invite(
        self, inbox_service, ws_repo, ws_member_repo, project_repo, project_member_repo
    ):
        _seed_workspace(ws_repo, ws_member_repo, "ws-1", "owner-1")
        ws_member_repo.seed(make_ws_member("ws-1", "lead-1"))
        ws_member_repo.seed(make_ws_member("ws-1", "target-1"))
        _seed_project(project_repo, project_member_repo, "ws-1", "proj-1", "lead-1")

        result = await inbox_service.send_project_invite("proj-1", "target-1", "member", "lead-1")

        assert result.type == InboxItemType.project_invite
        assert result.user_id == "target-1"
        assert result.project_id == "proj-1"

    @pytest.mark.asyncio
    async def test_target_not_workspace_member_raises_400(
        self, inbox_service, ws_repo, ws_member_repo, project_repo, project_member_repo
    ):
        """Fix #1: cannot invite to project without workspace membership."""
        _seed_workspace(ws_repo, ws_member_repo, "ws-1", "owner-1")
        ws_member_repo.seed(make_ws_member("ws-1", "lead-1"))
        # target is NOT a workspace member
        _seed_project(project_repo, project_member_repo, "ws-1", "proj-1", "lead-1")

        with pytest.raises(HTTPException) as exc_info:
            await inbox_service.send_project_invite("proj-1", "outside-user", "member", "lead-1")
        assert exc_info.value.status_code == 400
        assert "workspace member" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_non_lead_raises_403(
        self, inbox_service, ws_repo, ws_member_repo, project_repo, project_member_repo
    ):
        _seed_workspace(ws_repo, ws_member_repo, "ws-1", "owner-1")
        ws_member_repo.seed(make_ws_member("ws-1", "regular-1"))
        ws_member_repo.seed(make_ws_member("ws-1", "target-1"))
        project = _seed_project(project_repo, project_member_repo, "ws-1", "proj-1", "lead-1")
        project_member_repo.seed(make_project_member("proj-1", "regular-1", role="member"))

        with pytest.raises(HTTPException) as exc_info:
            await inbox_service.send_project_invite("proj-1", "target-1", "member", "regular-1")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_target_already_project_member_raises_409(
        self, inbox_service, ws_repo, ws_member_repo, project_repo, project_member_repo
    ):
        _seed_workspace(ws_repo, ws_member_repo, "ws-1", "owner-1")
        ws_member_repo.seed(make_ws_member("ws-1", "lead-1"))
        ws_member_repo.seed(make_ws_member("ws-1", "existing-1"))
        _seed_project(project_repo, project_member_repo, "ws-1", "proj-1", "lead-1")
        project_member_repo.seed(make_project_member("proj-1", "existing-1"))

        with pytest.raises(HTTPException) as exc_info:
            await inbox_service.send_project_invite("proj-1", "existing-1", "member", "lead-1")
        assert exc_info.value.status_code == 409


# ════════════════════════════════════════════════════════════════════════════
# send_channel_invite  (Fix #6: advisor/viewer blocked)
# ════════════════════════════════════════════════════════════════════════════


class TestSendChannelInvite:
    def _setup(
        self, ws_repo, ws_member_repo, project_repo, project_member_repo, channel_repo,
        target_role="member"
    ):
        _seed_workspace(ws_repo, ws_member_repo, "ws-1", "owner-1")
        ws_member_repo.seed(make_ws_member("ws-1", "lead-1"))
        _seed_project(project_repo, project_member_repo, "ws-1", "proj-1", "lead-1")
        project_member_repo.seed(make_project_member("proj-1", "target-1", role=target_role))
        _seed_channel(channel_repo, "proj-1", "chan-1")

    @pytest.mark.asyncio
    async def test_team_lead_sends_channel_invite(
        self, inbox_service, ws_repo, ws_member_repo, project_repo, project_member_repo, channel_repo
    ):
        self._setup(ws_repo, ws_member_repo, project_repo, project_member_repo, channel_repo)
        result = await inbox_service.send_channel_invite("chan-1", "target-1", "member", "lead-1")
        assert result.type == InboxItemType.channel_invite
        assert result.channel_id == "chan-1"

    @pytest.mark.asyncio
    async def test_advisor_cannot_receive_channel_invite(
        self, inbox_service, ws_repo, ws_member_repo, project_repo, project_member_repo, channel_repo
    ):
        """Fix #6: advisors are project-scoped, channel membership is invalid."""
        self._setup(ws_repo, ws_member_repo, project_repo, project_member_repo, channel_repo, target_role="advisor")

        with pytest.raises(HTTPException) as exc_info:
            await inbox_service.send_channel_invite("chan-1", "target-1", "member", "lead-1")
        assert exc_info.value.status_code == 400
        assert "advisor" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_viewer_cannot_receive_channel_invite(
        self, inbox_service, ws_repo, ws_member_repo, project_repo, project_member_repo, channel_repo
    ):
        """Fix #6: viewers are strictly read-only, channel membership is invalid."""
        self._setup(ws_repo, ws_member_repo, project_repo, project_member_repo, channel_repo, target_role="viewer")

        with pytest.raises(HTTPException) as exc_info:
            await inbox_service.send_channel_invite("chan-1", "target-1", "member", "lead-1")
        assert exc_info.value.status_code == 400
        assert "viewer" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_leads_channel_invite_blocked(
        self, inbox_service, ws_repo, ws_member_repo, project_repo, project_member_repo, channel_repo
    ):
        self._setup(ws_repo, ws_member_repo, project_repo, project_member_repo, channel_repo)
        _seed_channel(channel_repo, "proj-1", "leads-chan", is_leads=True)

        with pytest.raises(HTTPException) as exc_info:
            await inbox_service.send_channel_invite("leads-chan", "target-1", "member", "lead-1")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_target_not_in_project_raises_400(
        self, inbox_service, ws_repo, ws_member_repo, project_repo, project_member_repo, channel_repo
    ):
        _seed_workspace(ws_repo, ws_member_repo, "ws-1", "owner-1")
        ws_member_repo.seed(make_ws_member("ws-1", "lead-1"))
        _seed_project(project_repo, project_member_repo, "ws-1", "proj-1", "lead-1")
        _seed_channel(channel_repo, "proj-1", "chan-1")
        # target-1 is NOT a project member

        with pytest.raises(HTTPException) as exc_info:
            await inbox_service.send_channel_invite("chan-1", "target-1", "member", "lead-1")
        assert exc_info.value.status_code == 400
        assert "project member" in exc_info.value.detail


# ════════════════════════════════════════════════════════════════════════════
# accept_invite
# ════════════════════════════════════════════════════════════════════════════


class TestAcceptInvite:
    @pytest.mark.asyncio
    async def test_workspace_invite_creates_membership(
        self, inbox_service, inbox_repo, ws_repo, ws_member_repo
    ):
        ws = make_project("_", "ws-1")
        ws.id = "ws-1"
        ws_repo.seed(ws)
        item = make_item(
            id="inv-1",
            user_id="user-1",
            type=InboxItemType.workspace_invite,
            status=InboxItemStatus.pending,
            workspace_id="ws-1",
            role="member",
        )
        inbox_repo.seed(item)

        result = await inbox_service.accept_invite("inv-1", "user-1")

        assert result.status == InboxItemStatus.accepted
        member = await ws_member_repo.get_by_workspace_and_user("ws-1", "user-1")
        assert member is not None
        assert member.is_owner is False

    @pytest.mark.asyncio
    async def test_project_invite_requires_workspace_membership_at_acceptance(
        self, inbox_service, inbox_repo, ws_member_repo, project_repo, project_member_repo
    ):
        """Fix #1: workspace check is re-validated at acceptance time."""
        project = make_project("ws-1", "proj-1")
        project_repo.seed(project)
        item = make_item(
            id="inv-1",
            user_id="user-1",
            type=InboxItemType.project_invite,
            status=InboxItemStatus.pending,
            workspace_id="ws-1",
            project_id="proj-1",
            role="member",
        )
        inbox_repo.seed(item)
        # user-1 is NOT a workspace member at acceptance time

        with pytest.raises(HTTPException) as exc_info:
            await inbox_service.accept_invite("inv-1", "user-1")
        assert exc_info.value.status_code == 400
        assert "workspace" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_project_invite_accepted_creates_project_member(
        self, inbox_service, inbox_repo, ws_member_repo, project_repo, project_member_repo
    ):
        project = make_project("ws-1", "proj-1")
        project_repo.seed(project)
        ws_member_repo.seed(make_ws_member("ws-1", "user-1"))
        item = make_item(
            id="inv-1",
            user_id="user-1",
            type=InboxItemType.project_invite,
            status=InboxItemStatus.pending,
            workspace_id="ws-1",
            project_id="proj-1",
            role="member",
        )
        inbox_repo.seed(item)

        result = await inbox_service.accept_invite("inv-1", "user-1")

        assert result.status == InboxItemStatus.accepted
        pm = await project_member_repo.get_by_project_and_user("proj-1", "user-1")
        assert pm is not None

    @pytest.mark.asyncio
    async def test_channel_invite_advisor_blocked_at_acceptance(
        self, inbox_service, inbox_repo, ws_member_repo, project_member_repo, channel_repo
    ):
        """Fix #6: even if an invite somehow exists, advisor is blocked at acceptance."""
        ws_member_repo.seed(make_ws_member("ws-1", "user-1"))
        project_member_repo.seed(make_project_member("proj-1", "user-1", role="advisor"))
        _seed_channel(channel_repo, "proj-1", "chan-1")
        item = make_item(
            id="inv-1",
            user_id="user-1",
            type=InboxItemType.channel_invite,
            status=InboxItemStatus.pending,
            project_id="proj-1",
            channel_id="chan-1",
            role="member",
        )
        inbox_repo.seed(item)

        with pytest.raises(HTTPException) as exc_info:
            await inbox_service.accept_invite("inv-1", "user-1")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_expired_invite_raises_400(self, inbox_service, inbox_repo):
        item = make_item(
            id="inv-expired",
            user_id="user-1",
            type=InboxItemType.workspace_invite,
            status=InboxItemStatus.pending,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        inbox_repo.seed(item)

        with pytest.raises(HTTPException) as exc_info:
            await inbox_service.accept_invite("inv-expired", "user-1")
        assert exc_info.value.status_code == 400
        assert "expired" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_already_accepted_invite_raises_400(self, inbox_service, inbox_repo):
        item = make_item(
            id="inv-done",
            user_id="user-1",
            type=InboxItemType.workspace_invite,
            status=InboxItemStatus.accepted,
        )
        inbox_repo.seed(item)

        with pytest.raises(HTTPException) as exc_info:
            await inbox_service.accept_invite("inv-done", "user-1")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_notification_cannot_be_accepted(self, inbox_service, inbox_repo):
        item = make_item(
            id="notif-1",
            user_id="user-1",
            type=InboxItemType.notification,
            status=InboxItemStatus.unread,
            expires_at=None,
        )
        inbox_repo.seed(item)

        with pytest.raises(HTTPException) as exc_info:
            await inbox_service.accept_invite("notif-1", "user-1")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_wrong_user_cannot_accept(self, inbox_service, inbox_repo):
        item = make_item(id="inv-1", user_id="user-1")
        inbox_repo.seed(item)

        with pytest.raises(HTTPException) as exc_info:
            await inbox_service.accept_invite("inv-1", "other-user")
        assert exc_info.value.status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# decline_invite
# ════════════════════════════════════════════════════════════════════════════


class TestDeclineInvite:
    @pytest.mark.asyncio
    async def test_pending_invite_can_be_declined(self, inbox_service, inbox_repo):
        item = make_item(id="inv-1", user_id="user-1", status=InboxItemStatus.pending)
        inbox_repo.seed(item)

        result = await inbox_service.decline_invite("inv-1", "user-1")
        assert result.status == InboxItemStatus.declined

    @pytest.mark.asyncio
    async def test_already_accepted_cannot_be_declined(self, inbox_service, inbox_repo):
        item = make_item(id="inv-1", user_id="user-1", status=InboxItemStatus.accepted)
        inbox_repo.seed(item)

        with pytest.raises(HTTPException) as exc_info:
            await inbox_service.decline_invite("inv-1", "user-1")
        assert exc_info.value.status_code == 400


# ════════════════════════════════════════════════════════════════════════════
# mark_read
# ════════════════════════════════════════════════════════════════════════════


class TestMarkRead:
    @pytest.mark.asyncio
    async def test_unread_notification_becomes_read(self, inbox_service, inbox_repo):
        item = make_item(
            id="notif-1",
            user_id="user-1",
            type=InboxItemType.notification,
            status=InboxItemStatus.unread,
            expires_at=None,
        )
        inbox_repo.seed(item)

        result = await inbox_service.mark_read("notif-1", "user-1")
        assert result.status == InboxItemStatus.read

    @pytest.mark.asyncio
    async def test_already_read_is_idempotent(self, inbox_service, inbox_repo):
        item = make_item(
            id="notif-1",
            user_id="user-1",
            type=InboxItemType.notification,
            status=InboxItemStatus.read,
            expires_at=None,
        )
        inbox_repo.seed(item)

        result = await inbox_service.mark_read("notif-1", "user-1")
        assert result.status == InboxItemStatus.read

    @pytest.mark.asyncio
    async def test_wrong_user_raises_404(self, inbox_service, inbox_repo):
        item = make_item(id="notif-1", user_id="user-1", expires_at=None)
        inbox_repo.seed(item)

        with pytest.raises(HTTPException) as exc_info:
            await inbox_service.mark_read("notif-1", "other-user")
        assert exc_info.value.status_code == 404