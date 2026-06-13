import redis.asyncio as aioredis
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_redis
from app.database import get_db

from .service import MessageService
from .uow import SqlAlchemyMessageUnitOfWork


async def get_message_service(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> MessageService:
    return MessageService(SqlAlchemyMessageUnitOfWork(db), redis)