import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.auth.dependencies import get_current_user
from app.ticket.dependencies import get_ticket_service
from app.ticket.schemas import TicketRead, TicketDetailResponse
from app.ticket.models import TicketStatus, TicketSource, TicketPriority


def _fake_ticket_read(**overrides):
    return {
        "id": overrides.get("id", "ticket-1"),
        "channel_id": overrides.get("channel_id", "channel-1"),
        "title": overrides.get("title", "Ticket 1"),
        "description": overrides.get("description", "Description"),
        "status": overrides.get("status", TicketStatus.backlog),
        "source": overrides.get("source", TicketSource.synapse),
        "priority": overrides.get("priority", TicketPriority.medium),
        "creator_id": overrides.get("creator_id", "user-1"),
        "github_issue_number": overrides.get("github_issue_number", None),
        "github_author_login": overrides.get("github_author_login", None),
        "github_pr_number": overrides.get("github_pr_number", None),
        "parent_ticket_id": overrides.get("parent_ticket_id", None),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


class TestTicketRouter:
    @pytest.fixture(autouse=True)
    def setup_overrides(self):
        self.mock_service = AsyncMock()
        self.mock_user = MagicMock()
        self.mock_user.id = "user-1"

        app.dependency_overrides[get_ticket_service] = lambda: self.mock_service
        app.dependency_overrides[get_current_user] = lambda: self.mock_user
        yield
        app.dependency_overrides.clear()

    def test_create_ticket(self):
        client = TestClient(app)
        fake_res = TicketRead(**_fake_ticket_read())
        self.mock_service.create_ticket.return_value = fake_res

        resp = client.post(
            "/api/v1/channels/channel-1/tickets",
            json={"title": "Ticket 1", "description": "Desc"},
        )
        assert resp.status_code == 201
        assert resp.json()["title"] == "Ticket 1"
        self.mock_service.create_ticket.assert_awaited_once()

    def test_list_tickets(self):
        client = TestClient(app)
        fake_res = [TicketRead(**_fake_ticket_read())]
        self.mock_service.list_tickets.return_value = fake_res

        resp = client.get("/api/v1/channels/channel-1/tickets")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        self.mock_service.list_tickets.assert_awaited_once_with("channel-1", "user-1")

    def test_get_ticket(self):
        client = TestClient(app)
        fake_ticket = TicketRead(**_fake_ticket_read())
        fake_detail = {
            "ticket": fake_ticket.model_dump(),
            "messages": {"items": [], "has_more": False, "next_cursor": None},
            "thread_state": None,
        }
        self.mock_service.get_ticket.return_value = TicketDetailResponse(**fake_detail)

        resp = client.get("/api/v1/tickets/ticket-1")
        assert resp.status_code == 200
        assert resp.json()["ticket"]["id"] == "ticket-1"
        self.mock_service.get_ticket.assert_awaited_once_with("ticket-1", "user-1")

    def test_update_ticket(self):
        client = TestClient(app)
        fake_res = TicketRead(**_fake_ticket_read(title="New Title"))
        self.mock_service.update_ticket.return_value = fake_res

        resp = client.patch(
            "/api/v1/tickets/ticket-1",
            json={"title": "New Title"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "New Title"
        self.mock_service.update_ticket.assert_awaited_once()

    def test_route_ticket(self):
        client = TestClient(app)
        fake_res = TicketRead(**_fake_ticket_read(channel_id="channel-2", status=TicketStatus.routed))
        self.mock_service.route_ticket.return_value = fake_res

        resp = client.post(
            "/api/v1/tickets/ticket-1/route",
            json={"channel_id": "channel-2"},
        )
        assert resp.status_code == 200
        assert resp.json()["channel_id"] == "channel-2"
        self.mock_service.route_ticket.assert_awaited_once()

    def test_activate_ticket(self):
        client = TestClient(app)
        fake_res = TicketRead(**_fake_ticket_read(status=TicketStatus.active))
        self.mock_service.activate_ticket.return_value = fake_res

        resp = client.post("/api/v1/tickets/ticket-1/activate")
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"
        self.mock_service.activate_ticket.assert_awaited_once_with("ticket-1", "user-1")

    def test_generate_plan(self):
        client = TestClient(app)
        fake_res = TicketRead(**_fake_ticket_read(status=TicketStatus.consensus_reached))
        self.mock_service.generate_plan.return_value = fake_res

        resp = client.post("/api/v1/tickets/ticket-1/generate-plan")
        assert resp.status_code == 200
        self.mock_service.generate_plan.assert_awaited_once_with("ticket-1", "user-1")

    def test_close_ticket(self):
        client = TestClient(app)
        fake_res = TicketRead(**_fake_ticket_read(status=TicketStatus.closed))
        self.mock_service.close_ticket.return_value = fake_res

        resp = client.post("/api/v1/tickets/ticket-1/close")
        assert resp.status_code == 200
        assert resp.json()["status"] == "closed"
        self.mock_service.close_ticket.assert_awaited_once_with("ticket-1", "user-1")

    def test_split_ticket(self):
        client = TestClient(app)
        fake_res = TicketRead(**_fake_ticket_read(status=TicketStatus.split))
        self.mock_service.split_ticket.return_value = fake_res

        resp = client.post(
            "/api/v1/tickets/ticket-1/split",
            json={"child_ticket_ids": ["ticket-2", "ticket-3"]},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "split"
        self.mock_service.split_ticket.assert_awaited_once()