"""
Unit tests for app.auth.router
────────────────────────────────
Uses FastAPI's synchronous TestClient. All AuthService methods are
replaced with MagicMock / AsyncMock so no DB, Redis, or HTTP calls
are made. get_current_user dependency is overridden per-test where auth
is required.

Endpoints covered:
  POST /register              – 201 + cookies set, 409 from service
  POST /login                 – 200 + cookies set, 401 from service
  GET  /github                – redirect to GitHub, correct query params
  GET  /github/callback       – login flow (no state), link flow (state=link:id),
                                service error → HTML error popup
  GET  /link/github           – requires auth, redirect carries state=link:{id}
  GET  /link/github/callback  – requires auth, calls link_github, error path
  DEL  /link/github           – requires auth, returns UserRead
  GET  /google                – redirect to Google with redirect_uri
  GET  /google/callback       – login flow, service error → HTML error popup
  GET  /link/google           – redirect carries link/google/callback redirect_uri
  GET  /link/google/callback  – requires auth, calls link_google, error path
  DEL  /link/google           – requires auth, returns UserRead
  POST /refresh               – no cookie → 401, valid cookie → new cookies
  POST /logout                – clears both cookies
  GET  /me                    – returns UserRead, no cookie → 401

HTML popup helpers:
  _success_html / _error_html – content and postMessage correctness
"""

import json
import urllib.parse
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth.tests.helpers import make_user


# ════════════════════════════════════════════════════════════════════════════
# App + dependency overrides
# ════════════════════════════════════════════════════════════════════════════

def _build_client(
    service_overrides: dict | None = None,
    current_user=None,
):
    """
    Build a TestClient with:
      - AuthService fully mocked (every method is an AsyncMock)
      - get_current_user overridden to return `current_user`
        (or raise 401 if None)
    """
    from app.main import app
    from app.auth.dependencies import get_auth_service, get_current_user

    mock_service = AsyncMock()
    # Apply any per-test overrides
    if service_overrides:
        for attr, value in service_overrides.items():
            setattr(mock_service, attr, value)

    async def _override_service():
        return mock_service

    async def _override_user():
        if current_user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return current_user

    app.dependency_overrides[get_auth_service] = _override_service
    app.dependency_overrides[get_current_user] = _override_user

    client = TestClient(app, raise_server_exceptions=False)
    return client, mock_service


