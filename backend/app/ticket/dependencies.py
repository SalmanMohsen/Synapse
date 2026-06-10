from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

from .service import TicketService
from .uow import SqlAlchemyTicketUnitOfWork


async def get_ticket_service(
    db: AsyncSession = Depends(get_db),
) -> TicketService:
    return TicketService(SqlAlchemyTicketUnitOfWork(db))