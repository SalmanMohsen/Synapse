"""GitHub App authentication for code-service.

Same identity model as backend and planning-service: a short-lived GitHub App
installation token, fetched fresh at job time and never stored (platform-wide
rule). Reuses the same GITHUB_APP_ID / GITHUB_APP_PRIVATE_KEY_BASE64 secrets.
"""

import base64
import time

import httpx
import jwt

from app.config import GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY_BASE64

_GITHUB_API_BASE = "https://api.github.com"


def _load_private_key() -> str:
    return base64.b64decode(GITHUB_APP_PRIVATE_KEY_BASE64).decode("utf-8")


def _generate_app_jwt() -> str:
    """Short-lived JWT identifying the GitHub App itself (max 10 min per GitHub)."""
    now = int(time.time())
    payload = {
        "iat": now - 60,  # allow for clock drift
        "exp": now + (9 * 60),
        "iss": GITHUB_APP_ID,
    }
    return jwt.encode(payload, _load_private_key(), algorithm="RS256")


async def get_installation_token(installation_id: str) -> str:
    """Exchange the App JWT for a short-lived installation access token."""
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
    """Build a clone URL embedding the installation token (x-access-token scheme)."""
    return f"https://x-access-token:{installation_token}@github.com/{repo_full_name}.git"


async def open_pull_request(
    installation_id: str,
    repo_full_name: str,
    head_branch: str,
    base_branch: str,
    title: str,
    body: str,
) -> dict:
    """Open a PR via the GitHub REST API. Returns the created PR payload."""
    token = await get_installation_token(installation_id)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_GITHUB_API_BASE}/repos/{repo_full_name}/pulls",
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
