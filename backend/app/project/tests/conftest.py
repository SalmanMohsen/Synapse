"""
Project test fixtures.

Fake repositories are in-memory stand-ins for the SQLAlchemy repos.
Each fake mirrors the real repo interface exactly so tests exercise
the service layer in isolation with no database.

The UoW includes workspace repos because the service verifies workspace
existence and ownership on every operation.

Design note: FakeProjectRepository receives a reference to
FakeProjectMemberRepository so list_by_workspace_for_user can filter
correctly without a real SQL JOIN — the UoW wires this up at construction.
"""
import pytest

from app.project.models import ProjectRole
from app.project.service import ProjectService
from app.project.tests.helpers import make_project, make_project_member
from app.workspace.tests.helpers import make_workspace, make_workspace_member


# ── Fake workspace repos (only the methods the project service calls) ─────────

class FakeWorkspaceRepository:
    def __init__(self):
        self._workspaces: dict[str, object] = {}

    def seed(self, workspace) -> None:
        self._workspaces[workspace.id] = workspace

    async def get_by_id(self, workspace_id: str):
        return self._workspaces.get(workspace_id)


class FakeWorkspaceMemberRepository:
    def __init__(self):
        self._members: dict[tuple[str, str], object] = {}

    def seed(self, member) -> None:
        self._members[(member.workspace_id, member.user_id)] = member

    async def get_by_workspace_and_user(self, workspace_id: str, user_id: str):
        return self._members.get((workspace_id, user_id))


# ── Fake project repos ────────────────────────────────────────────────────────

class FakeProjectMemberRepository:
    def __init__(self):
        self._members: dict[tuple[str, str], object] = {}

    def seed(self, member) -> None:
        self._members[(member.project_id, member.user_id)] = member

    async def get_by_project_and_user(self, project_id: str, user_id: str):
        return self._members.get((project_id, user_id))

    async def list_by_project(self, project_id: str) -> list:
        return [m for m in self._members.values() if m.project_id == project_id]

    async def count_by_role(self, project_id: str, role: ProjectRole) -> int:
        return sum(
            1
            for m in self._members.values()
            if m.project_id == project_id and m.role == role
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


class FakeProjectRepository:
    """
    Receives a reference to FakeProjectMemberRepository so
    list_by_workspace_for_user can replicate the SQL JOIN in memory.
    The UoW passes the shared member repo instance at construction.
    """
    def __init__(self, member_repo: FakeProjectMemberRepository):
        self._projects: dict[str, object] = {}
        self._member_repo = member_repo

    def seed(self, project) -> None:
        self._projects[project.id] = project

    async def get_by_id(self, project_id: str):
        return self._projects.get(project_id)

    async def list_by_workspace(self, workspace_id: str) -> list:
        return [p for p in self._projects.values() if p.workspace_id == workspace_id]

    async def list_by_workspace_for_user(self, workspace_id: str, user_id: str) -> list:
        user_project_ids = {
            m.project_id
            for m in self._member_repo._members.values()
            if m.user_id == user_id
        }
        return [
            p for p in self._projects.values()
            if p.workspace_id == workspace_id and p.id in user_project_ids
        ]

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


# ── Fake UoW ──────────────────────────────────────────────────────────────────

class FakeProjectUnitOfWork:
    def __init__(
        self,
        workspace_repo: FakeWorkspaceRepository | None = None,
        workspace_member_repo: FakeWorkspaceMemberRepository | None = None,
        project_member_repo: FakeProjectMemberRepository | None = None,
    ):
        self.workspaces = workspace_repo or FakeWorkspaceRepository()
        self.workspace_members = workspace_member_repo or FakeWorkspaceMemberRepository()
        self.project_members = project_member_repo or FakeProjectMemberRepository()
        # project repo receives member repo reference for list_by_workspace_for_user
        self.projects = FakeProjectRepository(self.project_members)
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


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def workspace_repo():
    return FakeWorkspaceRepository()


@pytest.fixture
def workspace_member_repo():
    return FakeWorkspaceMemberRepository()


@pytest.fixture
def project_member_repo():
    return FakeProjectMemberRepository()


@pytest.fixture
def fake_uow(workspace_repo, workspace_member_repo, project_member_repo):
    uow = FakeProjectUnitOfWork(workspace_repo, workspace_member_repo, project_member_repo)
    return uow


@pytest.fixture
def project_service(fake_uow):
    return ProjectService(fake_uow)