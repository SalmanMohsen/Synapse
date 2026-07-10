from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.skill.models import SkillFile, SkillAssignment, SkillDimension
from app.channel.models import ChannelDiscipline

class SkillRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_file_by_id(self, file_id: str) -> SkillFile | None:
        result = await self.db.execute(select(SkillFile).where(SkillFile.id == file_id))
        return result.scalar_one_or_none()

    async def get_specialty_file(self, workspace_id: str, discipline: ChannelDiscipline) -> SkillFile | None:
        result = await self.db.execute(
            select(SkillFile).where(
                SkillFile.workspace_id == workspace_id,
                SkillFile.dimension == SkillDimension.specialty,
                SkillFile.discipline == discipline
            )
        )
        return result.scalar_one_or_none()

    async def list_files_by_workspace(self, workspace_id: str) -> list[SkillFile]:
        result = await self.db.execute(select(SkillFile).where(SkillFile.workspace_id == workspace_id))
        return list(result.scalars().all())

    async def create_file(self, **kwargs) -> SkillFile:
        skill_file = SkillFile(**kwargs)
        self.db.add(skill_file)
        await self.db.flush()
        await self.db.refresh(skill_file)
        return skill_file

    async def get_assignment_by_channel(self, channel_id: str) -> SkillAssignment | None:
        result = await self.db.execute(select(SkillAssignment).where(SkillAssignment.channel_id == channel_id))
        return result.scalar_one_or_none()

    async def create_assignment(self, **kwargs) -> SkillAssignment:
        assignment = SkillAssignment(**kwargs)
        self.db.add(assignment)
        await self.db.flush()
        await self.db.refresh(assignment)
        return assignment

    async def update_assignment(self, assignment: SkillAssignment, **kwargs) -> SkillAssignment:
        for key, value in kwargs.items():
            setattr(assignment, key, value)
        await self.db.flush()
        await self.db.refresh(assignment)
        return assignment