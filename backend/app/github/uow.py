# backend/app/github/uow.py (new file)
from sqlalchemy.ext.asyncio import AsyncSession
from app.UoW import AbstractUnitOfWork
from app.project.repository import ProjectRepository, ProjectMemberRepository
from app.workspace.repository import WorkspaceMemberRepository
from app.channel.repository import ChannelRepository, ChannelMemberRepository
from app.ticket.repository import TicketRepository
from app.message.repository import MessageRepository
from app.thread_state.repository import ThreadStateRepository
from app.inbox.repository import InboxItemRepository
from app.auth.repository import UserRepository

from .repository import GitIntegrationRepository, WebhookEventRepository


class AbstractGitIntegrationUnitOfWork(AbstractUnitOfWork):
    git_integrations: GitIntegrationRepository
    webhook_events: WebhookEventRepository
    projects: ProjectRepository
    project_members: ProjectMemberRepository
    workspace_members: WorkspaceMemberRepository
    channels: ChannelRepository
    channel_members: ChannelMemberRepository
    tickets: TicketRepository
    messages: MessageRepository
    thread_states: ThreadStateRepository
    inbox_items: InboxItemRepository
    users: UserRepository


class SqlAlchemyGitIntegrationUnitOfWork(AbstractGitIntegrationUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.git_integrations = GitIntegrationRepository(session)
        self.webhook_events = WebhookEventRepository(session)
        self.projects = ProjectRepository(session)
        self.project_members = ProjectMemberRepository(session)
        self.workspace_members = WorkspaceMemberRepository(session)
        self.channels = ChannelRepository(session)
        self.channel_members = ChannelMemberRepository(session)
        self.tickets = TicketRepository(session)
        self.messages = MessageRepository(session)
        self.thread_states = ThreadStateRepository(session)
        self.inbox_items = InboxItemRepository(session)
        self.users = UserRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()