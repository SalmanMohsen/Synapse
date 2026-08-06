"""GitHub adapter -- the only concrete GitProvider implementation today.

Wraps the same GitHub App JWT / installation-token logic that used to live
directly in app.git.github_auth (that module is now superseded by this
one). The auth flow itself is unchanged; it's just reached through the
GitProvider interface instead of imported directly by runner.py.
"""

import base64
import time

import httpx
import jwt

from app.config import GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY_BASE64
from app.git_providers.base import GitIntegrationRef

_GITHUB_API_BASE = "https://api.github.com"


class GitHubProvider:
    def _load_private_key(self) -> str:
        return base64.b64decode(GITHUB_APP_PRIVATE_KEY_BASE64).decode("utf-8")

    def _generate_app_jwt(self) -> str:
        """Short-lived JWT identifying the GitHub App itself (max 10 min per GitHub)."""
        now = int(time.time())
        payload = {
            "iat": now - 60,  # allow for clock drift
            "exp": now + (9 * 60),
            "iss": GITHUB_APP_ID,
        }
        return jwt.encode(payload, self._load_private_key(), algorithm="RS256")

    async def get_access_token(self, integration: GitIntegrationRef) -> str:
        """Exchanges the App JWT for a short-lived installation access token.
        `integration.external_ref` is the GitHub App installation id."""
        app_jwt = self._generate_app_jwt()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_GITHUB_API_BASE}/app/installations/{integration.external_ref}/access_tokens",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                },
            )
            response.raise_for_status()
            return response.json()["token"]

    def build_authenticated_clone_url(self, integration: GitIntegrationRef, token: str) -> str:
        """x-access-token scheme, GitHub App's convention for token-authenticated clones."""
        return f"https://x-access-token:{token}@github.com/{integration.repo_full_name}.git"

    async def open_pull_request(
        self,
        integration: GitIntegrationRef,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> dict:
        token = await self.get_access_token(integration)
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_GITHUB_API_BASE}/repos/{integration.repo_full_name}/pulls",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                json={
                    "title": title,
                    "body": body,
                    "head": head_branch,
                    "base": base_branch,
                },
            )
            response.raise_for_status()
            return response.json()