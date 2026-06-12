from sqlalchemy.ext.asyncio import AsyncSession

from app.UoW import AbstractUnitOfWork
from app.auth.repository import UserRepository
from app.channel.repository import ChannelMemberRepository, ChannelRepository
from app.project.repository import ProjectMemberRepository, ProjectRepository
from app.ticket.repository import TicketRepository
from app.workspace.repository import WorkspaceMemberRepository

from .repository import MessageRepository


class AbstractMessageUnitOfWork(AbstractUnitOfWork):
    messages: MessageRepository
    tickets: TicketRepository
    channels: ChannelRepository
    channel_members: ChannelMemberRepository
    projects: ProjectRepository
    project_members: ProjectMemberRepository
    workspace_members: WorkspaceMemberRepository
    users: UserRepository


class SqlAlchemyMessageUnitOfWork(AbstractMessageUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.messages = MessageRepository(session)
        self.tickets = TicketRepository(session)
        self.channels = ChannelRepository(session)
        self.channel_members = ChannelMemberRepository(session)
        self.projects = ProjectRepository(session)
        self.project_members = ProjectMemberRepository(session)
        self.workspace_members = WorkspaceMemberRepository(session)
        self.users = UserRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()