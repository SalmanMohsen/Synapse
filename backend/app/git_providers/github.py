"""GitHub adapter -- the only concrete GitProvider implementation today.

Everything here used to live directly inside GitIntegrationService:
_generate_github_app_jwt / _get_installation_access_token, the repo-listing
call inside handle_callback, the HMAC verification inside handle_webhook,
and the four event_type/action -> payload-shape assumptions baked into
_handle_issue_opened / _handle_issue_reopened / _handle_push /
_handle_pull_request_closed. None of that logic changed -- it's relocated
and, for the four handlers' payload reading, now produces a
NormalizedGitEvent instead of handing the service a raw GitHub payload.
"""

import base64
import hashlib
import hmac
import time

import httpx
from fastapi import HTTPException
from jose import jwt

from app.config import get_settings
from app.git_providers.base import InstallationRepo, NormalizedGitEvent

_GITHUB_API_BASE = "https://api.github.com"


class GitHubProvider:
    def __init__(self) -> None:
        self._settings = get_settings()

    def _generate_app_jwt(self) -> str:
        settings = self._settings
        if not settings.github_app_private_key_base64:
            raise HTTPException(
                status_code=500,
                detail="GitHub App credentials are not configured on the server.",
            )
        try:
            private_key_pem = base64.b64decode(settings.github_app_private_key_base64).decode("utf-8")
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to decode the base64-encoded GitHub App private key: {e}",
            )

        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + (10 * 60),
            "iss": settings.github_app_id,
        }
        return jwt.encode(payload, private_key_pem, algorithm="RS256")

    async def get_access_token(self, external_ref: str) -> str:
        """external_ref is the GitHub App installation id."""
        app_jwt = self._generate_app_jwt()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_GITHUB_API_BASE}/app/installations/{external_ref}/access_tokens",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "Synapse-App",
                },
                timeout=10,
            )
            if resp.status_code != 201:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Could not generate GitHub App installation token: {resp.text}",
                )
            return resp.json()["token"]

    def build_install_url(self, state_token: str) -> str:
        app_slug = self._settings.github_app_slug
        return f"https://github.com/apps/{app_slug}/installations/new?state={state_token}"

    async def list_installation_repos(self, external_ref: str) -> list[InstallationRepo]:
        installation_token = await self.get_access_token(external_ref)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_GITHUB_API_BASE}/installation/repositories",
                headers={
                    "Authorization": f"Bearer {installation_token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "Synapse-App",
                },
                timeout=10,
            )
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Could not retrieve repositories: {resp.text}",
                )
            repos_json = resp.json()
            repositories = repos_json.get("repositories", [])
            if not repositories:
                raise HTTPException(
                    status_code=400,
                    detail="No repositories are configured under this App installation.",
                )
            return [
                InstallationRepo(
                    repo_full_name=r["full_name"],
                    default_branch=r.get("default_branch", "main"),
                )
                for r in repositories
            ]

    def verify_webhook_signature(self, headers: dict, body_bytes: bytes) -> bool:
        signature = headers.get("X-Hub-Signature-256") or headers.get("x-hub-signature-256")
        if not signature or not signature.startswith("sha256="):
            return False

        received_hash = signature[7:]
        expected_hash = hmac.new(
            self._settings.github_webhook_secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(received_hash, expected_hash)

    def extract_delivery_metadata(self, headers: dict, payload: dict) -> tuple[str, str, str]:
        delivery_id = headers.get("X-GitHub-Delivery", "") or headers.get("x-github-delivery", "")
        event_type = headers.get("X-GitHub-Event", "") or headers.get("x-github-event", "")
        action = payload.get("action", "")
        return delivery_id, event_type, action

    def parse_webhook_event(self, event_type: str, action: str, payload: dict) -> NormalizedGitEvent | None:
        repo_full_name = payload.get("repository", {}).get("full_name")

        if event_type == "issues" and action == "opened":
            issue = payload.get("issue", {})
            return NormalizedGitEvent(
                kind="issue_opened",
                repo_full_name=repo_full_name,
                issue_number=issue.get("number"),
                title=issue.get("title", ""),
                description=issue.get("body", "") or "",
                author_external_id=str(issue.get("user", {}).get("id") or "") or None,
                author_login=issue.get("user", {}).get("login"),
            )

        if event_type == "issues" and action == "reopened":
            issue = payload.get("issue", {})
            return NormalizedGitEvent(
                kind="issue_reopened",
                repo_full_name=repo_full_name,
                issue_number=issue.get("number"),
                title=issue.get("title", ""),
                author_login=issue.get("user", {}).get("login"),
            )

        if event_type == "push":
            return NormalizedGitEvent(
                kind="push",
                repo_full_name=repo_full_name,
                ref=payload.get("ref", ""),
            )

        if event_type == "pull_request" and action == "closed":
            pr = payload.get("pull_request", {})
            return NormalizedGitEvent(
                kind="change_request_closed",
                repo_full_name=repo_full_name,
                change_request_number=pr.get("number"),
                merged=pr.get("merged", False),
            )

        return None