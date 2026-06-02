from sqlalchemy.ext.asyncio import AsyncSession
from app.UoW import AbstractUnitOfWork
from app.channel.repository import ChannelRepository, ChannelMemberRepository
from app.inbox.repository import InboxItemRepository
from app.workspace.repository import WorkspaceMemberRepository, WorkspaceRepository

from .repository import ProjectMemberRepository, ProjectRepository


class AbstractProjectUnitOfWork(AbstractUnitOfWork):
    workspaces: WorkspaceRepository
    workspace_members: WorkspaceMemberRepository
    projects: ProjectRepository
    project_members: ProjectMemberRepository
    channels: ChannelRepository
    channel_members: ChannelMemberRepository
    inbox_items: InboxItemRepository


class SqlAlchemyProjectUnitOfWork(AbstractProjectUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.workspaces = WorkspaceRepository(session)
        self.workspace_members = WorkspaceMemberRepository(session)
        self.projects = ProjectRepository(session)
        self.project_members = ProjectMemberRepository(session)
        self.channels = ChannelRepository(session)
        self.channel_members = ChannelMemberRepository(session)
        self.inbox_items = InboxItemRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()