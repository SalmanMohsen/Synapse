from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

from .service import MessageService
from .uow import SqlAlchemyMessageUnitOfWork


async def get_message_service(
    db: AsyncSession = Depends(get_db),
) -> MessageService:
    return MessageService(SqlAlchemyMessageUnitOfWork(db))