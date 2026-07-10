from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.skill.uow import SqlAlchemySkillUnitOfWork
from app.skill.service import SkillService

async def get_skill_service(db: AsyncSession = Depends(get_db)) -> SkillService:
    return SkillService(SqlAlchemySkillUnitOfWork(db))