import pytest
import hmac
import hashlib
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi import HTTPException

from app.git_providers.factory import get_git_provider
from app.git_providers.github import GitHubProvider
from app.git_providers.base import NormalizedGitEvent, InstallationRepo


def test_factory_resolves_github_provider():
    provider = get_git_provider("github")
    assert isinstance(provider, GitHubProvider)

    with pytest.raises(ValueError, match="No GitProvider registered"):
        get_git_provider("unsupported_vendor")


@patch("app.git_providers.github.get_settings")
def test_verify_webhook_signature(mock_get_settings):
    # Configure mock settings
    mock_settings = MagicMock()
    mock_settings.github_webhook_secret = "webhook-key-123"
    mock_get_settings.return_value = mock_settings

    provider = GitHubProvider()
    body = b'{"action": "opened"}'

    # Compute a valid HMAC SHA256 signature
    expected_hash = hmac.new(b"webhook-key-123", body, hashlib.sha256).hexdigest()
    valid_headers = {"X-Hub-Signature-256": f"sha256={expected_hash}"}

    assert provider.verify_webhook_signature(valid_headers, body) is True
    assert provider.verify_webhook_signature({"X-Hub-Signature-256": "sha256=bad"}, body) is False


def test_parse_webhook_event_issue_opened():
    provider = GitHubProvider()
    payload = {
        "repository": {"full_name": "synapse/app"},
        "issue": {
            "number": 42,
            "title": "Fix memory leak",
            "body": "Profile leaks on loop",
            "user": {"id": 999, "login": "alice_dev"}
        }
    }

    event = provider.parse_webhook_event("issues", "opened", payload)

    assert isinstance(event, NormalizedGitEvent)
    assert event.kind == "issue_opened"
    assert event.repo_full_name == "synapse/app"
    assert event.issue_number == 42
    assert event.title == "Fix memory leak"
    assert event.description == "Profile leaks on loop"
    assert event.author_external_id == "999"
    assert event.author_login == "alice_dev"


def test_parse_webhook_event_unhandled_type_returns_none():
    provider = GitHubProvider()
    payload = {"repository": {"full_name": "synapse/app"}}

    # Returns None for actions we do not monitor
    event = provider.parse_webhook_event("star", "created", payload)
    assert event is None