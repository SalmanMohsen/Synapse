# backend/app/github/dependencies.py (new file)
import redis.asyncio as aioredis
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_redis
from app.database import get_db

from .service import GitIntegrationService
from .uow import SqlAlchemyGitIntegrationUnitOfWork


async def get_git_integration_service(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> GitIntegrationService:
    return GitIntegrationService(SqlAlchemyGitIntegrationUnitOfWork(db), redis)