"""
Workspace test fixtures.

Fake repositories are in-memory stand-ins for the SQLAlchemy repos.
Each fake mirrors the real repo interface exactly so tests exercise
the service layer in isolation with no database.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.workspace.tests.helpers import (
    make_workspace,
    make_workspace_invite,
    make_workspace_member,
)


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


class FakeWorkspaceInviteRepository:
    def __init__(self):
        self._invites: dict[str, object] = {}  # keyed by token

    def seed(self, invite) -> None:
        self._invites[invite.token] = invite

    async def get_by_token(self, token: str):
        return self._invites.get(token)

    async def create(self, **kwargs) -> object:
        invite = make_workspace_invite(**kwargs)
        self.seed(invite)
        return invite

    async def mark_used(self, invite) -> object:
        invite.used_at = datetime.now(timezone.utc)
        return invite


# ── Fake UoW ──────────────────────────────────────────────────────────────────


class FakeWorkspaceUnitOfWork:
    def __init__(
        self,
        workspace_repo: FakeWorkspaceRepository | None = None,
        member_repo: FakeWorkspaceMemberRepository | None = None,
        invite_repo: FakeWorkspaceInviteRepository | None = None,
    ):
        self.workspaces = workspace_repo or FakeWorkspaceRepository()
        self.members = member_repo or FakeWorkspaceMemberRepository()
        self.invites = invite_repo or FakeWorkspaceInviteRepository()
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
def invite_repo():
    return FakeWorkspaceInviteRepository()


@pytest.fixture
def fake_uow(workspace_repo, member_repo, invite_repo):
    return FakeWorkspaceUnitOfWork(workspace_repo, member_repo, invite_repo)


@pytest.fixture
def workspace_service(fake_uow):
    from app.workspace.service import WorkspaceService
    return WorkspaceService(fake_uow)