from fastapi import HTTPException

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
            return [ChannelRead.model_validate(c) for c in channels]

    async def get_channel(
        self, channel_id: str, requester_id: str
    ) -> ChannelRead:
        async with self.uow:
            channel = await self._require_channel(channel_id)
            project = await self._require_project(channel.project_id)
            await self._require_project_access(project, requester_id)
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

    async def list_members(
        self, channel_id: str, requester_id: str
    ) -> list[ChannelMemberRead]:
        async with self.uow:
            channel = await self._require_channel(channel_id)
            project = await self._require_project(channel.project_id)
            await self._require_project_access(project, requester_id)
            members = await self.uow.channel_members.list_by_channel(channel_id)
            return [ChannelMemberRead.model_validate(m) for m in members]

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
            project = await self._require_project(channel.project_id)
            await self._require_channel_lead_or_team_lead_or_owner(
                channel, project, requester_id
            )

            member = await self.uow.channel_members.get_by_channel_and_user(
                channel_id, target_user_id
            )
            if member is None:
                raise HTTPException(status_code=404, detail="Member not found.")

            member = await self.uow.channel_members.update(member, role=data.role)
            await self.uow.commit()
            return ChannelMemberRead.model_validate(member)

    async def remove_member(
        self, channel_id: str, requester_id: str, target_user_id: str
    ) -> None:
        async with self.uow:
            channel = await self._require_channel(channel_id)
            project = await self._require_project(channel.project_id)
            await self._require_channel_lead_or_team_lead_or_owner(
                channel, project, requester_id
            )

            member = await self.uow.channel_members.get_by_channel_and_user(
                channel_id, target_user_id
            )
            if member is None:
                raise HTTPException(status_code=404, detail="Member not found.")

            await self.uow.channel_members.delete(member)
            await self.uow.commit()

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

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