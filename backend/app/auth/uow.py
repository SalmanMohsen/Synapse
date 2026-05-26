from sqlalchemy.ext.asyncio import AsyncSession

from app.UoW import AbstractUnitOfWork
from .repository import UserRepository


class AbstractAuthUnitOfWork(AbstractUnitOfWork):
    users: UserRepository


class SqlAlchemyAuthUnitOfWork(AbstractAuthUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()