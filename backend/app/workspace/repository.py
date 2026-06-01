from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Workspace, WorkspaceMember


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

    async def list_owners_except(
        self, workspace_id: str, exclude_user_id: str
    ) -> list[WorkspaceMember]:
        """Return all owners in the workspace except a specific user. Used to
        fan out notifications to other owners when a project is created."""
        result = await self.db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.is_owner.is_(True),
                WorkspaceMember.user_id != exclude_user_id,
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