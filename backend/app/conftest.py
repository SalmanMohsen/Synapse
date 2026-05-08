"""
Root conftest for all Synapse backend unit tests.

Fixtures here are visible to every test under app/.
make_user lives in app.auth.tests.helpers so tests can import it directly
without relying on pytest's sys.path injection of this file.
"""
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── set env vars BEFORE any app import so lru_cache picks them up ─────────────
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-that-is-long-enough")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")
os.environ.setdefault("BACKEND_URL", "http://localhost:8000")
os.environ.setdefault("GITHUB_CLIENT_ID", "test-gh-client-id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-gh-client-secret")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-g-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-g-client-secret")

from app.config import get_settings
get_settings.cache_clear()

# Re-export make_user so conftest fixtures below can use it,
# and so existing code that does `from conftest import make_user` still works.
from app.auth.tests.helpers import make_user  # noqa: E402


# ── Fakes ─────────────────────────────────────────────────────────────────────

class FakeRedis:
    """Minimal in-memory async Redis stub."""

    def __init__(self):
        self._store: dict[str, tuple[str, int | None]] = {}

    async def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        return entry[0] if entry else None

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = (value, ttl)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def is_revoked(self, jti: str) -> bool:
        return f"revoked:{jti}" in self._store


class FakeUserRepository:
    """In-memory stand-in for UserRepository."""

    def __init__(self):
        self._users: dict[str, object] = {}
        self._by_email: dict[str, str] = {}
        self._by_github: dict[str, str] = {}
        self._by_google: dict[str, str] = {}

    def seed(self, user) -> None:
        self._users[user.id] = user
        self._by_email[user.email] = user.id
        if user.github_user_id:
            self._by_github[user.github_user_id] = user.id
        if user.google_user_id:
            self._by_google[user.google_user_id] = user.id

    async def get_by_id(self, user_id: str):
        return self._users.get(user_id)

    async def get_by_email(self, email: str):
        uid = self._by_email.get(email)
        return self._users.get(uid) if uid else None

    async def get_by_github_id(self, github_id: str):
        uid = self._by_github.get(github_id)
        return self._users.get(uid) if uid else None

    async def get_by_google_id(self, google_id: str):
        uid = self._by_google.get(google_id)
        return self._users.get(uid) if uid else None

    async def create(self, **kwargs) -> object:
        user = make_user(**kwargs)
        self.seed(user)
        return user

    async def update(self, user, **kwargs) -> object:
        for k, v in kwargs.items():
            setattr(user, k, v)
        self._by_github = {u.github_user_id: u.id for u in self._users.values() if u.github_user_id}
        self._by_google = {u.google_user_id: u.id for u in self._users.values() if u.google_user_id}
        return user


class FakeUnitOfWork:
    """Minimal UoW. commit/rollback are no-ops."""

    def __init__(self, user_repo: FakeUserRepository | None = None):
        self.users = user_repo or FakeUserRepository()
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            await self.rollback()

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def user_repo():
    return FakeUserRepository()


@pytest.fixture
def fake_uow(user_repo):
    return FakeUnitOfWork(user_repo)


@pytest.fixture
def auth_service(fake_uow, fake_redis):
    from app.auth.service import AuthService
    return AuthService(fake_uow, fake_redis)