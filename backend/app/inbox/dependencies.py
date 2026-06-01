from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

from .service import InboxService
from .uow import SqlAlchemyInboxUnitOfWork


async def get_inbox_service(db: AsyncSession = Depends(get_db)) -> InboxService:
    return InboxService(SqlAlchemyInboxUnitOfWork(db))