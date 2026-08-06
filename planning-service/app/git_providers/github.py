"""GitHub adapter -- the only concrete GitProvider implementation today.

Wraps the same GitHub App JWT / installation-token logic that used to live
directly in app.ingestion.github_auth (that module is now superseded by
this one). Still reads credentials from os.environ directly rather than
app.config, same as the module it replaces -- not changed here since that
wasn't part of this refactor; worth aligning with code-service's
app.config-based approach in a separate pass if you want the two services
consistent.
"""

import base64
import os
import time

import httpx
import jwt

from app.git_providers.base import GitIntegrationRef

_GITHUB_API_BASE = "https://api.github.com"


class GitHubProvider:
    def _load_private_key(self) -> str:
        encoded = os.environ["GITHUB_APP_PRIVATE_KEY_BASE64"]
        return base64.b64decode(encoded).decode("utf-8")

    def _generate_app_jwt(self) -> str:
        """Short-lived JWT identifying the GitHub App itself (max 10 min per GitHub)."""
        app_id = os.environ["GITHUB_APP_ID"]
        now = int(time.time())
        payload = {
            "iat": now - 60,  # allow for clock drift
            "exp": now + (9 * 60),
            "iss": app_id,
        }
        return jwt.encode(payload, self._load_private_key(), algorithm="RS256")

    async def get_access_token(self, integration: GitIntegrationRef) -> str:
        """Exchanges the App JWT for a short-lived installation access token.
        Never stored -- fetched fresh at job time (platform-wide rule)."""
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
        return f"https://x-access-token:{token}@github.com/{integration.repo_full_name}.git"