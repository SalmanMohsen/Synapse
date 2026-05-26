from fastapi import HTTPException

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

            # Policy gate: restricted workspaces only allow owners to create projects
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
            # Only workspace owners may delete projects (design decision: owners
            # can delete any project regardless of who created it).
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

    async def list_members(
        self, project_id: str, requester_id: str
    ) -> list[ProjectMemberRead]:
        async with self.uow:
            project = await self._require_project(project_id)
            await self._require_project_visibility(project, requester_id)
            members = await self.uow.project_members.list_by_project(project_id)
            return [ProjectMemberRead.model_validate(m) for m in members]

    async def add_member(
        self, project_id: str, requester_id: str, data: ProjectMemberAdd
    ) -> ProjectMemberRead:
        """
        Add a workspace member to this project directly.

        Only team leads (and workspace owners as fallback) may add members.
        The target must already be a workspace member — project membership
        is always a subset of workspace membership.

        NOTE: Async token-based invite flow (for member acceptance/refusal)
        is deferred to Phase 2 when the notification system is built.
        """
        async with self.uow:
            project = await self._require_project(project_id)
            await self._require_team_lead_or_owner(project, requester_id)

            # Target must be in the workspace already
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

            # Guard: don't demote the last team lead
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
        """
        A requester can see a project if they are:
        - a workspace owner, OR
        - a project member (any role)
        """
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
        """
        Allow if the requester is a workspace owner OR a project team lead.
        Workspace owners act as fallback for all project operations.
        """
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