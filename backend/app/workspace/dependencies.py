import redis.asyncio as aioredis
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_redis, get_current_user
from app.database import get_db

from .service import WorkspaceService
from .uow import SqlAlchemyWorkspaceUnitOfWork


async def get_workspace_service(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> WorkspaceService:
    return WorkspaceService(SqlAlchemyWorkspaceUnitOfWork(db), redis)