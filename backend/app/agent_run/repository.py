from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_run.models import (
    AgentRun,
    AgentRunStatus,
    AgentRunStep,
    AgentRunStepStatus,
)

_ACTIVE_STATUSES = (AgentRunStatus.pending, AgentRunStatus.running)


class AgentRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, ticket_id: str, status: AgentRunStatus) -> AgentRun:
        run = AgentRun(ticket_id=ticket_id, status=status)
        self.session.add(run)
        await self.session.flush()
        await self.session.refresh(run)
        return run

    async def get_by_id(self, run_id: str) -> AgentRun | None:
        return await self.session.get(AgentRun, run_id)

    async def get_active_by_ticket(self, ticket_id: str) -> AgentRun | None:
        """Returns the current pending/running run for a ticket, if any.

        Mirrors the partial unique index — used to give the trigger endpoint
        a clean pre-check before hitting the DB constraint.
        """
        result = await self.session.execute(
            select(AgentRun).where(
                AgentRun.ticket_id == ticket_id,
                AgentRun.status.in_(_ACTIVE_STATUSES),
            )
        )
        return result.scalar_one_or_none()

    async def list_by_ticket(self, ticket_id: str) -> list[AgentRun]:
        result = await self.session.execute(
            select(AgentRun)
            .where(AgentRun.ticket_id == ticket_id)
            .order_by(AgentRun.created_at.desc())
        )
        return list(result.scalars().all())

    async def update(self, run: AgentRun, **fields) -> AgentRun:
        for key, value in fields.items():
            setattr(run, key, value)
        await self.session.flush()
        await self.session.refresh(run)
        return run


class AgentRunStepRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        agent_run_id: str,
        step_number: int,
        description: str,
        status: AgentRunStepStatus,
        model_prompt: str | None = None,
        model_response: str | None = None,
        error: str | None = None,
    ) -> AgentRunStep:
        step = AgentRunStep(
            agent_run_id=agent_run_id,
            step_number=step_number,
            description=description,
            status=status,
            model_prompt=model_prompt,
            model_response=model_response,
            error=error,
        )
        self.session.add(step)
        await self.session.flush()
        await self.session.refresh(step)
        return step

    async def list_by_run(self, agent_run_id: str) -> list[AgentRunStep]:
        result = await self.session.execute(
            select(AgentRunStep)
            .where(AgentRunStep.agent_run_id == agent_run_id)
            .order_by(AgentRunStep.step_number.asc())
        )
        return list(result.scalars().all())