from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.channel.models import ChannelMemberRole
from app.project.models import ProjectRole
from app.workspace.models import WorkspaceMember

from .models import InboxItem, InboxItemStatus, InboxItemType
from .schemas import InboxItemRead
from .uow import AbstractInboxUnitOfWork

# Invite TTLs per scope (design spec: 30 days workspace, 7 days project/channel)
_TTL: dict[InboxItemType, int] = {
    InboxItemType.workspace_invite: 30,
    InboxItemType.project_invite: 7,
    InboxItemType.channel_invite: 7,
}

# Roles that are project-scoped only and must never get channel membership.
_CHANNEL_INELIGIBLE_ROLES = {ProjectRole.advisor, ProjectRole.viewer}


class InboxService:
    def __init__(self, uow: AbstractInboxUnitOfWork) -> None:
        self.uow = uow

    # ------------------------------------------------------------------ #
    # Read                                                                 #
    # ------------------------------------------------------------------ #

    async def list_inbox(self, user_id: str) -> list[InboxItemRead]:
        """
        Return all inbox items for the authenticated user.
        Pending invites are lazily marked expired if their TTL has passed.
        """
        async with self.uow:
            items = await self.uow.inbox_items.list_by_user(user_id)
            now = datetime.now(timezone.utc)
            for item in items:
                if (
                    item.status == InboxItemStatus.pending
                    and item.expires_at is not None
                    and item.expires_at < now
                ):
                    await self.uow.inbox_items.expire_stale(item)
            await self.uow.commit()
            return [InboxItemRead.model_validate(i) for i in items]

    # ------------------------------------------------------------------ #
    # Send invites                                                         #
    # ------------------------------------------------------------------ #

    async def send_workspace_invite(
        self,
        workspace_id: str,
        target_user_id: str,
        role: str,
        sender_id: str,
    ) -> InboxItemRead:
        """
        Only workspace owners may send workspace invites.
        Target must be a registered platform user who is not already a member.
        """
        async with self.uow:
            workspace = await self._require_workspace(workspace_id)
            await self._require_owner(workspace_id, sender_id)

            target = await self.uow.users.get_by_id(target_user_id)
            if target is None:
                raise HTTPException(status_code=404, detail="Target user not found.")

            existing_member = await self.uow.workspace_members.get_by_workspace_and_user(
                workspace_id, target_user_id
            )
            if existing_member is not None:
                raise HTTPException(
                    status_code=409,
                    detail="User is already a member of this workspace.",
                )

            await self._guard_duplicate_invite(
                target_user_id, workspace_id=workspace_id
            )

            item = await self.uow.inbox_items.create(
                user_id=target_user_id,
                type=InboxItemType.workspace_invite,
                status=InboxItemStatus.pending,
                sender_id=sender_id,
                workspace_id=workspace_id,
                role=role,
                title=f"You've been invited to join the workspace \"{workspace.name}\"",
                body=f"You'll join as {role}.",
                expires_at=self._expiry(InboxItemType.workspace_invite),
            )
            await self.uow.commit()
            return InboxItemRead.model_validate(item)

    async def send_project_invite(
        self,
        project_id: str,
        target_user_id: str,
        role: str,
        sender_id: str,
    ) -> InboxItemRead:
        """
        Team leads and workspace owners may send project invites.
        Target must already be a workspace member.
        Advisors and viewers are accepted roles (project-scoped, no channel assignment).
        """
        async with self.uow:
            project = await self._require_project(project_id)
            await self._require_team_lead_or_owner(project, sender_id)

            # Target must already be in the workspace
            ws_member = await self.uow.workspace_members.get_by_workspace_and_user(
                project.workspace_id, target_user_id
            )
            if ws_member is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "The user must be a workspace member before they can be invited "
                        "to a project. Invite them to the workspace first."
                    ),
                )

            existing = await self.uow.project_members.get_by_project_and_user(
                project_id, target_user_id
            )
            if existing is not None:
                raise HTTPException(
                    status_code=409,
                    detail="User is already a member of this project.",
                )

            await self._guard_duplicate_invite(
                target_user_id, project_id=project_id
            )

            item = await self.uow.inbox_items.create(
                user_id=target_user_id,
                type=InboxItemType.project_invite,
                status=InboxItemStatus.pending,
                sender_id=sender_id,
                workspace_id=project.workspace_id,
                project_id=project_id,
                role=role,
                title=f"You've been invited to join the project \"{project.name}\"",
                body=f"You'll join as {role}.",
                expires_at=self._expiry(InboxItemType.project_invite),
            )
            await self.uow.commit()
            return InboxItemRead.model_validate(item)

    async def send_channel_invite(
        self,
        channel_id: str,
        target_user_id: str,
        role: str,
        sender_id: str,
    ) -> InboxItemRead:
        """
        Channel leads, team leads, and workspace owners may send channel invites.
        Target must already be a project member.
        Advisors and viewers may NOT receive channel invites — their access is
        governed by their project role and they never need channel membership.
        """
        async with self.uow:
            channel = await self._require_channel(channel_id)

            if channel.is_leads_channel:
                raise HTTPException(
                    status_code=400,
                    detail="Members cannot be invited to the leads channel.",
                )

            project = await self._require_project(channel.project_id)
            await self._require_channel_lead_or_team_lead_or_owner(
                channel, project, sender_id
            )

            # Target must already be a project member
            target_pm = await self.uow.project_members.get_by_project_and_user(
                channel.project_id, target_user_id
            )
            if target_pm is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "The user must be a project member before they can be invited "
                        "to a channel. Add them to the project first."
                    ),
                )

            # Fix #6: advisors and viewers are project-scoped roles only
            if target_pm.role in _CHANNEL_INELIGIBLE_ROLES:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Users with the '{target_pm.role}' role are project-scoped "
                        "and cannot be assigned to channels. Their access is governed "
                        "by their project role."
                    ),
                )

            existing = await self.uow.channel_members.get_by_channel_and_user(
                channel_id, target_user_id
            )
            if existing is not None:
                raise HTTPException(
                    status_code=409,
                    detail="User is already a member of this channel.",
                )

            await self._guard_duplicate_invite(
                target_user_id, channel_id=channel_id
            )

            item = await self.uow.inbox_items.create(
                user_id=target_user_id,
                type=InboxItemType.channel_invite,
                status=InboxItemStatus.pending,
                sender_id=sender_id,
                workspace_id=project.workspace_id,
                project_id=channel.project_id,
                channel_id=channel_id,
                role=role,
                title=f"You've been invited to join the channel \"{channel.name}\"",
                body=f"You'll join as {role}.",
                expires_at=self._expiry(InboxItemType.channel_invite),
            )
            await self.uow.commit()
            return InboxItemRead.model_validate(item)

    # ------------------------------------------------------------------ #
    # Accept / decline                                                     #
    # ------------------------------------------------------------------ #

    async def accept_invite(self, item_id: str, user_id: str) -> InboxItemRead:
        async with self.uow:
            item = await self._require_invite_item(item_id, user_id)

            if item.type == InboxItemType.workspace_invite:
                await self._accept_workspace_invite(item)
            elif item.type == InboxItemType.project_invite:
                await self._accept_project_invite(item)
            elif item.type == InboxItemType.channel_invite:
                await self._accept_channel_invite(item)

            item = await self.uow.inbox_items.update(
                item, status=InboxItemStatus.accepted
            )
            await self.uow.commit()
            return InboxItemRead.model_validate(item)

    async def decline_invite(self, item_id: str, user_id: str) -> InboxItemRead:
        async with self.uow:
            item = await self._require_invite_item(item_id, user_id)
            item = await self.uow.inbox_items.update(
                item, status=InboxItemStatus.declined
            )
            await self.uow.commit()
            return InboxItemRead.model_validate(item)

    # ------------------------------------------------------------------ #
    # Mark read                                                            #
    # ------------------------------------------------------------------ #

    async def mark_read(self, item_id: str, user_id: str) -> InboxItemRead:
        async with self.uow:
            item = await self.uow.inbox_items.get_by_id(item_id)
            if item is None or item.user_id != user_id:
                raise HTTPException(status_code=404, detail="Inbox item not found.")
            if item.status == InboxItemStatus.unread:
                item = await self.uow.inbox_items.update(
                    item, status=InboxItemStatus.read
                )
                await self.uow.commit()
            return InboxItemRead.model_validate(item)

    # ------------------------------------------------------------------ #
    # Internal notification helper (called from other services via        #
    # InboxItemRepository directly inside their own UoW transaction)      #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def create_notification(
        inbox_repo,
        *,
        user_id: str,
        title: str,
        body: str | None = None,
        sender_id: str | None = None,
        workspace_id: str | None = None,
        project_id: str | None = None,
        channel_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> InboxItem:
        """
        Lightweight static helper so other services (project, workspace, etc.)
        can insert a notification row inside their own UoW transaction without
        instantiating InboxService. Caller is responsible for commit.

        Usage (inside project service after creating project):
            await InboxService.create_notification(
                self.uow.inbox_items,
                user_id=owner.user_id,
                title="New project created: ...",
                ...
            )
        """
        return await inbox_repo.create(
            user_id=user_id,
            type=InboxItemType.notification,
            status=InboxItemStatus.unread,
            sender_id=sender_id,
            workspace_id=workspace_id,
            project_id=project_id,
            channel_id=channel_id,
            title=title,
            body=body,
            entity_type=entity_type,
            entity_id=entity_id,
        )

    # ------------------------------------------------------------------ #
    # Accept helpers (one per invite type)                                 #
    # ------------------------------------------------------------------ #

    async def _accept_workspace_invite(self, item: InboxItem) -> None:
        if item.workspace_id is None:
            raise HTTPException(
                status_code=400,
                detail="This invite is no longer valid (workspace was removed).",
            )
        existing = await self.uow.workspace_members.get_by_workspace_and_user(
            item.workspace_id, item.user_id
        )
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail="You are already a member of this workspace.",
            )
        await self.uow.workspace_members.create(
            workspace_id=item.workspace_id,
            user_id=item.user_id,
            is_owner=(item.role == "owner"),
        )

    async def _accept_project_invite(self, item: InboxItem) -> None:
        if item.project_id is None:
            raise HTTPException(
                status_code=400,
                detail="This invite is no longer valid (project was removed).",
            )
        # Re-verify workspace membership at acceptance time
        if item.workspace_id is not None:
            ws_member = await self.uow.workspace_members.get_by_workspace_and_user(
                item.workspace_id, item.user_id
            )
            if ws_member is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "You must be a workspace member to join this project. "
                        "Accept the workspace invite first."
                    ),
                )
        existing = await self.uow.project_members.get_by_project_and_user(
            item.project_id, item.user_id
        )
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail="You are already a member of this project.",
            )
        await self.uow.project_members.create(
            project_id=item.project_id,
            user_id=item.user_id,
            role=item.role,
        )

    async def _accept_channel_invite(self, item: InboxItem) -> None:
        if item.channel_id is None:
            raise HTTPException(
                status_code=400,
                detail="This invite is no longer valid (channel was removed).",
            )
        # Re-verify project membership and role at acceptance time
        if item.project_id is not None:
            pm = await self.uow.project_members.get_by_project_and_user(
                item.project_id, item.user_id
            )
            if pm is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "You must be a project member to join this channel. "
                        "Accept the project invite first."
                    ),
                )
            # Fix #6 at acceptance time as well
            if pm.role in _CHANNEL_INELIGIBLE_ROLES:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Users with the '{pm.role}' role cannot be assigned "
                        "to channels."
                    ),
                )
        existing = await self.uow.channel_members.get_by_channel_and_user(
            item.channel_id, item.user_id
        )
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail="You are already a member of this channel.",
            )
        await self.uow.channel_members.create(
            channel_id=item.channel_id,
            user_id=item.user_id,
            role=item.role,
        )

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    async def _require_invite_item(self, item_id: str, user_id: str) -> InboxItem:
        item = await self.uow.inbox_items.get_by_id(item_id)
        if item is None or item.user_id != user_id:
            raise HTTPException(status_code=404, detail="Inbox item not found.")
        if item.type == InboxItemType.notification:
            raise HTTPException(
                status_code=400,
                detail="Notifications cannot be accepted or declined.",
            )
        if item.status != InboxItemStatus.pending:
            raise HTTPException(
                status_code=400,
                detail=f"Invite has already been {item.status}.",
            )
        if item.expires_at and item.expires_at < datetime.now(timezone.utc):
            await self.uow.inbox_items.expire_stale(item)
            raise HTTPException(status_code=400, detail="Invite has expired.")
        return item

    async def _guard_duplicate_invite(
        self,
        target_user_id: str,
        workspace_id: str | None = None,
        project_id: str | None = None,
        channel_id: str | None = None,
    ) -> None:
        existing = await self.uow.inbox_items.list_pending_invites_for_target(
            target_user_id,
            workspace_id=workspace_id,
            project_id=project_id,
            channel_id=channel_id,
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail="A pending invite for this user already exists.",
            )

    async def _require_workspace(self, workspace_id: str):
        workspace = await self.uow.workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found.")
        return workspace

    async def _require_project(self, project_id: str):
        project = await self.uow.projects.get_by_id(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        return project

    async def _require_channel(self, channel_id: str):
        channel = await self.uow.channels.get_by_id(channel_id)
        if channel is None:
            raise HTTPException(status_code=404, detail="Channel not found.")
        return channel

    async def _require_owner(self, workspace_id: str, user_id: str):
        member = await self.uow.workspace_members.get_by_workspace_and_user(
            workspace_id, user_id
        )
        if member is None or not member.is_owner:
            raise HTTPException(
                status_code=403,
                detail="Only workspace owners can send workspace invites.",
            )
        return member

    async def _require_team_lead_or_owner(self, project, requester_id: str):
        ws_member = await self.uow.workspace_members.get_by_workspace_and_user(
            project.workspace_id, requester_id
        )
        if ws_member and ws_member.is_owner:
            return ws_member
        pm = await self.uow.project_members.get_by_project_and_user(
            project.id, requester_id
        )
        if pm is None or pm.role != "team_lead":
            raise HTTPException(
                status_code=403,
                detail="Only Team Leads (or workspace owners) can send project invites.",
            )
        return pm

    async def _require_channel_lead_or_team_lead_or_owner(
        self, channel, project, requester_id: str
    ):
        ws_member = await self.uow.workspace_members.get_by_workspace_and_user(
            project.workspace_id, requester_id
        )
        if ws_member and ws_member.is_owner:
            return ws_member

        pm = await self.uow.project_members.get_by_project_and_user(
            project.id, requester_id
        )
        if pm and pm.role == "team_lead":
            return pm

        cm = await self.uow.channel_members.get_by_channel_and_user(
            channel.id, requester_id
        )
        if cm and cm.role == ChannelMemberRole.channel_lead:
            return cm

        raise HTTPException(
            status_code=403,
            detail="Only Channel Leads, Team Leads, or workspace owners can send channel invites.",
        )

    @staticmethod
    def _expiry(item_type: InboxItemType) -> datetime:
        return datetime.now(timezone.utc) + timedelta(days=_TTL[item_type])