def _fake_user_read(**overrides):
    """Return a dict that matches UserRead's JSON shape."""
    return {
        "id": overrides.get("id", "user-1"),
        "email": overrides.get("email", "alice@example.com"),
        "display_name": overrides.get("display_name", "Alice"),
        "avatar_url": overrides.get("avatar_url", None),
        "github_user_id": overrides.get("github_user_id", None),
        "google_user_id": overrides.get("google_user_id", None),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _user_read_obj(**overrides):
    """Return a MagicMock that behaves like a UserRead Pydantic model."""
    from app.auth.schemas import UserRead
    data = _fake_user_read(**overrides)
    return UserRead(**data)


def _clear_overrides():
    from app.main import app
    app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════════════════
# HTML popup helpers
# ════════════════════════════════════════════════════════════════════════════

class TestHtmlHelpers:
    def test_success_html_contains_postmessage(self):
        from app.auth.router import _success_html
        html = _success_html()
        assert "postMessage" in html
        assert "oauth_success" in html
        assert "window.close" in html

    def test_success_html_uses_custom_event_type(self):
        from app.auth.router import _success_html
        html = _success_html("link_success")
        assert "link_success" in html

    def test_error_html_contains_reason(self):
        from app.auth.router import _error_html
        html = _error_html("Something went wrong")
        assert "Something went wrong" in html
        assert "oauth_error" in html

    def test_error_html_uses_custom_event_type(self):
        from app.auth.router import _error_html
        html = _error_html("bad", "link_error")
        assert "link_error" in html

    def test_error_html_escapes_single_quotes(self):
        from app.auth.router import _error_html
        html = _error_html("it's broken")
        assert "it\\'s broken" in html

    def test_success_html_targets_frontend_origin(self):
        from app.auth.router import _success_html
        from app.config import get_settings
        html = _success_html()
        assert get_settings().frontend_url in html


# ════════════════════════════════════════════════════════════════════════════
# Cookie helpers
# ════════════════════════════════════════════════════════════════════════════

class TestCookieHelpers:
    def test_set_auth_cookies_sets_both_cookies(self):
        from fastapi import Response
        from app.auth.router import _set_auth_cookies

        response = MagicMock(spec=Response)
        _set_auth_cookies(response, "access123", "refresh456")

        calls = [c.args[0] for c in response.set_cookie.call_args_list]
        assert "access_token" in calls
        assert "refresh_token" in calls

    def test_set_auth_cookies_are_httponly(self):
        from fastapi import Response
        from app.auth.router import _set_auth_cookies

        response = MagicMock(spec=Response)
        _set_auth_cookies(response, "a", "r")

        for call in response.set_cookie.call_args_list:
            assert call.kwargs.get("httponly") is True

    def test_clear_auth_cookies_deletes_both(self):
        from fastapi import Response
        from app.auth.router import _clear_auth_cookies

        response = MagicMock(spec=Response)
        _clear_auth_cookies(response)

        deleted = [c.args[0] for c in response.delete_cookie.call_args_list]
        assert "access_token" in deleted
        assert "refresh_token" in deleted


# ════════════════════════════════════════════════════════════════════════════
# POST /register
# ════════════════════════════════════════════════════════════════════════════

class TestRegisterEndpoint:
    def setup_method(self):
        _clear_overrides()

    def test_register_201_and_body(self):
        user_read = _user_read_obj()
        client, svc = _build_client(
            service_overrides={"register": AsyncMock(return_value=(user_read, "acc", "ref"))}
        )
        resp = client.post("/api/v1/auth/register", json={
            "email": "alice@example.com",
            "display_name": "Alice",
            "password": "password123",
        })
        assert resp.status_code == 201
        assert resp.json()["email"] == "alice@example.com"

    def test_register_sets_access_cookie(self):
        user_read = _user_read_obj()
        client, svc = _build_client(
            service_overrides={"register": AsyncMock(return_value=(user_read, "acc", "ref"))}
        )
        resp = client.post("/api/v1/auth/register", json={
            "email": "alice@example.com", "display_name": "Alice", "password": "password123"
        })
        assert "access_token" in resp.cookies

    def test_register_invalid_body_returns_422(self):
        client, _ = _build_client()
        resp = client.post("/api/v1/auth/register", json={"email": "bad"})
        assert resp.status_code == 422

    def test_register_service_409_is_propagated(self):
        client, svc = _build_client(
            service_overrides={"register": AsyncMock(
                side_effect=HTTPException(status_code=409, detail="Email already registered")
            )}
        )
        resp = client.post("/api/v1/auth/register", json={
            "email": "a@b.com", "display_name": "Al", "password": "password123"
        })
        assert resp.status_code == 409


# ════════════════════════════════════════════════════════════════════════════
# POST /login
# ════════════════════════════════════════════════════════════════════════════

class TestLoginEndpoint:
    def setup_method(self):
        _clear_overrides()

    def test_login_200_and_body(self):
        user_read = _user_read_obj()
        client, _ = _build_client(
            service_overrides={"login": AsyncMock(return_value=(user_read, "acc", "ref"))}
        )
        resp = client.post("/api/v1/auth/login", json={
            "email": "alice@example.com", "password": "password123"
        })
        assert resp.status_code == 200
        assert resp.json()["email"] == "alice@example.com"

    def test_login_sets_cookies(self):
        user_read = _user_read_obj()
        client, _ = _build_client(
            service_overrides={"login": AsyncMock(return_value=(user_read, "acc", "ref"))}
        )
        resp = client.post("/api/v1/auth/login", json={
            "email": "alice@example.com", "password": "password123"
        })
        assert "access_token" in resp.cookies

    def test_login_service_401_is_propagated(self):
        client, _ = _build_client(
            service_overrides={"login": AsyncMock(
                side_effect=HTTPException(status_code=401, detail="Invalid credentials")
            )}
        )
        resp = client.post("/api/v1/auth/login", json={
            "email": "a@b.com", "password": "wrong"
        })
        assert resp.status_code == 401


# ════════════════════════════════════════════════════════════════════════════
# GET /github  (login start)
# ════════════════════════════════════════════════════════════════════════════

class TestGithubOAuthStart:
    def setup_method(self):
        _clear_overrides()

    def test_redirects_to_github(self):
        client, _ = _build_client()
        resp = client.get("/api/v1/auth/github", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert "github.com/login/oauth/authorize" in resp.headers["location"]

    def test_redirect_includes_client_id(self):
        client, _ = _build_client()
        resp = client.get("/api/v1/auth/github", follow_redirects=False)
        location = resp.headers["location"]
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(location).query))
        assert "client_id" in params

    def test_redirect_requests_user_email_scope(self):
        client, _ = _build_client()
        resp = client.get("/api/v1/auth/github", follow_redirects=False)
        location = resp.headers["location"]
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(location).query))
        assert "user:email" in params.get("scope", "")

    def test_no_redirect_uri_in_params(self):
        """
        /github start does NOT include redirect_uri — it relies on the one
        registered in the GitHub App settings.
        """
        client, _ = _build_client()
        resp = client.get("/api/v1/auth/github", follow_redirects=False)
        location = resp.headers["location"]
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(location).query))
        assert "redirect_uri" not in params


