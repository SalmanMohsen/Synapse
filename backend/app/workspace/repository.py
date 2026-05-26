from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Workspace, WorkspaceInvite, WorkspaceMember


class WorkspaceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, workspace_id: str) -> Workspace | None:
        result = await self.db.execute(
            select(Workspace).where(Workspace.id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> Workspace:
        workspace = Workspace(**kwargs)
        self.db.add(workspace)
        await self.db.flush()
        await self.db.refresh(workspace)
        return workspace

    async def update(self, workspace: Workspace, **kwargs) -> Workspace:
        for key, value in kwargs.items():
            setattr(workspace, key, value)
        await self.db.flush()
        await self.db.refresh(workspace)
        return workspace

    async def delete(self, workspace: Workspace) -> None:
        await self.db.delete(workspace)
        await self.db.flush()


class WorkspaceMemberRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_workspace_and_user(
        self, workspace_id: str, user_id: str
    ) -> WorkspaceMember | None:
        result = await self.db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_workspace(self, workspace_id: str) -> list[WorkspaceMember]:
        result = await self.db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id
            )
        )
        return list(result.scalars().all())

    async def count_owners(self, workspace_id: str) -> int:
        result = await self.db.execute(
            select(func.count()).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.is_owner.is_(True),
            )
        )
        return result.scalar_one()

    async def create(self, **kwargs) -> WorkspaceMember:
        member = WorkspaceMember(**kwargs)
        self.db.add(member)
        await self.db.flush()
        await self.db.refresh(member)
        return member

    async def update(self, member: WorkspaceMember, **kwargs) -> WorkspaceMember:
        for key, value in kwargs.items():
            setattr(member, key, value)
        await self.db.flush()
        await self.db.refresh(member)
        return member

    async def delete(self, member: WorkspaceMember) -> None:
        await self.db.delete(member)
        await self.db.flush()


class WorkspaceInviteRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_token(self, token: str) -> WorkspaceInvite | None:
        result = await self.db.execute(
            select(WorkspaceInvite).where(WorkspaceInvite.token == token)
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> WorkspaceInvite:
        invite = WorkspaceInvite(**kwargs)
        self.db.add(invite)
        await self.db.flush()
        await self.db.refresh(invite)
        return invite

    async def mark_used(self, invite: WorkspaceInvite) -> WorkspaceInvite:
        from datetime import datetime, timezone

        invite.used_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(invite)
        return invite