import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.auth.dependencies import get_current_user
from app.message.dependencies import get_message_service
from app.message.schemas import MessageRead, MessageListResponse
from app.message.models import MessageType


def _fake_message_read(**overrides):
    return {
        "id": overrides.get("id", "msg-1"),
        "ticket_id": overrides.get("ticket_id", "ticket-1"),
        "author_id": overrides.get("author_id", "user-1"),
        "author": overrides.get("author", {"id": "user-1", "display_name": "Author", "avatar_url": None}),
        "content": overrides.get("content", "Message Content"),
        "type": overrides.get("type", MessageType.human),
        "metadata_json": overrides.get("metadata_json", None),
        "deleted_at": overrides.get("deleted_at", None),
        "edited_at": overrides.get("edited_at", None),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


class TestMessageRouter:
    @pytest.fixture(autouse=True)
    def setup_overrides(self):
        self.mock_service = AsyncMock()
        self.mock_user = MagicMock()
        self.mock_user.id = "user-1"

        app.dependency_overrides[get_message_service] = lambda: self.mock_service
        app.dependency_overrides[get_current_user] = lambda: self.mock_user
        yield
        app.dependency_overrides.clear()

    def test_create_message(self):
        client = TestClient(app)
        fake_res = MessageRead(**_fake_message_read(content="Hello"))
        self.mock_service.create_message.return_value = fake_res

        resp = client.post(
            "/api/v1/tickets/ticket-1/messages",
            json={"content": "Hello"},
        )
        assert resp.status_code == 201
        assert resp.json()["content"] == "Hello"
        self.mock_service.create_message.assert_awaited_once()

    def test_list_messages(self):
        client = TestClient(app)
        fake_items = [MessageRead(**_fake_message_read())]
        fake_res = MessageListResponse(items=fake_items, has_more=False, next_cursor=None)
        self.mock_service.list_messages.return_value = fake_res

        resp = client.get("/api/v1/tickets/ticket-1/messages")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1
        self.mock_service.list_messages.assert_awaited_once_with("ticket-1", "user-1", before_id=None)

    def test_edit_message(self):
        client = TestClient(app)
        fake_res = MessageRead(**_fake_message_read(content="Edited"))
        self.mock_service.edit_message.return_value = fake_res

        resp = client.patch(
            "/api/v1/tickets/ticket-1/messages/msg-1",
            json={"content": "Edited"},
        )
        assert resp.status_code == 200
        assert resp.json()["content"] == "Edited"
        self.mock_service.edit_message.assert_awaited_once()

    def test_delete_message(self):
        client = TestClient(app)
        fake_res = MessageRead(**_fake_message_read(content=None, deleted_at="2026-08-07T20:08:00Z"))
        self.mock_service.delete_message.return_value = fake_res

        resp = client.delete("/api/v1/tickets/ticket-1/messages/msg-1")
        assert resp.status_code == 200
        assert resp.json()["content"] is None
        self.mock_service.delete_message.assert_awaited_once_with("ticket-1", "msg-1", "user-1")