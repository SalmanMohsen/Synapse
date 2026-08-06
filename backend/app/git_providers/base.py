"""GitProvider interface for backend.

This is the seam GitIntegrationService goes through for everything
vendor-specific: building the install/authorize URL, exchanging a token,
listing repos accessible under an installation, verifying a webhook's
signature, and parsing a webhook's event_type/action/payload into a
NormalizedGitEvent.

Once a provider's parse_webhook_event() has run, nothing downstream --
_handle_issue_opened, _handle_push, _handle_pull_request_closed, etc. --
ever reads a vendor's raw payload shape again. That's deliberate: those
methods are ticket/messaging business logic, not GitHub logic, and they
should stay reusable as-is when a second provider is added.

Webhook delivery/signature headers differ enough per vendor (GitHub:
X-Hub-Signature-256 + X-GitHub-Event; GitLab: X-Gitlab-Token +
X-Gitlab-Event; Azure DevOps: no standard signature header at all) that
each provider gets its own webhook route in router.py rather than one
shared route -- that's normal, since each vendor's webhook settings UI
needs its own URL to point at anyway. The route itself is what tells the
service which provider to resolve; see router.py.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class InstallationRepo:
    """One repo accessible under an installation/integration, as returned
    by the vendor's 'list accessible repos' call -- used right after the
    install callback to auto-select which repo to link to the project."""

    repo_full_name: str
    default_branch: str


@dataclass(frozen=True)
class NormalizedGitEvent:
    """Canonical shape every webhook handler in GitIntegrationService reads.
    Optional fields are simply unset for event kinds that don't use them."""

    kind: str  # "issue_opened" | "issue_reopened" | "push" | "change_request_closed"
    repo_full_name: str
    issue_number: int | None = None
    title: str = ""
    description: str = ""
    author_external_id: str | None = None
    author_login: str | None = None
    ref: str | None = None
    change_request_number: int | None = None
    merged: bool = False


class GitProvider(Protocol):
    def build_install_url(self, state_token: str) -> str:
        """URL sent to the browser to start the app-install / authorize flow."""
        ...

    async def get_access_token(self, external_ref: str) -> str:
        """Short-lived token authorized to act via this installation/integration."""
        ...

    async def list_installation_repos(self, external_ref: str) -> list[InstallationRepo]:
        """Repos accessible under this installation/integration."""
        ...

    def verify_webhook_signature(self, headers: dict, body_bytes: bytes) -> bool:
        """True if this webhook request is authentically from this vendor."""
        ...

    def extract_delivery_metadata(self, headers: dict, payload: dict) -> tuple[str, str, str]:
        """Returns (delivery_id, event_type, action) from the raw request --
        used once at ingestion time, before the event is even stored."""
        ...

    def parse_webhook_event(self, event_type: str, action: str, payload: dict) -> NormalizedGitEvent | None:
        """Maps a stored (event_type, action, payload) row into a
        NormalizedGitEvent. Returns None for event kinds this platform
        doesn't act on -- the caller just leaves those stored and skips them."""
        ...