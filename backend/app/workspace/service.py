from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from .schemas import (
    WorkspaceCreate,
    WorkspaceInviteCreate,
    WorkspaceInviteRead,
    WorkspaceMemberRead,
    WorkspaceRead,
    WorkspaceUpdate,
)
from .uow import AbstractWorkspaceUnitOfWork

_WORKSPACE_INVITE_TTL_DAYS = 30


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

        Allowed callers:
        - Any workspace owner may remove any other member.
        - Any member may remove themselves (self-removal).

        In both cases the last-owner invariant is enforced: if the target
        is the last owner, the removal is rejected regardless of who asked.
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

            await self.uow.members.delete(member)
            await self.uow.commit()

    # ------------------------------------------------------------------ #
    # Invites                                                              #
    # ------------------------------------------------------------------ #

    async def create_invite(
        self,
        workspace_id: str,
        data: WorkspaceInviteCreate,
        requester_id: str,
    ) -> WorkspaceInviteRead:
        """Only owners may create workspace-scope invites."""
        async with self.uow:
            await self._require_workspace(workspace_id)
            await self._require_owner(workspace_id, requester_id)

            expires_at = datetime.now(timezone.utc) + timedelta(
                days=_WORKSPACE_INVITE_TTL_DAYS
            )
            invite = await self.uow.invites.create(
                workspace_id=workspace_id,
                role=data.role,
                invited_by=requester_id,
                expires_at=expires_at,
            )
            await self.uow.commit()
            return WorkspaceInviteRead.model_validate(invite)

    async def accept_invite(self, token: str, user_id: str) -> WorkspaceRead:
        async with self.uow:
            invite = await self.uow.invites.get_by_token(token)
            if invite is None:
                raise HTTPException(status_code=404, detail="Invite not found")

            if invite.used_at is not None:
                raise HTTPException(
                    status_code=400, detail="Invite has already been used"
                )
            if datetime.now(timezone.utc) > invite.expires_at:
                raise HTTPException(status_code=400, detail="Invite has expired")

            existing = await self.uow.members.get_by_workspace_and_user(
                invite.workspace_id, user_id
            )
            if existing is not None:
                raise HTTPException(
                    status_code=409,
                    detail="You are already a member of this workspace",
                )

            await self.uow.members.create(
                workspace_id=invite.workspace_id,
                user_id=user_id,
                is_owner=(invite.role == "owner"),
            )
            await self.uow.invites.mark_used(invite)
            await self.uow.commit()

            workspace = await self.uow.workspaces.get_by_id(invite.workspace_id)
            return WorkspaceRead.model_validate(workspace)

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