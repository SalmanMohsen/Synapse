import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.auth.dependencies import get_current_user
from app.inbox.dependencies import get_inbox_service
from app.inbox.schemas import InboxItemRead
from app.inbox.models import InboxItemType, InboxItemStatus


def _fake_inbox_item_read(**overrides):
    return {
        "id": overrides.get("id", "item-1"),
        "user_id": overrides.get("user_id", "user-1"),
        "type": overrides.get("type", InboxItemType.workspace_invite),
        "status": overrides.get("status", InboxItemStatus.pending),
        "sender_id": overrides.get("sender_id", "sender-1"),
        "workspace_id": overrides.get("workspace_id", "ws-1"),
        "project_id": overrides.get("project_id", None),
        "channel_id": overrides.get("channel_id", None),
        "role": overrides.get("role", "member"),
        "title": overrides.get("title", "Invite Title"),
        "body": overrides.get("body", "Invite Body"),
        "entity_type": overrides.get("entity_type", None),
        "entity_id": overrides.get("entity_id", None),
        "expires_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


class TestInboxRouter:
    @pytest.fixture(autouse=True)
    def setup_overrides(self):
        self.mock_service = AsyncMock()
        self.mock_user = MagicMock()
        self.mock_user.id = "user-1"

        app.dependency_overrides[get_inbox_service] = lambda: self.mock_service
        app.dependency_overrides[get_current_user] = lambda: self.mock_user
        yield
        app.dependency_overrides.clear()

    def test_list_inbox(self):
        client = TestClient(app)
        fake_res = [InboxItemRead(**_fake_inbox_item_read())]
        self.mock_service.list_inbox.return_value = fake_res

        resp = client.get("/api/v1/inbox")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        self.mock_service.list_inbox.assert_awaited_once_with("user-1")

    def test_accept_invite(self):
        client = TestClient(app)
        fake_res = InboxItemRead(**_fake_inbox_item_read(status=InboxItemStatus.accepted))
        self.mock_service.accept_invite.return_value = fake_res

        resp = client.post("/api/v1/inbox/invites/item-1/accept")
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"
        self.mock_service.accept_invite.assert_awaited_once_with("item-1", "user-1")

    def test_decline_invite(self):
        client = TestClient(app)
        fake_res = InboxItemRead(**_fake_inbox_item_read(status=InboxItemStatus.declined))
        self.mock_service.decline_invite.return_value = fake_res

        resp = client.post("/api/v1/inbox/invites/item-1/decline")
        assert resp.status_code == 200
        assert resp.json()["status"] == "declined"
        self.mock_service.decline_invite.assert_awaited_once_with("item-1", "user-1")

    def test_mark_read(self):
        client = TestClient(app)
        fake_res = InboxItemRead(**_fake_inbox_item_read(status=InboxItemStatus.read, type=InboxItemType.notification))
        self.mock_service.mark_read.return_value = fake_res

        resp = client.patch("/api/v1/inbox/item-1/read")
        assert resp.status_code == 200
        assert resp.json()["status"] == "read"
        self.mock_service.mark_read.assert_awaited_once_with("item-1", "user-1")

    def test_send_workspace_invite(self):
        client = TestClient(app)
        fake_res = InboxItemRead(**_fake_inbox_item_read(user_id="user-2"))
        self.mock_service.send_workspace_invite.return_value = fake_res

        resp = client.post(
            "/api/v1/workspaces/ws-1/invites",
            json={"target_user_id": "user-2", "role": "member"},
        )
        assert resp.status_code == 201
        assert resp.json()["user_id"] == "user-2"
        self.mock_service.send_workspace_invite.assert_awaited_once_with("ws-1", "user-2", "member", "user-1")

    def test_send_project_invite(self):
        client = TestClient(app)
        fake_res = InboxItemRead(**_fake_inbox_item_read(user_id="user-2", project_id="project-1"))
        self.mock_service.send_project_invite.return_value = fake_res

        resp = client.post(
            "/api/v1/projects/project-1/invites",
            json={"target_user_id": "user-2", "role": "member"},
        )
        assert resp.status_code == 201
        assert resp.json()["project_id"] == "project-1"
        self.mock_service.send_project_invite.assert_awaited_once_with("project-1", "user-2", "member", "user-1")

    def test_send_channel_invite(self):
        client = TestClient(app)
        fake_res = InboxItemRead(**_fake_inbox_item_read(user_id="user-2", channel_id="channel-1"))
        self.mock_service.send_channel_invite.return_value = fake_res

        resp = client.post(
            "/api/v1/channels/channel-1/invites",
            json={"target_user_id": "user-2", "role": "member"},
        )
        assert resp.status_code == 201
        assert resp.json()["channel_id"] == "channel-1"
        self.mock_service.send_channel_invite.assert_awaited_once_with("channel-1", "user-2", "member", "user-1")