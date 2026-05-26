from sqlalchemy.ext.asyncio import AsyncSession

from app.UoW import AbstractUnitOfWork
from app.workspace.repository import WorkspaceMemberRepository, WorkspaceRepository

from .repository import ProjectMemberRepository, ProjectRepository


class AbstractProjectUnitOfWork(AbstractUnitOfWork):
    # Workspace repos are included so the service can verify workspace
    # existence and ownership without crossing module boundaries at the
    # service layer — all reads happen in one DB session / transaction.
    workspaces: WorkspaceRepository
    workspace_members: WorkspaceMemberRepository
    projects: ProjectRepository
    project_members: ProjectMemberRepository


class SqlAlchemyProjectUnitOfWork(AbstractProjectUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.workspaces = WorkspaceRepository(session)
        self.workspace_members = WorkspaceMemberRepository(session)
        self.projects = ProjectRepository(session)
        self.project_members = ProjectMemberRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()