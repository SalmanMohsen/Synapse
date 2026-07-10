from sqlalchemy.ext.asyncio import AsyncSession
from app.UoW import AbstractUnitOfWork
from app.skill.repository import SkillRepository
from app.channel.repository import ChannelRepository, ChannelMemberRepository
from app.project.repository import ProjectRepository, ProjectMemberRepository
from app.workspace.repository import WorkspaceMemberRepository

class AbstractSkillUnitOfWork(AbstractUnitOfWork):
    skills: SkillRepository
    channels: ChannelRepository
    channel_members: ChannelMemberRepository
    projects: ProjectRepository
    project_members: ProjectMemberRepository
    workspace_members: WorkspaceMemberRepository

class SqlAlchemySkillUnitOfWork(AbstractSkillUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.skills = SkillRepository(session)
        self.channels = ChannelRepository(session)
        self.channel_members = ChannelMemberRepository(session)
        self.projects = ProjectRepository(session)
        self.project_members = ProjectMemberRepository(session)
        self.workspace_members = WorkspaceMemberRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()