from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

from .service import ChannelService
from .uow import SqlAlchemyChannelUnitOfWork


async def get_channel_service(
    db: AsyncSession = Depends(get_db),
) -> ChannelService:
    return ChannelService(SqlAlchemyChannelUnitOfWork(db))