from fastapi import HTTPException
from app.auth.schemas import UserRead
from app.channel.models import ApprovalPolicy
from app.inbox.service import InboxService
from app.workspace.models import ProjectCreationPolicy

from .models import ProjectRole
from .schemas import (
    ProjectCreate,
    ProjectMemberAdd,
    ProjectMemberRead,
    ProjectMemberUpdate,
    ProjectRead,
    ProjectUpdate,
)
from .uow import AbstractProjectUnitOfWork
from app.channel.models import ChannelMemberRole

_LEADS_CHANNEL_NAME = "leads"


class ProjectService:
    def __init__(self, uow: AbstractProjectUnitOfWork) -> None:
        self.uow = uow

    # ------------------------------------------------------------------ #
    # Project CRUD                                                         #
    # ------------------------------------------------------------------ #

    async def create_project(
        self, workspace_id: str, creator_id: str, data: ProjectCreate
    ) -> ProjectRead:
        async with self.uow:
            workspace = await self._require_workspace(workspace_id)
            ws_member = await self._require_workspace_member(workspace_id, creator_id)

            # Policy gate
            if workspace.project_creation_policy == ProjectCreationPolicy.restricted:
                if not ws_member.is_owner:
                    raise HTTPException(
                        status_code=403,
                        detail=(
                            "This workspace requires owner permission to create projects. "
                            "Ask a workspace owner to create the project or change the policy."
                        ),
                    )

            project = await self.uow.projects.create(
                workspace_id=workspace_id,
                name=data.name,
                github_app_installation_id=data.github_app_installation_id,
                default_branch=data.default_branch,
            )
            await self.uow.project_members.create(
                project_id=project.id,
                user_id=creator_id,
                role=ProjectRole.team_lead,
            )
            # Leads channel is created atomically in the same transaction.
            leads_channel = await self.uow.channels.create(
                project_id=project.id,
                name=_LEADS_CHANNEL_NAME,
                discipline=None,
                is_leads_channel=True,
                approval_policy=ApprovalPolicy.lead_only,
            )

            await self.uow.channel_members.create(
                channel_id=leads_channel.id,
                user_id=creator_id,
                role=ChannelMemberRole.channel_lead
            )
            
            # Fix #2: notify all other workspace owners that a new project was created.
            other_owners = await self.uow.workspace_members.list_owners_except(
                workspace_id, exclude_user_id=creator_id
            )
            for owner in other_owners:
                await self.uow.channel_members.create(
                    channel_id=leads_channel.id,
                    user_id=owner.user_id,
                    role=ChannelMemberRole.member
                )

            for owner in other_owners:
                await InboxService.create_notification(
                    self.uow.inbox_items,
                    user_id=owner.user_id,
                    title=f"New project created: \"{data.name}\"",
                    body=f"A new project was created in your workspace by a team member.",
                    sender_id=creator_id,
                    workspace_id=workspace_id,
                    project_id=project.id,
                    entity_type="project",
                    entity_id=project.id,
                )

            await self.uow.commit()
            return ProjectRead.model_validate(project)

    async def list_projects(
        self, workspace_id: str, requester_id: str
    ) -> list[ProjectRead]:
        async with self.uow:
            await self._require_workspace(workspace_id)
            ws_member = await self._require_workspace_member(workspace_id, requester_id)

            if ws_member.is_owner:
                projects = await self.uow.projects.list_by_workspace(workspace_id)
            else:
                projects = await self.uow.projects.list_by_workspace_for_user(
                    workspace_id, requester_id
                )

            return [ProjectRead.model_validate(p) for p in projects]

    async def get_project(
        self, project_id: str, requester_id: str
    ) -> ProjectRead:
        async with self.uow:
            project = await self._require_project(project_id)
            await self._require_project_visibility(project, requester_id)
            return ProjectRead.model_validate(project)

    async def update_project(
        self, project_id: str, requester_id: str, data: ProjectUpdate
    ) -> ProjectRead:
        async with self.uow:
            project = await self._require_project(project_id)
            await self._require_team_lead_or_owner(project, requester_id)

            updates = data.model_dump(exclude_none=True)
            if updates:
                project = await self.uow.projects.update(project, **updates)

            await self.uow.commit()
            return ProjectRead.model_validate(project)

    async def delete_project(
        self, project_id: str, requester_id: str
    ) -> None:
        async with self.uow:
            project = await self._require_project(project_id)
            ws_member = await self.uow.workspace_members.get_by_workspace_and_user(
                project.workspace_id, requester_id
            )
            if ws_member is None or not ws_member.is_owner:
                raise HTTPException(
                    status_code=403,
                    detail="Only workspace owners can delete projects.",
                )
            await self.uow.projects.delete(project)
            await self.uow.commit()

    # ------------------------------------------------------------------ #
    # Member management                                                    #
    # ------------------------------------------------------------------ #

    async def list_members(self, project_id: str, requester_id: str) -> list[ProjectMemberRead]:
        async with self.uow:
            project = await self._require_project(project_id)
            await self._require_project_visibility(project, requester_id)
            
            # Use the new joined query
            rows = await self.uow.project_members.list_by_project_with_users(project_id)
            return [
                ProjectMemberRead(
                    **ProjectMemberRead.model_validate(m).model_dump(exclude={"user"}),
                    user=UserRead.model_validate(u)
                )
                for m, u in rows
            ]
        
    async def add_member(
        self, project_id: str, requester_id: str, data: ProjectMemberAdd
    ) -> ProjectMemberRead:
        """
        Direct add (no invite) — used by team leads and owners to immediately
        assign a workspace member to the project.

        The invite flow (inbox) should be preferred for the typical onboarding
        path so the target user can see who is inviting them and accept/decline.
        Direct add is kept for programmatic and admin use cases.
        """
        async with self.uow:
            project = await self._require_project(project_id)
            await self._require_team_lead_or_owner(project, requester_id)

            target_ws_member = await self.uow.workspace_members.get_by_workspace_and_user(
                project.workspace_id, data.user_id
            )
            if target_ws_member is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "The user must be a workspace member before they can be "
                        "added to a project. Invite them to the workspace first."
                    ),
                )

            existing = await self.uow.project_members.get_by_project_and_user(
                project_id, data.user_id
            )
            if existing is not None:
                raise HTTPException(
                    status_code=409,
                    detail="User is already a member of this project.",
                )

            member = await self.uow.project_members.create(
                project_id=project_id,
                user_id=data.user_id,
                role=data.role,
            )

            if data.role in (ProjectRole.team_lead, ProjectRole.advisor, ProjectRole.viewer):
                leads_channel = await self.uow.channels.get_leads_channel(project_id)
                if leads_channel:
                    await self.uow.channel_members.create(
                        channel_id=leads_channel.id,
                        user_id=data.user_id,
                        role=(
                            ChannelMemberRole.channel_lead 
                            if data.role == ProjectRole.team_lead 
                            else ChannelMemberRole.member
                        )
                    )

            await self.uow.commit()
            return ProjectMemberRead.model_validate(member)

    async def update_member_role(
        self,
        project_id: str,
        requester_id: str,
        target_user_id: str,
        data: ProjectMemberUpdate,
    ) -> ProjectMemberRead:
        async with self.uow:
            project = await self._require_project(project_id)
            await self._require_team_lead_or_owner(project, requester_id)

            member = await self.uow.project_members.get_by_project_and_user(
                project_id, target_user_id
            )
            if member is None:
                raise HTTPException(status_code=404, detail="Member not found.")

            if member.role == ProjectRole.team_lead and data.role != ProjectRole.team_lead:
                lead_count = await self.uow.project_members.count_by_role(
                    project_id, ProjectRole.team_lead
                )
                if lead_count <= 1:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Cannot change the role of the last Team Lead. "
                            "Assign another Team Lead first."
                        ),
                    )

            member = await self.uow.project_members.update(member, role=data.role)
            if data.role in (ProjectRole.team_lead, ProjectRole.advisor, ProjectRole.viewer):
                leads_channel = await self.uow.channels.get_leads_channel(project_id)
                if leads_channel:
                    existing_cm = await self.uow.channel_members.get_by_channel_and_user(
                        leads_channel.id, target_user_id
                    )
                    
                    target_channel_role = (
                        ChannelMemberRole.channel_lead 
                        if data.role == ProjectRole.team_lead 
                        else ChannelMemberRole.member
                    )

                    if not existing_cm:
                        await self.uow.channel_members.create(
                            channel_id=leads_channel.id,
                            user_id=target_user_id,
                            role=target_channel_role
                        )
                    elif existing_cm.role != target_channel_role and data.role == ProjectRole.team_lead:
                        # Upgrade their channel role to channel_lead if they are now a team_lead
                        await self.uow.channel_members.update(
                            existing_cm, role=ChannelMemberRole.channel_lead
                        )

            await self.uow.commit()
            return ProjectMemberRead.model_validate(member)

    async def remove_member(
        self, project_id: str, requester_id: str, target_user_id: str
    ) -> None:
        async with self.uow:
            project = await self._require_project(project_id)
            await self._require_team_lead_or_owner(project, requester_id)

            member = await self.uow.project_members.get_by_project_and_user(
                project_id, target_user_id
            )
            if member is None:
                raise HTTPException(status_code=404, detail="Member not found.")

            if member.role == ProjectRole.team_lead:
                lead_count = await self.uow.project_members.count_by_role(
                    project_id, ProjectRole.team_lead
                )
                if lead_count <= 1:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Cannot remove the last Team Lead. "
                            "Assign another Team Lead first."
                        ),
                    )

            await self.uow.project_members.delete(member)
            await self.uow.commit()

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    async def _require_workspace(self, workspace_id: str):
        workspace = await self.uow.workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found.")
        return workspace

    async def _require_workspace_member(self, workspace_id: str, user_id: str):
        member = await self.uow.workspace_members.get_by_workspace_and_user(
            workspace_id, user_id
        )
        if member is None:
            raise HTTPException(
                status_code=403,
                detail="You are not a member of this workspace.",
            )
        return member

    async def _require_project(self, project_id: str):
        project = await self.uow.projects.get_by_id(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        return project

    async def _require_project_visibility(self, project, requester_id: str):
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