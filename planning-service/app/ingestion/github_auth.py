"""GitHub App authentication for planning-service.

Same identity model as the backend: a GitHub App installation token, not a
personal access token. planning-service needs its own copy of the App
credentials (GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY_BASE64) once it's wired
into docker-compose — same env var names the backend already uses,
so the same .env secrets can be reused for both containers.
"""

import base64
import os
import time

import httpx
import jwt

_GITHUB_API_BASE = "https://api.github.com"


def _load_private_key() -> str:
    encoded = os.environ["GITHUB_APP_PRIVATE_KEY_BASE64"]
    return base64.b64decode(encoded).decode("utf-8")


def _generate_app_jwt() -> str:
    """Short-lived JWT identifying the GitHub App itself (max 10 min per GitHub)."""
    app_id = os.environ["GITHUB_APP_ID"]
    now = int(time.time())
    payload = {
        "iat": now - 60,  # allow for clock drift
        "exp": now + (9 * 60),
        "iss": app_id,
    }
    return jwt.encode(payload, _load_private_key(), algorithm="RS256")


async def get_installation_token(installation_id: str) -> str:
    """Exchanges the App JWT for a short-lived installation access token.

    Never stored — fetched fresh at job time (matches the platform-wide
    "short-lived installation tokens fetched at job time, never stored" rule).
    """
    app_jwt = _generate_app_jwt()
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
            },
        )
        response.raise_for_status()
        return response.json()["token"]


def authenticated_clone_url(repo_full_name: str, installation_token: str) -> str:
    """Builds a clone URL embedding the installation token (x-access-token scheme)."""
    return f"https://x-access-token:{installation_token}@github.com/{repo_full_name}.git"