from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_redis
from app.database import get_db
from app.ticket.uow import SqlAlchemyTicketUnitOfWork
from .service import AgentRunService


async def get_agent_run_service(
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis),
) -> AgentRunService:
    return AgentRunService(SqlAlchemyTicketUnitOfWork(db), redis)