# ════════════════════════════════════════════════════════════════════════════
# GET /github/callback
# ════════════════════════════════════════════════════════════════════════════

class TestGithubCallback:
    def setup_method(self):
        _clear_overrides()

    # ── login flow (no state / state not starting with "link:") ──────────

    def test_login_flow_sets_cookies_and_returns_success_html(self):
        user_read = _user_read_obj()
        client, _ = _build_client(
            service_overrides={"github_callback": AsyncMock(
                return_value=(user_read, "acc", "ref")
            )}
        )
        resp = client.get("/api/v1/auth/github/callback?code=ghcode")
        assert resp.status_code == 200
        assert "oauth_success" in resp.text
        assert "access_token" in resp.cookies

    def test_login_flow_service_error_returns_error_html(self):
        client, _ = _build_client(
            service_overrides={"github_callback": AsyncMock(
                side_effect=Exception("OAuth failed")
            )}
        )
        resp = client.get("/api/v1/auth/github/callback?code=bad")
        assert resp.status_code == 200
        assert "oauth_error" in resp.text
        assert "OAuth failed" in resp.text

    def test_login_flow_does_not_call_link_github(self):
        user_read = _user_read_obj()
        client, svc = _build_client(
            service_overrides={"github_callback": AsyncMock(
                return_value=(user_read, "acc", "ref")
            )}
        )
        client.get("/api/v1/auth/github/callback?code=x")
        svc.link_github.assert_not_awaited()

    # ── link flow (state=link:{user_id}) ──────────────────────────────────

    def test_link_flow_calls_link_github_with_correct_user_id(self):
        client, svc = _build_client(
            service_overrides={"link_github": AsyncMock(return_value=_user_read_obj())}
        )
        client.get("/api/v1/auth/github/callback?code=ghcode&state=link:user-42")
        svc.link_github.assert_awaited_once_with("user-42", "ghcode")

    def test_link_flow_returns_link_success_html(self):
        client, _ = _build_client(
            service_overrides={"link_github": AsyncMock(return_value=_user_read_obj())}
        )
        resp = client.get("/api/v1/auth/github/callback?code=x&state=link:user-1")
        assert resp.status_code == 200
        assert "link_success" in resp.text

    def test_link_flow_does_not_set_auth_cookies(self):
        """Linking must not issue new auth tokens."""
        client, _ = _build_client(
            service_overrides={"link_github": AsyncMock(return_value=_user_read_obj())}
        )
        resp = client.get("/api/v1/auth/github/callback?code=x&state=link:user-1")
        assert "access_token" not in resp.cookies

    def test_link_flow_service_error_returns_link_error_html(self):
        client, _ = _build_client(
            service_overrides={"link_github": AsyncMock(
                side_effect=HTTPException(status_code=409, detail="Already linked")
            )}
        )
        resp = client.get("/api/v1/auth/github/callback?code=x&state=link:user-1")
        assert resp.status_code == 200
        assert "link_error" in resp.text
        assert "Already linked" in resp.text

    def test_missing_code_param_returns_422(self):
        client, _ = _build_client()
        resp = client.get("/api/v1/auth/github/callback")
        assert resp.status_code == 422


# ════════════════════════════════════════════════════════════════════════════
# GET /link/github  (link start — requires auth)
# ════════════════════════════════════════════════════════════════════════════

