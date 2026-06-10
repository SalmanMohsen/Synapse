from sqlalchemy.ext.asyncio import AsyncSession

from app.UoW import AbstractUnitOfWork
from app.channel.repository import ChannelMemberRepository, ChannelRepository
from app.project.repository import ProjectMemberRepository, ProjectRepository
from app.workspace.repository import WorkspaceMemberRepository

from .repository import TicketRepository


class AbstractTicketUnitOfWork(AbstractUnitOfWork):
    workspace_members: WorkspaceMemberRepository
    projects: ProjectRepository
    project_members: ProjectMemberRepository
    channels: ChannelRepository
    channel_members: ChannelMemberRepository
    tickets: TicketRepository


class SqlAlchemyTicketUnitOfWork(AbstractTicketUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.workspace_members = WorkspaceMemberRepository(session)
        self.projects = ProjectRepository(session)
        self.project_members = ProjectMemberRepository(session)
        self.channels = ChannelRepository(session)
        self.channel_members = ChannelMemberRepository(session)
        self.tickets = TicketRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()