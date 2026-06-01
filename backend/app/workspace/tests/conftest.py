"""
Workspace test fixtures.

Fake repositories are in-memory stand-ins for the SQLAlchemy repos.
Each fake mirrors the real repo interface exactly so tests exercise
the service layer in isolation with no database.

Changes vs original:
- FakeWorkspaceInviteRepository removed (invites now live in inbox module).
- FakeProjectRepository, FakeProjectMemberRepository, FakeChannelRepository,
  FakeChannelMemberRepository added so remove_member cascade (Fix #5) can be
  exercised without a real DB.
- FakeWorkspaceMemberRepository gets list_owners_except (used by project
  service for owner notifications — not needed here but kept consistent).
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.workspace.service import WorkspaceService
from app.workspace.tests.helpers import make_workspace, make_workspace_member


# ── Fake repositories ─────────────────────────────────────────────────────────


class FakeWorkspaceRepository:
    def __init__(self):
        self._workspaces: dict[str, object] = {}

    def seed(self, workspace) -> None:
        self._workspaces[workspace.id] = workspace

    async def get_by_id(self, workspace_id: str):
        return self._workspaces.get(workspace_id)

    async def create(self, **kwargs) -> object:
        ws = make_workspace(**kwargs)
        self.seed(ws)
        return ws

    async def update(self, workspace, **kwargs) -> object:
        for k, v in kwargs.items():
            setattr(workspace, k, v)
        return workspace

    async def delete(self, workspace) -> None:
        self._workspaces.pop(workspace.id, None)


class FakeWorkspaceMemberRepository:
    def __init__(self):
        # key: (workspace_id, user_id)
        self._members: dict[tuple[str, str], object] = {}

    def seed(self, member) -> None:
        self._members[(member.workspace_id, member.user_id)] = member

    async def get_by_workspace_and_user(self, workspace_id: str, user_id: str):
        return self._members.get((workspace_id, user_id))

    async def list_by_workspace(self, workspace_id: str) -> list:
        return [m for m in self._members.values() if m.workspace_id == workspace_id]

    async def list_owners_except(self, workspace_id: str, exclude_user_id: str) -> list:
        return [
            m for m in self._members.values()
            if m.workspace_id == workspace_id
            and m.is_owner
            and m.user_id != exclude_user_id
        ]

    async def count_owners(self, workspace_id: str) -> int:
        return sum(
            1
            for m in self._members.values()
            if m.workspace_id == workspace_id and m.is_owner
        )

    async def create(self, **kwargs) -> object:
        member = make_workspace_member(**kwargs)
        self.seed(member)
        return member

    async def update(self, member, **kwargs) -> object:
        for k, v in kwargs.items():
            setattr(member, k, v)
        return member

    async def delete(self, member) -> None:
        self._members.pop((member.workspace_id, member.user_id), None)


class FakeProjectRepository:
    """Minimal project repo for cascade testing in remove_member."""

    def __init__(self):
        self._projects: dict[str, object] = {}

    def seed(self, project) -> None:
        self._projects[project.id] = project

    async def list_by_workspace(self, workspace_id: str) -> list:
        return [p for p in self._projects.values() if p.workspace_id == workspace_id]


class FakeProjectMemberRepository:
    """Minimal project member repo for cascade testing."""

    def __init__(self):
        # key: (project_id, user_id)
        self._members: dict[tuple[str, str], object] = {}

    def seed(self, member) -> None:
        self._members[(member.project_id, member.user_id)] = member

    async def get_by_project_and_user(self, project_id: str, user_id: str):
        return self._members.get((project_id, user_id))

    async def delete(self, member) -> None:
        self._members.pop((member.project_id, member.user_id), None)


class FakeChannelRepository:
    """Minimal channel repo for cascade testing."""

    def __init__(self):
        self._channels: dict[str, object] = {}

    def seed(self, channel) -> None:
        self._channels[channel.id] = channel

    async def list_by_project(self, project_id: str) -> list:
        return [c for c in self._channels.values() if c.project_id == project_id]


class FakeChannelMemberRepository:
    """Minimal channel member repo for cascade testing."""

    def __init__(self):
        # key: (channel_id, user_id)
        self._members: dict[tuple[str, str], object] = {}

    def seed(self, member) -> None:
        self._members[(member.channel_id, member.user_id)] = member

    async def get_by_channel_and_user(self, channel_id: str, user_id: str):
        return self._members.get((channel_id, user_id))

    async def delete(self, member) -> None:
        self._members.pop((member.channel_id, member.user_id), None)


# ── Fake UoW ──────────────────────────────────────────────────────────────────


class FakeWorkspaceUnitOfWork:
    def __init__(
        self,
        workspace_repo: FakeWorkspaceRepository | None = None,
        member_repo: FakeWorkspaceMemberRepository | None = None,
        project_repo: FakeProjectRepository | None = None,
        project_member_repo: FakeProjectMemberRepository | None = None,
        channel_repo: FakeChannelRepository | None = None,
        channel_member_repo: FakeChannelMemberRepository | None = None,
    ):
        self.workspaces = workspace_repo or FakeWorkspaceRepository()
        self.members = member_repo or FakeWorkspaceMemberRepository()
        self.projects = project_repo or FakeProjectRepository()
        self.project_members = project_member_repo or FakeProjectMemberRepository()
        self.channels = channel_repo or FakeChannelRepository()
        self.channel_members = channel_member_repo or FakeChannelMemberRepository()
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
def member_repo():
    return FakeWorkspaceMemberRepository()


@pytest.fixture
def project_repo():
    return FakeProjectRepository()


@pytest.fixture
def project_member_repo():
    return FakeProjectMemberRepository()


@pytest.fixture
def channel_repo():
    return FakeChannelRepository()


@pytest.fixture
def channel_member_repo():
    return FakeChannelMemberRepository()


@pytest.fixture
def fake_uow(
    workspace_repo,
    member_repo,
    project_repo,
    project_member_repo,
    channel_repo,
    channel_member_repo,
):
    return FakeWorkspaceUnitOfWork(
        workspace_repo=workspace_repo,
        member_repo=member_repo,
        project_repo=project_repo,
        project_member_repo=project_member_repo,
        channel_repo=channel_repo,
        channel_member_repo=channel_member_repo,
    )


@pytest.fixture
def workspace_service(fake_uow):
    return WorkspaceService(fake_uow)