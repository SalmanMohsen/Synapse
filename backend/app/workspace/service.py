from fastapi import HTTPException

from .schemas import (
    WorkspaceMemberRead,
    WorkspaceCreate,
    WorkspaceRead,
    WorkspaceUpdate,
)
from .uow import AbstractWorkspaceUnitOfWork


class WorkspaceService:
    def __init__(self, uow: AbstractWorkspaceUnitOfWork) -> None:
        self.uow = uow

    # ------------------------------------------------------------------ #
    # Workspace CRUD                                                       #
    # ------------------------------------------------------------------ #

    async def create_workspace(
        self, creator_id: str, data: WorkspaceCreate
    ) -> WorkspaceRead:
        async with self.uow:
            workspace = await self.uow.workspaces.create(name=data.name)
            await self.uow.members.create(
                workspace_id=workspace.id,
                user_id=creator_id,
                is_owner=True,
            )
            await self.uow.commit()
            return WorkspaceRead.model_validate(workspace)

    async def get_workspace(
        self, workspace_id: str, requester_id: str
    ) -> WorkspaceRead:
        async with self.uow:
            workspace = await self._require_workspace(workspace_id)
            await self._require_member(workspace_id, requester_id)
            return WorkspaceRead.model_validate(workspace)

    async def update_workspace(
        self, workspace_id: str, data: WorkspaceUpdate, requester_id: str
    ) -> WorkspaceRead:
        async with self.uow:
            workspace = await self._require_workspace(workspace_id)
            await self._require_owner(workspace_id, requester_id)

            updates = data.model_dump(exclude_none=True)
            if updates:
                workspace = await self.uow.workspaces.update(workspace, **updates)

            await self.uow.commit()
            return WorkspaceRead.model_validate(workspace)

    async def delete_workspace(
        self, workspace_id: str, requester_id: str
    ) -> None:
        async with self.uow:
            workspace = await self._require_workspace(workspace_id)
            await self._require_owner(workspace_id, requester_id)
            await self.uow.workspaces.delete(workspace)
            await self.uow.commit()

    # ------------------------------------------------------------------ #
    # Member management                                                    #
    # ------------------------------------------------------------------ #

    async def list_members(
        self, workspace_id: str, requester_id: str
    ) -> list[WorkspaceMemberRead]:
        async with self.uow:
            await self._require_workspace(workspace_id)
            await self._require_member(workspace_id, requester_id)
            members = await self.uow.members.list_by_workspace(workspace_id)
            return [WorkspaceMemberRead.model_validate(m) for m in members]

    async def add_owner(
        self, workspace_id: str, target_user_id: str, requester_id: str
    ) -> WorkspaceMemberRead:
        """Promote an existing workspace member to owner."""
        async with self.uow:
            await self._require_workspace(workspace_id)
            await self._require_owner(workspace_id, requester_id)

            member = await self.uow.members.get_by_workspace_and_user(
                workspace_id, target_user_id
            )
            if member is None:
                raise HTTPException(
                    status_code=404,
                    detail="User is not a member of this workspace",
                )
            if member.is_owner:
                raise HTTPException(
                    status_code=409, detail="User is already an owner"
                )

            member = await self.uow.members.update(member, is_owner=True)
            await self.uow.commit()
            return WorkspaceMemberRead.model_validate(member)

    async def remove_member(
        self, workspace_id: str, target_user_id: str, requester_id: str
    ) -> None:
        """
        Remove a member from the workspace.

        Fix #5 — cascade cleanup: all of the user's project and channel
        memberships within this workspace are deleted in the same transaction
        so the data model invariant (workspace ⊃ project ⊃ channel membership)
        is never violated.

        Allowed callers:
        - Any workspace owner may remove any other member.
        - Any member may remove themselves (self-removal).

        The last-owner invariant is enforced regardless of who asked.
        """
        async with self.uow:
            await self._require_workspace(workspace_id)

            # Non-owners may only remove themselves.
            if requester_id != target_user_id:
                await self._require_owner(workspace_id, requester_id)

            member = await self.uow.members.get_by_workspace_and_user(
                workspace_id, target_user_id
            )
            if member is None:
                raise HTTPException(status_code=404, detail="Member not found")

            if member.is_owner:
                owner_count = await self.uow.members.count_owners(workspace_id)
                if owner_count <= 1:
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot remove the last owner. Assign a new owner first.",
                    )

            # Cascade: remove channel memberships before project memberships
            # (channel membership is a subset of project membership).
            projects = await self.uow.projects.list_by_workspace(workspace_id)
            project_ids = [p.id for p in projects]

            if project_ids:
                for project_id in project_ids:
                    # Channel memberships in this project
                    channels = await self.uow.channels.list_by_project(project_id)
                    for channel in channels:
                        cm = await self.uow.channel_members.get_by_channel_and_user(
                            channel.id, target_user_id
                        )
                        if cm is not None:
                            await self.uow.channel_members.delete(cm)

                    # Project membership
                    pm = await self.uow.project_members.get_by_project_and_user(
                        project_id, target_user_id
                    )
                    if pm is not None:
                        await self.uow.project_members.delete(pm)

            # Finally remove the workspace membership itself
            await self.uow.members.delete(member)
            await self.uow.commit()

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    async def _require_workspace(self, workspace_id: str):
        workspace = await self.uow.workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        return workspace

    async def _require_member(self, workspace_id: str, user_id: str):
        member = await self.uow.members.get_by_workspace_and_user(
            workspace_id, user_id
        )
        if member is None:
            raise HTTPException(
                status_code=403, detail="You are not a member of this workspace"
            )
        return member

    async def _require_owner(self, workspace_id: str, user_id: str):
        member = await self.uow.members.get_by_workspace_and_user(
            workspace_id, user_id
        )
        if member is None or not member.is_owner:
            raise HTTPException(
                status_code=403,
                detail="Only workspace owners can perform this action",
            )
        return member