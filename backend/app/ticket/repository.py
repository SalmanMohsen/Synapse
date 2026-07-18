from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.channel.models import Channel
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
    
    async def get_by_project_and_issue_number(self, project_id: str, issue_number: int) -> Ticket | None:
        result = await self.db.execute(
            select(Ticket)
            .join(Channel, Channel.id == Ticket.channel_id)
            .where(
                Channel.project_id == project_id,
                Ticket.github_issue_number == issue_number,
            )
        )
        return result.scalar_one_or_none()

    async def update(self, ticket: Ticket, **kwargs) -> Ticket:
        for key, value in kwargs.items():
            setattr(ticket, key, value)
        await self.db.flush()
        await self.db.refresh(ticket)
        return ticket
    
    async def get_by_project_and_pr_number(self, project_id: str, pr_number: int) -> Ticket | None:
        result = await self.db.execute(
            select(Ticket)
            .join(Channel, Channel.id == Ticket.channel_id)
            .where(
                Channel.project_id == project_id,
                Ticket.github_pr_number == pr_number,
            )
        )
        return result.scalar_one_or_none()