import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.auth.dependencies import get_current_user
from app.channel.dependencies import get_channel_service
from app.channel.schemas import ChannelRead, ChannelMemberRead
from app.channel.models import ChannelDiscipline, ApprovalPolicy, ChannelMemberRole


def _fake_channel_read(**overrides):
    return {
        "id": overrides.get("id", "channel-1"),
        "project_id": overrides.get("project_id", "project-1"),
        "name": overrides.get("name", "Backend Channel"),
        "discipline": overrides.get("discipline", ChannelDiscipline.backend),
        "is_leads_channel": overrides.get("is_leads_channel", False),
        "approval_policy": overrides.get("approval_policy", ApprovalPolicy.lead_only),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _fake_channel_member_read(**overrides):
    return {
        "id": overrides.get("id", "member-1"),
        "channel_id": overrides.get("channel_id", "channel-1"),
        "user_id": overrides.get("user_id", "user-1"),
        "role": overrides.get("role", ChannelMemberRole.member),
        "joined_at": datetime.now(timezone.utc).isoformat(),
    }


class TestChannelRouter:
    @pytest.fixture(autouse=True)
    def setup_overrides(self):
        self.mock_service = AsyncMock()
        self.mock_user = MagicMock()
        self.mock_user.id = "user-1"

        app.dependency_overrides[get_channel_service] = lambda: self.mock_service
        app.dependency_overrides[get_current_user] = lambda: self.mock_user
        yield
        app.dependency_overrides.clear()

    def test_create_channel(self):
        client = TestClient(app)
        fake_res = ChannelRead(**_fake_channel_read())
        self.mock_service.create_channel.return_value = fake_res

        resp = client.post(
            "/api/v1/projects/project-1/channels",
            json={"name": "Backend", "discipline": "backend"},
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Backend Channel"
        self.mock_service.create_channel.assert_awaited_once()

    def test_create_leads_channel(self):
        client = TestClient(app)
        fake_res = ChannelRead(**_fake_channel_read(is_leads_channel=True, discipline=None))
        self.mock_service.create_leads_channel.return_value = fake_res

        resp = client.post("/api/v1/projects/project-1/leads-channel")
        assert resp.status_code == 201
        assert resp.json()["is_leads_channel"] is True
        self.mock_service.create_leads_channel.assert_awaited_once()

    def test_list_channels(self):
        client = TestClient(app)
        fake_res = [ChannelRead(**_fake_channel_read())]
        self.mock_service.list_channels.return_value = fake_res

        resp = client.get("/api/v1/projects/project-1/channels")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        self.mock_service.list_channels.assert_awaited_once()

    def test_get_channel(self):
        client = TestClient(app)
        fake_res = ChannelRead(**_fake_channel_read())
        self.mock_service.get_channel.return_value = fake_res

        resp = client.get("/api/v1/channels/channel-1")
        assert resp.status_code == 200
        assert resp.json()["id"] == "channel-1"
        self.mock_service.get_channel.assert_awaited_once_with("channel-1", "user-1")

    def test_update_channel(self):
        client = TestClient(app)
        fake_res = ChannelRead(**_fake_channel_read(name="New Name"))
        self.mock_service.update_channel.return_value = fake_res

        resp = client.patch(
            "/api/v1/channels/channel-1",
            json={"name": "New Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"
        self.mock_service.update_channel.assert_awaited_once()

    def test_delete_channel(self):
        client = TestClient(app)
        self.mock_service.delete_channel.return_value = None

        resp = client.delete("/api/v1/channels/channel-1")
        assert resp.status_code == 204
        self.mock_service.delete_channel.assert_awaited_once_with("channel-1", "user-1")

    def test_list_members(self):
        client = TestClient(app)
        fake_res = [ChannelMemberRead(**_fake_channel_member_read())]
        self.mock_service.list_members.return_value = fake_res

        resp = client.get("/api/v1/channels/channel-1/members")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        self.mock_service.list_members.assert_awaited_once_with("channel-1", "user-1")

    def test_add_member(self):
        client = TestClient(app)
        fake_res = ChannelMemberRead(**_fake_channel_member_read(user_id="user-2"))
        self.mock_service.add_member.return_value = fake_res

        resp = client.post(
            "/api/v1/channels/channel-1/members",
            json={"user_id": "user-2", "role": "member"},
        )
        assert resp.status_code == 201
        assert resp.json()["user_id"] == "user-2"
        self.mock_service.add_member.assert_awaited_once()

    def test_update_member_role(self):
        client = TestClient(app)
        fake_res = ChannelMemberRead(**_fake_channel_member_read(user_id="user-2", role=ChannelMemberRole.channel_lead))
        self.mock_service.update_member_role.return_value = fake_res

        resp = client.patch(
            "/api/v1/channels/channel-1/members/user-2",
            json={"role": "channel_lead"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "channel_lead"
        self.mock_service.update_member_role.assert_awaited_once()

    def test_remove_member(self):
        client = TestClient(app)
        self.mock_service.remove_member.return_value = None

        resp = client.delete("/api/v1/channels/channel-1/members/user-2")
        assert resp.status_code == 204
        self.mock_service.remove_member.assert_awaited_once_with("channel-1", "user-1", "user-2")