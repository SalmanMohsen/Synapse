import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.uow import SqlAlchemyUnitOfWork
from app.auth.models import User
from app.auth.service import AuthService
from app.database import get_db

async def get_redis(request: Request) -> aioredis.Redis:
    """Pull the Redis client that was stored on app.state at startup."""
    return request.app.state.redis

async def get_auth_service(
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis),
) -> AuthService:
    return AuthService(SqlAlchemyUnitOfWork(db), redis)

async def get_current_user(
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> User:
    """
    FastAPI dependency that all protected routes depend on.
    Reads the httpOnly access_token cookie — never touches Authorization header.
    Returns the authenticated User model or raises 401.
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Not authenticated"
        )
    return await service.get_user_from_access_token(token)