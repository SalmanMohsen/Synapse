from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

from .service import ProjectService
from .uow import SqlAlchemyProjectUnitOfWork


async def get_project_service(
    db: AsyncSession = Depends(get_db),
) -> ProjectService:
    return ProjectService(SqlAlchemyProjectUnitOfWork(db))