from sqlalchemy.ext.asyncio import AsyncSession

from app.UoW import AbstractUnitOfWork
from .repository import (
    WorkspaceInviteRepository,
    WorkspaceMemberRepository,
    WorkspaceRepository,
)


class AbstractWorkspaceUnitOfWork(AbstractUnitOfWork):
    workspaces: WorkspaceRepository
    members: WorkspaceMemberRepository
    invites: WorkspaceInviteRepository


class SqlAlchemyWorkspaceUnitOfWork(AbstractWorkspaceUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.workspaces = WorkspaceRepository(session)
        self.members = WorkspaceMemberRepository(session)
        self.invites = WorkspaceInviteRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()