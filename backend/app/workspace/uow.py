from sqlalchemy.ext.asyncio import AsyncSession

from app.UoW import AbstractUnitOfWork
from app.channel.repository import ChannelMemberRepository, ChannelRepository
from app.project.repository import ProjectMemberRepository, ProjectRepository

from .repository import WorkspaceMemberRepository, WorkspaceRepository


class AbstractWorkspaceUnitOfWork(AbstractUnitOfWork):
    workspaces: WorkspaceRepository
    members: WorkspaceMemberRepository
    # Needed to cascade-clean project and channel memberships when a workspace
    # member is removed (Fix #5).
    projects: ProjectRepository
    project_members: ProjectMemberRepository
    channels: ChannelRepository
    channel_members: ChannelMemberRepository


class SqlAlchemyWorkspaceUnitOfWork(AbstractWorkspaceUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.workspaces = WorkspaceRepository(session)
        self.members = WorkspaceMemberRepository(session)
        self.projects = ProjectRepository(session)
        self.project_members = ProjectMemberRepository(session)
        self.channels = ChannelRepository(session)
        self.channel_members = ChannelMemberRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()