from fastapi import HTTPException
from app.auth.schemas import UserRead
from app.project.models import ProjectRole

from .models import ApprovalPolicy, ChannelMemberRole
from .schemas import (
    ChannelCreate,
    ChannelMemberAdd,
    ChannelMemberRead,
    ChannelMemberUpdate,
    ChannelRead,
    ChannelUpdate,
)
from .uow import AbstractChannelUnitOfWork

# Roles that are project-scoped only and must never get channel membership.
_CHANNEL_INELIGIBLE_ROLES = {ProjectRole.advisor, ProjectRole.viewer}


class ChannelService:
    def __init__(self, uow: AbstractChannelUnitOfWork) -> None:
        self.uow = uow

    # ------------------------------------------------------------------ #
    # Channel CRUD                                                         #
    # ------------------------------------------------------------------ #

    async def create_channel(
        self, project_id: str, requester_id: str, data: ChannelCreate
    ) -> ChannelRead:
        async with self.uow:
            project = await self._require_project(project_id)
            await self._require_team_lead_or_owner(project, requester_id)

            existing_channels = await self.uow.channels.list_by_project(project_id)
            if any(c.discipline == data.discipline for c in existing_channels):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"A channel for discipline '{data.discipline}' already exists "
                        "in this project."
                    ),
                )

            channel = await self.uow.channels.create(
                project_id=project_id,
                name=data.name,
                discipline=data.discipline,
                is_leads_channel=False,
                approval_policy=data.approval_policy,
            )
            await self.uow.commit()
            return ChannelRead.model_validate(channel)

    async def list_channels(
        self, project_id: str, requester_id: str
    ) -> list[ChannelRead]:
        """
        Visibility rules: workspace owners and team leads see all channels;
        all other project members see channel names (metadata returned here)
        regardless of assignment — content gating is ticket-level.
        """
        async with self.uow:
            project = await self._require_project(project_id)
            await self._require_project_access(project, requester_id)
            channels = await self.uow.channels.list_by_project(project_id)
            filtered_channels = []
            for c in channels:
                if c.is_leads_channel:
                    try:
                        await self._require_leads_channel_access(project, requester_id)
                        filtered_channels.append(c)
                    except HTTPException:
                        # Dynamically hide the leads channel if they aren't eligible
                        continue
                else:
                    filtered_channels.append(c)

            return [ChannelRead.model_validate(c) for c in filtered_channels]

    async def get_channel(
        self, channel_id: str, requester_id: str
    ) -> ChannelRead:
        async with self.uow:
            channel = await self._require_channel(channel_id)
            project = await self._require_project(channel.project_id)
            await self._require_project_access(project, requester_id)
            if channel.is_leads_channel:
                await self._require_leads_channel_access(project, requester_id)

            return ChannelRead.model_validate(channel)

    async def update_channel(
        self, channel_id: str, requester_id: str, data: ChannelUpdate
    ) -> ChannelRead:
        async with self.uow:
            channel = await self._require_channel(channel_id)
            project = await self._require_project(channel.project_id)
            await self._require_team_lead_or_owner(project, requester_id)

            updates = data.model_dump(exclude_none=True)
            if updates:
                channel = await self.uow.channels.update(channel, **updates)

            await self.uow.commit()
            return ChannelRead.model_validate(channel)

    async def delete_channel(
        self, channel_id: str, requester_id: str
    ) -> None:
        async with self.uow:
            channel = await self._require_channel(channel_id)

            if channel.is_leads_channel:
                raise HTTPException(
                    status_code=400,
                    detail="The leads channel cannot be deleted.",
                )

            project = await self._require_project(channel.project_id)
            await self._require_team_lead_or_owner(project, requester_id)

            await self.uow.channels.delete(channel)
            await self.uow.commit()

    # ------------------------------------------------------------------ #
    # Member management                                                    #
    # ------------------------------------------------------------------ #

    async def list_members(self, channel_id: str, requester_id: str) -> list[ChannelMemberRead]:
        async with self.uow:
            channel = await self._require_channel(channel_id)
            project = await self._require_project(channel.project_id)
            await self._require_project_access(project, requester_id)
            if channel.is_leads_channel:
                await self._require_leads_channel_access(project, requester_id)
            # Use the new joined query
            rows = await self.uow.channel_members.list_by_channel_with_users(channel_id)

            return [
                ChannelMemberRead(
                    **ChannelMemberRead.model_validate(m).model_dump(exclude={"user"}),
                    user=UserRead.model_validate(u)
                )
                for m, u in rows
            ]

    async def add_member(
        self, channel_id: str, requester_id: str, data: ChannelMemberAdd
    ) -> ChannelMemberRead:
        """
        Directly add a project member to a channel.

        Who may add:
        - Team Lead or workspace owner (anywhere in the project).
        - Channel Lead (in their own channel only).

        The target must already be a project member — channel membership is
        always a subset of project membership.

        Fix #6: advisors and viewers may not be added to channels. Their
        access is governed by their project role; assigning them to a channel
        (especially as channel_lead) would contradict their role's intent.
        """
        async with self.uow:
            channel = await self._require_channel(channel_id)

            if channel.is_leads_channel:
                raise HTTPException(
                    status_code=400,
                    detail="Members cannot be added to the leads channel directly.",
                )

            project = await self._require_project(channel.project_id)
            await self._require_channel_lead_or_team_lead_or_owner(
                channel, project, requester_id
            )

            target_project_member = await self.uow.project_members.get_by_project_and_user(
                channel.project_id, data.user_id
            )
            if target_project_member is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "The user must be a project member before they can be "
                        "added to a channel. Add them to the project first."
                    ),
                )

            # Fix #6: block advisor/viewer from channel membership
            if target_project_member.role in _CHANNEL_INELIGIBLE_ROLES:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Users with the '{target_project_member.role}' role are "
                        "project-scoped and cannot be assigned to channels. "
                        "Their access is governed by their project role."
                    ),
                )

            existing = await self.uow.channel_members.get_by_channel_and_user(
                channel_id, data.user_id
            )
            if existing is not None:
                raise HTTPException(
                    status_code=409,
                    detail="User is already a member of this channel.",
                )

            member = await self.uow.channel_members.create(
                channel_id=channel_id,
                user_id=data.user_id,
                role=data.role,
            )

            # §7.3 — auto-sync: channel leads get leads channel membership.
            if data.role == ChannelMemberRole.channel_lead:
                await self._add_to_leads_channel_if_needed(
                    channel.project_id, data.user_id
                )

            await self.uow.commit()
            return ChannelMemberRead.model_validate(member)

    async def update_member_role(
        self,
        channel_id: str,
        requester_id: str,
        target_user_id: str,
        data: ChannelMemberUpdate,
    ) -> ChannelMemberRead:
        async with self.uow:
            channel = await self._require_channel(channel_id)
            if channel.is_leads_channel:
                raise HTTPException(
                    status_code=400,
                    detail="Members cannot be manually removed from the leads channel. Membership is automatically managed by project and workspace roles."
                )
            project = await self._require_project(channel.project_id)
            await self._require_channel_lead_or_team_lead_or_owner(
                channel, project, requester_id
            )
            if requester_id != target_user_id:
                requester_weight = await self._get_user_hierarchy_weight(project, channel, requester_id)
                target_weight = await self._get_user_hierarchy_weight(project, channel, target_user_id)

                if requester_weight < target_weight:
                    raise HTTPException(
                        status_code=403,
                        detail="You cannot modify the role of a user who holds a higher role hierarchy."
                    )
            member = await self.uow.channel_members.get_by_channel_and_user(
                channel_id, target_user_id
            )
            if member is None:
                raise HTTPException(status_code=404, detail="Member not found.")

            member = await self.uow.channel_members.update(member, role=data.role)

            # §7.2 — auto-sync leads channel membership on role change.
            if data.role == ChannelMemberRole.channel_lead:
                await self._add_to_leads_channel_if_needed(
                    channel.project_id, target_user_id
                )
            elif data.role == ChannelMemberRole.member:
                await self._remove_from_leads_channel_if_unneeded(
                    channel.project_id, channel.id, target_user_id
                )

            await self.uow.commit()
            return ChannelMemberRead.model_validate(member)

    async def remove_member(
        self, channel_id: str, requester_id: str, target_user_id: str
    ) -> None:
        async with self.uow:
            channel = await self._require_channel(channel_id)
            if channel.is_leads_channel:
                raise HTTPException(
                    status_code=400,
                    detail="Members cannot be manually removed from the leads channel. Membership is automatically managed by project and workspace roles."
                )
            project = await self._require_project(channel.project_id)

            # 1. Verify the requester has base permission to manage members
            await self._require_channel_lead_or_team_lead_or_owner(
                channel, project, requester_id
            )

            # 2. Prevent subordinates from kicking superiors (self-removal is exempt)
            if requester_id != target_user_id:
                requester_weight = await self._get_user_hierarchy_weight(
                    project, channel, requester_id
                )
                target_weight = await self._get_user_hierarchy_weight(
                    project, channel, target_user_id
                )

                if requester_weight < target_weight:
                    raise HTTPException(
                        status_code=403,
                        detail="You cannot remove a user who holds a higher role hierarchy."
                    )

            member = await self.uow.channel_members.get_by_channel_and_user(
                channel_id, target_user_id
            )
            if member is None:
                raise HTTPException(status_code=404, detail="Member not found.")

            await self.uow.channel_members.delete(member)

            # §7.5 — auto-sync: if removing a channel lead, clean up leads
            # channel membership unless another access path retains it.
            if member.role == ChannelMemberRole.channel_lead:
                await self._remove_from_leads_channel_if_unneeded(
                    channel.project_id, channel.id, target_user_id
                )

            await self.uow.commit()

    # ------------------------------------------------------------------ #
    # Leads channel auto-sync helpers (§7.2 / §7.3 / §7.5)               #
    # ------------------------------------------------------------------ #

    async def _add_to_leads_channel_if_needed(
        self, project_id: str, user_id: str
    ) -> None:
        """Add user to the leads channel as a plain member, if not already there."""
        leads_channel = await self.uow.channels.get_leads_channel(project_id)
        if leads_channel is None:
            return
        existing = await self.uow.channel_members.get_by_channel_and_user(
            leads_channel.id, user_id
        )
        if existing is None:
            await self.uow.channel_members.create(
                channel_id=leads_channel.id,
                user_id=user_id,
                role=ChannelMemberRole.member,
            )

    async def _remove_from_leads_channel_if_unneeded(
        self, project_id: str, excluding_channel_id: str, user_id: str
    ) -> None:
        """Remove user from leads channel unless a retained access path exists:

        - A project-level role (team_lead, advisor, viewer) grants standalone
          leads channel access.
        - Being a channel_lead in any OTHER discipline channel also retains it.

        ``excluding_channel_id`` is the channel the role change / removal just
        happened in — it must be skipped when checking other channels.
        """
        # Retained via project role?
        pm = await self.uow.project_members.get_by_project_and_user(
            project_id, user_id
        )
        if pm and pm.role in (
            ProjectRole.team_lead,
            ProjectRole.advisor,
            ProjectRole.viewer,
        ):
            return

        # Retained as channel lead elsewhere?
        channels = await self.uow.channels.list_by_project(project_id)
        for ch in channels:
            if ch.id == excluding_channel_id or ch.is_leads_channel:
                continue
            cm = await self.uow.channel_members.get_by_channel_and_user(ch.id, user_id)
            if cm and cm.role == ChannelMemberRole.channel_lead:
                return

        # No retained path — remove from leads channel.
        leads_channel = await self.uow.channels.get_leads_channel(project_id)
        if leads_channel is None:
            return
        leads_member = await self.uow.channel_members.get_by_channel_and_user(
            leads_channel.id, user_id
        )
        if leads_member:
            await self.uow.channel_members.delete(leads_member)

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    async def _get_user_hierarchy_weight(self, project, channel, user_id: str) -> int:
        """
        Returns a numeric weight representing the user's highest authority level.
        3 = Workspace Owner
        2 = Team Lead
        1 = Channel Lead
        0 = Standard Member / Advisor / Viewer
        """
        ws_member = await self.uow.workspace_members.get_by_workspace_and_user(
            project.workspace_id, user_id
        )
        if ws_member and ws_member.is_owner:
            return 3

        project_member = await self.uow.project_members.get_by_project_and_user(
            project.id, user_id
        )
        if project_member and project_member.role == ProjectRole.team_lead:
            return 2

        channel_member = await self.uow.channel_members.get_by_channel_and_user(
            channel.id, user_id
        )
        if channel_member and channel_member.role == ChannelMemberRole.channel_lead:
            return 1

        return 0

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

    async def _require_project_access(self, project, requester_id: str):
        ws_member = await self.uow.workspace_members.get_by_workspace_and_user(
            project.workspace_id, requester_id
        )
        if ws_member and ws_member.is_owner:
            return ws_member

        project_member = await self.uow.project_members.get_by_project_and_user(
            project.id, requester_id
        )
        if project_member is None:
            raise HTTPException(
                status_code=403,
                detail="You do not have access to this project.",
            )
        return project_member

    async def _require_team_lead_or_owner(self, project, requester_id: str):
        ws_member = await self.uow.workspace_members.get_by_workspace_and_user(
            project.workspace_id, requester_id
        )
        if ws_member and ws_member.is_owner:
            return ws_member

        project_member = await self.uow.project_members.get_by_project_and_user(
            project.id, requester_id
        )
        if project_member is None or project_member.role != ProjectRole.team_lead:
            raise HTTPException(
                status_code=403,
                detail="Only Team Leads (or workspace owners) can perform this action.",
            )
        return project_member

    async def _require_leads_channel_access(self, project, user_id: str) -> None:
        """§7.1 — Allow: workspace owners, team leads, advisors, viewers, and
        channel leads of any discipline channel in the project.
        """
        # 1. Workspace owners always have access
        ws_member = await self.uow.workspace_members.get_by_workspace_and_user(
            project.workspace_id, user_id
        )
        if ws_member and ws_member.is_owner:
            return

        # 2. Project Team Leads, Advisors, and Viewers have access
        pm = await self.uow.project_members.get_by_project_and_user(
            project.id, user_id
        )
        if pm and pm.role in (
            ProjectRole.team_lead,
            ProjectRole.advisor,
            ProjectRole.viewer,
        ):
            return

        # 3. Channel leads of any discipline channel in this project  ← §7.1 addition
        channels = await self.uow.channels.list_by_project(project.id)
        for ch in channels:
            if ch.is_leads_channel:
                continue
            cm = await self.uow.channel_members.get_by_channel_and_user(ch.id, user_id)
            if cm and cm.role == ChannelMemberRole.channel_lead:
                return

        raise HTTPException(
            status_code=403,
            detail="You are not authorized to view or enter the leads channel.",
        )

    async def _require_channel_lead_or_team_lead_or_owner(
        self, channel, project, requester_id: str
    ):
        ws_member = await self.uow.workspace_members.get_by_workspace_and_user(
            project.workspace_id, requester_id
        )
        if ws_member and ws_member.is_owner:
            return ws_member

        project_member = await self.uow.project_members.get_by_project_and_user(
            project.id, requester_id
        )
        if project_member and project_member.role == ProjectRole.team_lead:
            return project_member

        channel_member = await self.uow.channel_members.get_by_channel_and_user(
            channel.id, requester_id
        )
        if channel_member and channel_member.role == ChannelMemberRole.channel_lead:
            return channel_member

        raise HTTPException(
            status_code=403,
            detail=(
                "Only Channel Leads, Team Leads, or workspace owners "
                "can manage channel membership."
            ),
        )