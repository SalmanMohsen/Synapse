from sqlalchemy.ext.asyncio import AsyncSession

from app.UoW import AbstractUnitOfWork
from app.auth.repository import UserRepository
from app.channel.repository import ChannelMemberRepository, ChannelRepository
from app.project.repository import ProjectMemberRepository, ProjectRepository
from app.workspace.repository import WorkspaceMemberRepository, WorkspaceRepository

from .repository import InboxItemRepository


class AbstractInboxUnitOfWork(AbstractUnitOfWork):
    inbox_items: InboxItemRepository
    # Read-only lookups for validation and title generation
    users: UserRepository
    workspaces: WorkspaceRepository
    workspace_members: WorkspaceMemberRepository
    projects: ProjectRepository
    project_members: ProjectMemberRepository
    channels: ChannelRepository
    channel_members: ChannelMemberRepository


class SqlAlchemyInboxUnitOfWork(AbstractInboxUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.inbox_items = InboxItemRepository(session)
        self.users = UserRepository(session)
        self.workspaces = WorkspaceRepository(session)
        self.workspace_members = WorkspaceMemberRepository(session)
        self.projects = ProjectRepository(session)
        self.project_members = ProjectMemberRepository(session)
        self.channels = ChannelRepository(session)
        self.channel_members = ChannelMemberRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()