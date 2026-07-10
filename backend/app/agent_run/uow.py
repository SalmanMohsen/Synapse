from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_run.repository import AgentRunRepository, AgentRunStepRepository


class AbstractAgentRunUnitOfWork(ABC):
    agent_runs: AgentRunRepository
    agent_run_steps: AgentRunStepRepository

    async def __aenter__(self) -> "AbstractAgentRunUnitOfWork":
        return self

    async def __aexit__(self, *args) -> None:
        await self.rollback()

    @abstractmethod
    async def commit(self) -> None: ...

    @abstractmethod
    async def rollback(self) -> None: ...


class AgentRunUnitOfWork(AbstractAgentRunUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def __aenter__(self) -> "AgentRunUnitOfWork":
        self.agent_runs = AgentRunRepository(self.session)
        self.agent_run_steps = AgentRunStepRepository(self.session)
        return self

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()