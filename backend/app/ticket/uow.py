from sqlalchemy.ext.asyncio import AsyncSession

from app.UoW import AbstractUnitOfWork
from app.agent_run.repository import AgentRunRepository
from app.auth.repository import UserRepository
from app.channel.repository import ChannelMemberRepository, ChannelRepository
from app.inbox.repository import InboxItemRepository
from app.message.repository import MessageRepository
from app.project.repository import ProjectMemberRepository, ProjectRepository
from app.skill.repository import SkillRepository
from app.thread_state.repository import ThreadStateRepository
from app.workspace.repository import WorkspaceMemberRepository

from .repository import TicketRepository


class AbstractTicketUnitOfWork(AbstractUnitOfWork):
    workspace_members: WorkspaceMemberRepository
    projects: ProjectRepository
    project_members: ProjectMemberRepository
    channels: ChannelRepository
    channel_members: ChannelMemberRepository
    tickets: TicketRepository
    messages: MessageRepository
    thread_states: ThreadStateRepository
    inbox_items: InboxItemRepository
    users: UserRepository
    skills: SkillRepository
    agent_runs: AgentRunRepository


class SqlAlchemyTicketUnitOfWork(AbstractTicketUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.workspace_members = WorkspaceMemberRepository(session)
        self.projects = ProjectRepository(session)
        self.project_members = ProjectMemberRepository(session)
        self.channels = ChannelRepository(session)
        self.channel_members = ChannelMemberRepository(session)
        self.tickets = TicketRepository(session)
        self.messages = MessageRepository(session)
        self.thread_states = ThreadStateRepository(session)
        self.inbox_items = InboxItemRepository(session)
        self.users = UserRepository(session)
        self.skills = SkillRepository(session)
        self.agent_runs = AgentRunRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()