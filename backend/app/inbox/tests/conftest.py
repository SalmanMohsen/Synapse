"""
Inbox test fixtures.

The InboxService touches six repos across four domain modules (inbox,
workspace, project, channel). All of them are faked in-memory here.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.inbox.models import InboxItem, InboxItemStatus, InboxItemType
from app.inbox.service import InboxService


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_item(
    *,
    id: str | None = None,
    user_id: str = "user-1",
    type: InboxItemType = InboxItemType.workspace_invite,
    status: InboxItemStatus = InboxItemStatus.pending,
    sender_id: str | None = "sender-1",
    workspace_id: str | None = "ws-1",
    project_id: str | None = None,
    channel_id: str | None = None,
    role: str | None = "member",
    title: str = "Test invite",
    body: str | None = None,
    expires_at: datetime | None = None,
) -> MagicMock:
    item = MagicMock(spec=InboxItem)
    item.id = id or str(uuid.uuid4())
    item.user_id = user_id
    item.type = type
    item.status = status
    item.sender_id = sender_id
    item.workspace_id = workspace_id
    item.project_id = project_id
    item.channel_id = channel_id
    item.role = role
    item.title = title
    item.body = body
    item.entity_type = None
    item.entity_id = None
    item.expires_at = expires_at or datetime.now(timezone.utc) + timedelta(days=7)
    item.created_at = datetime.now(timezone.utc)
    return item


def _make_user(user_id: str = "user-1") -> MagicMock:
    u = MagicMock()
    u.id = user_id
    return u


def _make_ws_member(workspace_id: str, user_id: str, is_owner: bool = False) -> MagicMock:
    m = MagicMock()
    m.workspace_id = workspace_id
    m.user_id = user_id
    m.is_owner = is_owner
    return m


def _make_project(workspace_id: str, project_id: str) -> MagicMock:
    p = MagicMock()
    p.id = project_id
    p.workspace_id = workspace_id
    p.name = "Test Project"
    return p


def _make_project_member(project_id: str, user_id: str, role: str = "member") -> MagicMock:
    m = MagicMock()
    m.project_id = project_id
    m.user_id = user_id
    m.role = role
    return m


def _make_channel(project_id: str, channel_id: str, is_leads_channel: bool = False) -> MagicMock:
    c = MagicMock()
    c.id = channel_id
    c.project_id = project_id
    c.name = "Test Channel"
    c.is_leads_channel = is_leads_channel
    return c


def _make_channel_member(channel_id: str, user_id: str, role: str = "member") -> MagicMock:
    m = MagicMock()
    m.channel_id = channel_id
    m.user_id = user_id
    m.role = role
    return m


# ── Fake repos ────────────────────────────────────────────────────────────────


class FakeInboxItemRepository:
    def __init__(self):
        self._items: dict[str, object] = {}

    def seed(self, item) -> None:
        self._items[item.id] = item

    async def get_by_id(self, item_id: str):
        return self._items.get(item_id)

    async def list_by_user(self, user_id: str) -> list:
        return [i for i in self._items.values() if i.user_id == user_id]

    async def list_pending_invites_for_target(
        self, target_user_id, workspace_id=None, project_id=None, channel_id=None
    ) -> list:
        results = []
        for item in self._items.values():
            if item.user_id != target_user_id:
                continue
            if item.status != InboxItemStatus.pending:
                continue
            if item.type not in (
                InboxItemType.workspace_invite,
                InboxItemType.project_invite,
                InboxItemType.channel_invite,
            ):
                continue
            if workspace_id and item.workspace_id != workspace_id:
                continue
            if project_id and item.project_id != project_id:
                continue
            if channel_id and item.channel_id != channel_id:
                continue
            results.append(item)
        return results

    async def create(self, **kwargs) -> object:
        item = _make_item(**{k: v for k, v in kwargs.items() if k in _make_item.__code__.co_varnames})
        # Preserve all kwargs directly for full fidelity
        for k, v in kwargs.items():
            setattr(item, k, v)
        item.id = str(uuid.uuid4())
        self.seed(item)
        return item

    async def update(self, item, **kwargs) -> object:
        for k, v in kwargs.items():
            setattr(item, k, v)
        return item

    async def expire_stale(self, item) -> object:
        item.status = InboxItemStatus.expired
        return item


class FakeUserRepository:
    def __init__(self):
        self._users: dict[str, object] = {}

    def seed(self, user) -> None:
        self._users[user.id] = user

    async def get_by_id(self, user_id: str):
        return self._users.get(user_id)


class FakeWorkspaceRepository:
    def __init__(self):
        self._workspaces: dict[str, object] = {}

    def seed(self, ws) -> None:
        self._workspaces[ws.id] = ws

    async def get_by_id(self, workspace_id: str):
        return self._workspaces.get(workspace_id)


class FakeWorkspaceMemberRepository:
    def __init__(self):
        self._members: dict[tuple[str, str], object] = {}

    def seed(self, m) -> None:
        self._members[(m.workspace_id, m.user_id)] = m

    async def get_by_workspace_and_user(self, workspace_id: str, user_id: str):
        return self._members.get((workspace_id, user_id))

    async def create(self, **kwargs) -> object:
        m = _make_ws_member(
            kwargs["workspace_id"], kwargs["user_id"], kwargs.get("is_owner", False)
        )
        self.seed(m)
        return m


class FakeProjectRepository:
    def __init__(self):
        self._projects: dict[str, object] = {}

    def seed(self, p) -> None:
        self._projects[p.id] = p

    async def get_by_id(self, project_id: str):
        return self._projects.get(project_id)


class FakeProjectMemberRepository:
    def __init__(self):
        self._members: dict[tuple[str, str], object] = {}

    def seed(self, m) -> None:
        self._members[(m.project_id, m.user_id)] = m

    async def get_by_project_and_user(self, project_id: str, user_id: str):
        return self._members.get((project_id, user_id))

    async def create(self, **kwargs) -> object:
        m = _make_project_member(kwargs["project_id"], kwargs["user_id"], kwargs.get("role", "member"))
        self.seed(m)
        return m


class FakeChannelRepository:
    def __init__(self):
        self._channels: dict[str, object] = {}

    def seed(self, c) -> None:
        self._channels[c.id] = c

    async def get_by_id(self, channel_id: str):
        return self._channels.get(channel_id)


class FakeChannelMemberRepository:
    def __init__(self):
        self._members: dict[tuple[str, str], object] = {}

    def seed(self, m) -> None:
        self._members[(m.channel_id, m.user_id)] = m

    async def get_by_channel_and_user(self, channel_id: str, user_id: str):
        return self._members.get((channel_id, user_id))

    async def create(self, **kwargs) -> object:
        m = _make_channel_member(kwargs["channel_id"], kwargs["user_id"], kwargs.get("role", "member"))
        self.seed(m)
        return m


# ── Fake UoW ──────────────────────────────────────────────────────────────────


class FakeInboxUnitOfWork:
    def __init__(
        self,
        inbox_items=None,
        users=None,
        workspaces=None,
        workspace_members=None,
        projects=None,
        project_members=None,
        channels=None,
        channel_members=None,
    ):
        self.inbox_items = inbox_items or FakeInboxItemRepository()
        self.users = users or FakeUserRepository()
        self.workspaces = workspaces or FakeWorkspaceRepository()
        self.workspace_members = workspace_members or FakeWorkspaceMemberRepository()
        self.projects = projects or FakeProjectRepository()
        self.project_members = project_members or FakeProjectMemberRepository()
        self.channels = channels or FakeChannelRepository()
        self.channel_members = channel_members or FakeChannelMemberRepository()
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        pass


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def inbox_repo():
    return FakeInboxItemRepository()


@pytest.fixture
def user_repo():
    return FakeUserRepository()


@pytest.fixture
def ws_repo():
    return FakeWorkspaceRepository()


@pytest.fixture
def ws_member_repo():
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
    inbox_repo,
    user_repo,
    ws_repo,
    ws_member_repo,
    project_repo,
    project_member_repo,
    channel_repo,
    channel_member_repo,
):
    return FakeInboxUnitOfWork(
        inbox_items=inbox_repo,
        users=user_repo,
        workspaces=ws_repo,
        workspace_members=ws_member_repo,
        projects=project_repo,
        project_members=project_member_repo,
        channels=channel_repo,
        channel_members=channel_member_repo,
    )


@pytest.fixture
def inbox_service(fake_uow):
    return InboxService(fake_uow)


# Re-export helpers so test files can import from conftest directly
make_item = _make_item
make_user = _make_user
make_ws_member = _make_ws_member
make_project = _make_project
make_project_member = _make_project_member
make_channel = _make_channel
make_channel_member = _make_channel_member