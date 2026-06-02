from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.models import User
from .models import Project, ProjectMember, ProjectRole


class ProjectRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, project_id: str) -> Project | None:
        result = await self.db.execute(
            select(Project).where(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def list_by_workspace(self, workspace_id: str) -> list[Project]:
        result = await self.db.execute(
            select(Project).where(Project.workspace_id == workspace_id)
        )
        return list(result.scalars().all())

    async def list_by_workspace_for_user(
        self, workspace_id: str, user_id: str
    ) -> list[Project]:
        """Return only the projects in a workspace where user_id is a member."""
        result = await self.db.execute(
            select(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(
                Project.workspace_id == workspace_id,
                ProjectMember.user_id == user_id,
            )
        )
        return list(result.scalars().all())

    async def create(self, **kwargs) -> Project:
        project = Project(**kwargs)
        self.db.add(project)
        await self.db.flush()
        await self.db.refresh(project)
        return project

    async def update(self, project: Project, **kwargs) -> Project:
        for key, value in kwargs.items():
            setattr(project, key, value)
        await self.db.flush()
        await self.db.refresh(project)
        return project

    async def delete(self, project: Project) -> None:
        await self.db.delete(project)
        await self.db.flush()


class ProjectMemberRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_project_and_user(
        self, project_id: str, user_id: str
    ) -> ProjectMember | None:
        result = await self.db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_project(self, project_id: str) -> list[ProjectMember]:
        result = await self.db.execute(
            select(ProjectMember).where(ProjectMember.project_id == project_id)
        )
        return list(result.scalars().all())

    async def count_by_role(self, project_id: str, role: ProjectRole) -> int:
        result = await self.db.execute(
            select(func.count()).where(
                ProjectMember.project_id == project_id,
                ProjectMember.role == role,
            )
        )
        return result.scalar_one()

    async def list_by_project_with_users(self, project_id: str) -> list[tuple[ProjectMember, User]]:
        result = await self.db.execute(
            select(ProjectMember, User)
            .join(User, User.id == ProjectMember.user_id)
            .where(ProjectMember.project_id == project_id)
        )
        return list(result.all())

    async def create(self, **kwargs) -> ProjectMember:
        member = ProjectMember(**kwargs)
        self.db.add(member)
        await self.db.flush()
        await self.db.refresh(member)
        return member

    async def update(self, member: ProjectMember, **kwargs) -> ProjectMember:
        for key, value in kwargs.items():
            setattr(member, key, value)
        await self.db.flush()
        await self.db.refresh(member)
        return member

    async def delete(self, member: ProjectMember) -> None:
        await self.db.delete(member)
        await self.db.flush()