import pytest
import hmac
import hashlib
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException
from app.github.service import GitIntegrationService
from app.github.models import WebhookEventStatus

class FakeWebhookEvent:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class FakeWebhookEventRepository:
    def __init__(self):
        self.events = {}

    async def get_by_delivery_id(self, delivery_id: str):
        return self.events.get(delivery_id)

    async def create(self, **kwargs):
        event = FakeWebhookEvent(id="event-123", **kwargs)
        self.events[kwargs["delivery_id"]] = event
        return event

    async def update(self, event, **kwargs):
        for k, v in kwargs.items():
            setattr(event, k, v)
        return event

class FakeGitIntegrationRepository:
    def __init__(self):
        self.integrations = {}

    async def get_by_repo_full_name(self, repo_full_name: str):
        return self.integrations.get(repo_full_name)

class FakeGitWebhookUnitOfWork:
    def __init__(self):
        self.webhook_events = FakeWebhookEventRepository()
        self.git_integrations = FakeGitIntegrationRepository()
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
@patch("app.github.service.settings")
async def test_handle_webhook_invalid_signature(mock_settings):
    mock_settings.github_webhook_secret = "secret-123"
    uow = FakeGitWebhookUnitOfWork()
    service = GitIntegrationService(uow, redis=AsyncMock())

    body = b'{"ref": "refs/heads/main"}'
    signature = "sha256=invalidhash"

    with pytest.raises(HTTPException) as exc_info:
        await service.handle_webhook(
            delivery_id="delivery-1",
            event_type="push",
            action="pushed",
            payload={"ref": "refs/heads/main"},
            body_bytes=body,
            signature=signature
        )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
@patch("app.github.service.settings")
async def test_handle_webhook_idempotency_duplicate(mock_settings):
    mock_settings.github_webhook_secret = "secret-123"
    uow = FakeGitWebhookUnitOfWork()
    service = GitIntegrationService(uow, redis=AsyncMock())

    # Seed an already processed event
    await uow.webhook_events.create(
        delivery_id="dup-delivery",
        event_type="push",
        action="pushed",
        payload={},
        status=WebhookEventStatus.processed
    )

    body = b'{"ref": "refs/heads/main"}'
    expected_hash = hmac.new(b"secret-123", body, hashlib.sha256).hexdigest()
    signature = f"sha256={expected_hash}"

    # Verify duplicate event exits early without raising exceptions or writing new rows
    initial_count = len(uow.webhook_events.events)
    await service.handle_webhook(
        delivery_id="dup-delivery",
        event_type="push",
        action="pushed",
        payload={"ref": "refs/heads/main"},
        body_bytes=body,
        signature=signature
    )
    assert len(uow.webhook_events.events) == initial_count


@pytest.mark.asyncio
@patch("app.github.service.get_arq_pool")
async def test_handle_push_event_matching_branch(mock_get_arq_pool):
    mock_pool = AsyncMock()
    mock_get_arq_pool.return_value = mock_pool

    uow = FakeGitWebhookUnitOfWork()
    integration = MagicMock()
    integration.project_id = "project-456"
    integration.default_branch = "main"
    uow.git_integrations.integrations["org/repo"] = integration

    service = GitIntegrationService(uow, redis=AsyncMock())

    payload = {
        "ref": "refs/heads/main",
        "repository": {"full_name": "org/repo"}
    }

    await service._handle_push(payload)
    mock_pool.enqueue_job.assert_called_once_with("ingest_repository", project_id="project-456")


@pytest.mark.asyncio
@patch("app.github.service.get_arq_pool")
async def test_handle_push_event_ignored_branch(mock_get_arq_pool):
    mock_pool = AsyncMock()
    mock_get_arq_pool.return_value = mock_pool

    uow = FakeGitWebhookUnitOfWork()
    integration = MagicMock()
    integration.project_id = "project-456"
    integration.default_branch = "main"
    uow.git_integrations.integrations["org/repo"] = integration

    service = GitIntegrationService(uow, redis=AsyncMock())

    payload = {
        "ref": "refs/heads/feature-branch",
        "repository": {"full_name": "org/repo"}
    }

    await service._handle_push(payload)
    mock_pool.enqueue_job.assert_not_called()