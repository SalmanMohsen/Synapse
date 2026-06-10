from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ThreadState


class ThreadStateRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, **kwargs) -> ThreadState:
        thread_state = ThreadState(**kwargs)
        self.db.add(thread_state)
        await self.db.flush()
        await self.db.refresh(thread_state)
        return thread_state

    async def get_by_ticket_id(self, ticket_id: str) -> ThreadState | None:
        result = await self.db.execute(
            select(ThreadState).where(ThreadState.ticket_id == ticket_id)
        )
        return result.scalar_one_or_none()

    async def delete_by_ticket_id(self, ticket_id: str) -> None:
        thread_state = await self.get_by_ticket_id(ticket_id)
        if thread_state is not None:
            await self.db.delete(thread_state)
            await self.db.flush()