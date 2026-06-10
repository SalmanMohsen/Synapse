from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Ticket


class TicketRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, **kwargs) -> Ticket:
        ticket = Ticket(**kwargs)
        self.db.add(ticket)
        await self.db.flush()
        await self.db.refresh(ticket)
        return ticket

    async def get_by_id(self, ticket_id: str) -> Ticket | None:
        result = await self.db.execute(
            select(Ticket).where(Ticket.id == ticket_id)
        )
        return result.scalar_one_or_none()

    async def list_by_channel(self, channel_id: str) -> list[Ticket]:
        result = await self.db.execute(
            select(Ticket)
            .where(Ticket.channel_id == channel_id)
            .order_by(Ticket.created_at.desc())
        )
        return list(result.scalars().all())

    async def update(self, ticket: Ticket, **kwargs) -> Ticket:
        for key, value in kwargs.items():
            setattr(ticket, key, value)
        await self.db.flush()
        await self.db.refresh(ticket)
        return ticket