class TestLinkGithubStart:
    def setup_method(self):
        _clear_overrides()

    def test_unauthenticated_returns_401(self):
        client, _ = _build_client(current_user=None)
        resp = client.get("/api/v1/auth/link/github", follow_redirects=False)
        assert resp.status_code == 401

    def test_authenticated_redirects_to_github(self):
        user = make_user(id="user-1")
        client, _ = _build_client(current_user=user)
        resp = client.get("/api/v1/auth/link/github", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert "github.com/login/oauth/authorize" in resp.headers["location"]

    def test_state_contains_link_prefix_and_user_id(self):
        user = make_user(id="user-42")
        client, _ = _build_client(current_user=user)
        resp = client.get("/api/v1/auth/link/github", follow_redirects=False)
        location = resp.headers["location"]
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(location).query))
        assert params.get("state") == "link:user-42"

    def test_state_is_plain_string_not_jwt(self):
        """
        Current implementation uses plain 'link:{id}' state (not signed).
        This test documents the current behaviour — it should be updated
        once the signed-JWT state pattern is implemented.
        """
        user = make_user(id="user-1")
        client, _ = _build_client(current_user=user)
        resp = client.get("/api/v1/auth/link/github", follow_redirects=False)
        location = resp.headers["location"]
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(location).query))
        state = params.get("state", "")
        # plain string — not three dot-separated JWT segments
        assert state.count(".") < 2, (
            "State looks like a JWT — update this test and remove the plain-string path"
        )


# ════════════════════════════════════════════════════════════════════════════
# GET /link/github/callback  (requires auth)
# ════════════════════════════════════════════════════════════════════════════

class TestLinkGithubCallback:
    def setup_method(self):
        _clear_overrides()

    def test_unauthenticated_returns_401(self):
        client, _ = _build_client(current_user=None)
        resp = client.get("/api/v1/auth/link/github/callback?code=x")
        assert resp.status_code == 401

    def test_success_returns_link_success_html(self):
        user = make_user(id="user-1")
        client, _ = _build_client(
            service_overrides={"link_github": AsyncMock(return_value=_user_read_obj())},
            current_user=user,
        )
        resp = client.get("/api/v1/auth/link/github/callback?code=ghcode")
        assert resp.status_code == 200
        assert "link_success" in resp.text

    def test_calls_link_github_with_current_user_id(self):
        user = make_user(id="user-99")
        client, svc = _build_client(
            service_overrides={"link_github": AsyncMock(return_value=_user_read_obj())},
            current_user=user,
        )
        client.get("/api/v1/auth/link/github/callback?code=mycode")
        svc.link_github.assert_awaited_once_with("user-99", "mycode")

    def test_service_error_returns_link_error_html(self):
        user = make_user(id="user-1")
        client, _ = _build_client(
            service_overrides={"link_github": AsyncMock(
                side_effect=HTTPException(status_code=409, detail="Taken")
            )},
            current_user=user,
        )
        resp = client.get("/api/v1/auth/link/github/callback?code=x")
        assert "link_error" in resp.text
        assert "Taken" in resp.text


# ════════════════════════════════════════════════════════════════════════════
# DELETE /link/github
# ════════════════════════════════════════════════════════════════════════════

class TestUnlinkGithub:
    def setup_method(self):
        _clear_overrides()

    def test_unauthenticated_returns_401(self):
        client, _ = _build_client(current_user=None)
        resp = client.delete("/api/v1/auth/link/github")
        assert resp.status_code == 401

    def test_returns_user_read(self):
        user = make_user(id="user-1")
        client, _ = _build_client(
            service_overrides={"unlink_github": AsyncMock(return_value=_user_read_obj())},
            current_user=user,
        )
        resp = client.delete("/api/v1/auth/link/github")
        assert resp.status_code == 200
        assert resp.json()["id"] == "user-1"

    def test_calls_unlink_github_with_current_user_id(self):
        user = make_user(id="user-7")
        client, svc = _build_client(
            service_overrides={"unlink_github": AsyncMock(return_value=_user_read_obj())},
            current_user=user,
        )
        client.delete("/api/v1/auth/link/github")
        svc.unlink_github.assert_awaited_once_with("user-7")


# ════════════════════════════════════════════════════════════════════════════
# GET /google  (login start)
# ════════════════════════════════════════════════════════════════════════════

