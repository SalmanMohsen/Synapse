from abc import ABC, abstractmethod
from sqlalchemy.ext.asyncio import AsyncSession
from .repository import UserRepository

class AbstractUnitOfWork(ABC):
    users: UserRepository

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self.rollback()

    @abstractmethod
    async def commit(self):
        pass

    @abstractmethod
    async def rollback(self):
        pass

class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)

    async def __aenter__(self):
        return await super().__aenter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await super().__aexit__(exc_type, exc_val, exc_tb)

    async def commit(self):
        await self.session.commit()

    async def rollback(self):
        await self.session.rollback()