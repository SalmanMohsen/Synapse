from sqlalchemy.ext.asyncio import AsyncSession

from app.UoW import AbstractUnitOfWork
from app.project.repository import ProjectMemberRepository, ProjectRepository
from app.workspace.repository import WorkspaceMemberRepository

from .repository import ChannelMemberRepository, ChannelRepository


class AbstractChannelUnitOfWork(AbstractUnitOfWork):
    # Cross-module repos are included so the service can verify project
    # existence, team-lead status, and workspace ownership in one DB
    # session — the same pattern used by ProjectUnitOfWork.
    workspace_members: WorkspaceMemberRepository
    projects: ProjectRepository
    project_members: ProjectMemberRepository
    channels: ChannelRepository
    channel_members: ChannelMemberRepository


class SqlAlchemyChannelUnitOfWork(AbstractChannelUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.workspace_members = WorkspaceMemberRepository(session)
        self.projects = ProjectRepository(session)
        self.project_members = ProjectMemberRepository(session)
        self.channels = ChannelRepository(session)
        self.channel_members = ChannelMemberRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()