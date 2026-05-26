import pytest
from datetime import datetime, timezone 
from app.project.service import ProjectService
from app.project.tests.helpers import (
    make_project,
    make_project_member
)

# ── Fake repositories ─────────────────────────────────────────────────────────

class FakeProjectRepository:
    def __init__(self):
        self._projects: dict[str, object] = {}

    def seed(self, project) -> None:
        self._projects[project.id] = project

    async def get_by_id(self, project_id: str):
        return self._projects.get(project_id)

    async def list_by_workspace(self, workspace_id: str) -> list:
        return [p for p in self._projects.values() if p.workspace_id == workspace_id]

    async def create(self, **kwargs) -> object:
        project = make_project(**kwargs)
        self.seed(project)
        return project

    async def update(self, project, **kwargs) -> object:
        for k, v in kwargs.items():
            setattr(project, k, v)
        return project

    async def delete(self, project) -> None:
        self._projects.pop(project.id, None)

class FakeProjectMemberRepository:
    def __init__(self):
        # key: (project_id, user_id)
        self._members: dict[tuple[str, str], object] = {}

    def seed(self, member) -> None:
        self._members[(member.project_id, member.user_id)] = member

    async def get_by_project_and_user(self, project_id: str, user_id: str):
        return self._members.get((project_id, user_id))

    async def list_by_project(self, project_id: str) -> list:
        return [m for m in self._members.values() if m.project_id == project_id]

    async def count_owners(self, project_id: str) -> int:
        return sum(
            1
            for m in self._members.values()
            if m.project_id == project_id and m.is_owner
        )
    async def create(self, **kwargs) -> object:
        member = make_project_member(**kwargs)
        self.seed(member)
        return member
    async def update(self, member, **kwargs) -> object:
        for k, v in kwargs.items():
            setattr(member, k, v)
        return member
    async def delete(self, member) -> None:
        self._members.pop((member.project_id, member.user_id), None)
    
# Fake UoW

class FakeProjectUnitOfWork:
    def __init__(
        self,
        project_repo: FakeProjectRepository | None = None,
        member_repo: FakeProjectMemberRepository | None = None,
    ):
        self.projects = project_repo or FakeProjectRepository()
        self.members = member_repo or FakeProjectMemberRepository()
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            await self.rollback()

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

# Fake fixtures

@pytest.fixture
def project_repo():
    return FakeProjectRepository()

@pytest.fixture
def project_member_repo():
    return FakeProjectMemberRepository()

@pytest.fixture
def fake_uow(project_repo, project_member_repo):
    return FakeProjectUnitOfWork(project_repo, project_member_repo)

@pytest.fixture
def project_service(fake_uow):
    return ProjectService(fake_uow)