class TestGoogleOAuthStart:
    def setup_method(self):
        _clear_overrides()

    def test_redirects_to_google(self):
        client, _ = _build_client()
        resp = client.get("/api/v1/auth/google", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert "accounts.google.com" in resp.headers["location"]

    def test_redirect_includes_redirect_uri(self):
        client, _ = _build_client()
        resp = client.get("/api/v1/auth/google", follow_redirects=False)
        location = resp.headers["location"]
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(location).query))
        assert "redirect_uri" in params
        assert "google/callback" in params["redirect_uri"]

    def test_redirect_includes_openid_scope(self):
        client, _ = _build_client()
        resp = client.get("/api/v1/auth/google", follow_redirects=False)
        location = resp.headers["location"]
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(location).query))
        assert "openid" in params.get("scope", "")


# ════════════════════════════════════════════════════════════════════════════
# GET /google/callback
# ════════════════════════════════════════════════════════════════════════════

class TestGoogleCallback:
    def setup_method(self):
        _clear_overrides()

    def test_success_sets_cookies_and_returns_success_html(self):
        user_read = _user_read_obj()
        client, _ = _build_client(
            service_overrides={"google_callback": AsyncMock(
                return_value=(user_read, "acc", "ref")
            )}
        )
        resp = client.get("/api/v1/auth/google/callback?code=gcode")
        assert resp.status_code == 200
        assert "oauth_success" in resp.text
        assert "access_token" in resp.cookies

    def test_service_error_returns_error_html(self):
        client, _ = _build_client(
            service_overrides={"google_callback": AsyncMock(
                side_effect=Exception("Google OAuth failed")
            )}
        )
        resp = client.get("/api/v1/auth/google/callback?code=bad")
        assert resp.status_code == 200
        assert "oauth_error" in resp.text

    def test_missing_code_param_returns_422(self):
        client, _ = _build_client()
        resp = client.get("/api/v1/auth/google/callback")
        assert resp.status_code == 422


# ════════════════════════════════════════════════════════════════════════════
# GET /link/google  (link start)
# ════════════════════════════════════════════════════════════════════════════

class TestLinkGoogleStart:
    def setup_method(self):
        _clear_overrides()

    def test_redirects_to_google(self):
        client, _ = _build_client()
        resp = client.get("/api/v1/auth/link/google", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert "accounts.google.com" in resp.headers["location"]

    def test_redirect_uri_points_to_link_google_callback(self):
        """
        /link/google must use the link-specific redirect_uri, not the
        login callback — Google validates this against registered URIs.
        """
        client, _ = _build_client()
        resp = client.get("/api/v1/auth/link/google", follow_redirects=False)
        location = resp.headers["location"]
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(location).query))
        assert "link/google/callback" in params.get("redirect_uri", "")

    def test_login_google_and_link_google_use_different_redirect_uris(self):
        """
        The two flows must register different redirect URIs with Google.
        This test will catch a merge regression.
        """
        client, _ = _build_client()
        login_resp = client.get("/api/v1/auth/google", follow_redirects=False)
        link_resp = client.get("/api/v1/auth/link/google", follow_redirects=False)

        login_params = dict(urllib.parse.parse_qsl(
            urllib.parse.urlparse(login_resp.headers["location"]).query
        ))
        link_params = dict(urllib.parse.parse_qsl(
            urllib.parse.urlparse(link_resp.headers["location"]).query
        ))

        assert login_params.get("redirect_uri") != link_params.get("redirect_uri")


# ════════════════════════════════════════════════════════════════════════════
# GET /link/google/callback  (requires auth)
# ════════════════════════════════════════════════════════════════════════════

class TestLinkGoogleCallback:
    def setup_method(self):
        _clear_overrides()

    def test_unauthenticated_returns_401(self):
        client, _ = _build_client(current_user=None)
        resp = client.get("/api/v1/auth/link/google/callback?code=x")
        assert resp.status_code == 401

    def test_success_returns_link_success_html(self):
        user = make_user(id="user-1")
        client, _ = _build_client(
            service_overrides={"link_google": AsyncMock(return_value=_user_read_obj())},
            current_user=user,
        )
        resp = client.get("/api/v1/auth/link/google/callback?code=gcode")
        assert resp.status_code == 200
        assert "link_success" in resp.text

    def test_calls_link_google_with_current_user_id(self):
        user = make_user(id="user-55")
        client, svc = _build_client(
            service_overrides={"link_google": AsyncMock(return_value=_user_read_obj())},
            current_user=user,
        )
        client.get("/api/v1/auth/link/google/callback?code=mycode")
        svc.link_google.assert_awaited_once_with("user-55", "mycode")

    def test_service_error_returns_link_error_html(self):
        user = make_user(id="user-1")
        client, _ = _build_client(
            service_overrides={"link_google": AsyncMock(
                side_effect=HTTPException(status_code=409, detail="Google taken")
            )},
            current_user=user,
        )
        resp = client.get("/api/v1/auth/link/google/callback?code=x")
        assert "link_error" in resp.text
        assert "Google taken" in resp.text


# ════════════════════════════════════════════════════════════════════════════
# DELETE /link/google
# ════════════════════════════════════════════════════════════════════════════

class TestUnlinkGoogle:
    def setup_method(self):
        _clear_overrides()

    def test_unauthenticated_returns_401(self):
        client, _ = _build_client(current_user=None)
        resp = client.delete("/api/v1/auth/link/google")
        assert resp.status_code == 401

    def test_returns_user_read(self):
        user = make_user(id="user-1")
        client, _ = _build_client(
            service_overrides={"unlink_google": AsyncMock(return_value=_user_read_obj())},
            current_user=user,
        )
        resp = client.delete("/api/v1/auth/link/google")
        assert resp.status_code == 200

    def test_calls_unlink_google_with_current_user_id(self):
        user = make_user(id="user-8")
        client, svc = _build_client(
            service_overrides={"unlink_google": AsyncMock(return_value=_user_read_obj())},
            current_user=user,
        )
        client.delete("/api/v1/auth/link/google")
        svc.unlink_google.assert_awaited_once_with("user-8")


# ════════════════════════════════════════════════════════════════════════════
# POST /refresh
# ════════════════════════════════════════════════════════════════════════════

class TestRefreshEndpoint:
    def setup_method(self):
        _clear_overrides()

    def test_no_refresh_cookie_returns_401(self):
        client, _ = _build_client()
        resp = client.post("/api/v1/auth/refresh")
        assert resp.status_code == 401
        assert "No refresh token" in resp.json()["detail"]

    def test_valid_cookie_returns_200_and_new_cookies(self):
        client, _ = _build_client(
            service_overrides={"refresh": AsyncMock(return_value=("new_acc", "new_ref"))}
        )
        client.cookies.set("refresh_token", "sometoken")
        resp = client.post("/api/v1/auth/refresh")
        assert resp.status_code == 200
        assert "access_token" in resp.cookies

    def test_service_401_is_propagated(self):
        client, _ = _build_client(
            service_overrides={"refresh": AsyncMock(
                side_effect=HTTPException(status_code=401, detail="revoked")
            )}
        )
        client.cookies.set("refresh_token", "bad")
        resp = client.post("/api/v1/auth/refresh")
        assert resp.status_code == 401


# ════════════════════════════════════════════════════════════════════════════
# POST /logout
# ════════════════════════════════════════════════════════════════════════════

class TestLogoutEndpoint:
    def setup_method(self):
        _clear_overrides()

    def test_logout_200_and_clears_cookies(self):
        client, svc = _build_client(
            service_overrides={"logout": AsyncMock(return_value=None)}
        )
        client.cookies.set("access_token", "acc")
        client.cookies.set("refresh_token", "ref")
        resp = client.post("/api/v1/auth/logout")
        assert resp.status_code == 200
        # Cookies should be cleared (max_age=0 or deleted)
        assert resp.cookies.get("access_token") in (None, "")

    def test_logout_calls_service_logout_with_both_tokens(self):
        client, svc = _build_client(
            service_overrides={"logout": AsyncMock(return_value=None)}
        )
        client.cookies.set("access_token", "myacc")
        client.cookies.set("refresh_token", "myref")
        client.post("/api/v1/auth/logout")
        svc.logout.assert_awaited_once_with("myacc", "myref")

    def test_logout_without_cookies_still_200(self):
        client, _ = _build_client(
            service_overrides={"logout": AsyncMock(return_value=None)}
        )
        resp = client.post("/api/v1/auth/logout")
        assert resp.status_code == 200


# ════════════════════════════════════════════════════════════════════════════
# GET /me
# ════════════════════════════════════════════════════════════════════════════

class TestGetMeEndpoint:
    def setup_method(self):
        _clear_overrides()

    def test_no_cookie_returns_401(self):
        client, _ = _build_client(current_user=None)
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_authenticated_returns_user_read(self):
        user = make_user(id="user-1", email="alice@example.com")
        client, _ = _build_client(current_user=user)
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["email"] == "alice@example.com"