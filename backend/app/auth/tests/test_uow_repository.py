"""
Unit tests for app.auth.uow and app.auth.repository
─────────────────────────────────────────────────────
UoW tests: context-manager protocol, commit, rollback on exception.
Repository tests: all query and mutation methods using an async mock session.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from app.auth.repository import UserRepository
from app.auth.uow import AbstractAuthUnitOfWork, SqlAlchemyAuthUnitOfWork


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

def _make_async_result(scalar_value):
    """Return a fake SQLAlchemy execute result whose scalar_one_or_none returns a value."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_value
    return result


def _mock_session(query_return=None):
    """Build an AsyncMock session whose execute() resolves to query_return."""
    session = AsyncMock()
    session.execute.return_value = _make_async_result(query_return)
    return session


# ════════════════════════════════════════════════════════════════════════════
# SqlAlchemyUnitOfWork
# ════════════════════════════════════════════════════════════════════════════

class TestSqlAlchemyUnitOfWork:
    @pytest.mark.asyncio
    async def test_aenter_returns_self(self):
        session = _mock_session()
        uow = SqlAlchemyAuthUnitOfWork(session)

        result = await uow.__aenter__()
        assert result is uow

    @pytest.mark.asyncio
    async def test_commit_calls_session_commit(self):
        session = _mock_session()
        uow = SqlAlchemyAuthUnitOfWork(session)

        await uow.commit()

        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rollback_calls_session_rollback(self):
        session = _mock_session()
        uow = SqlAlchemyAuthUnitOfWork(session)

        await uow.rollback()

        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_triggers_rollback_not_commit(self):
        session = _mock_session()
        uow = SqlAlchemyAuthUnitOfWork(session)

        with pytest.raises(ValueError):
            async with uow:
                raise ValueError("something went wrong")

        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_users_attribute_is_user_repository(self):
        session = _mock_session()
        uow = SqlAlchemyAuthUnitOfWork(session)

        assert isinstance(uow.users, UserRepository)

    @pytest.mark.asyncio
    async def test_context_manager_no_exception_does_not_auto_commit(self):
        """The UoW does NOT auto-commit; callers must call commit() explicitly."""
        session = _mock_session()
        uow = SqlAlchemyAuthUnitOfWork(session)

        async with uow:
            pass  # no explicit commit

        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_abstract_uow_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            AbstractAuthUnitOfWork()  # type: ignore[abstract]


# ════════════════════════════════════════════════════════════════════════════
# UserRepository
# ════════════════════════════════════════════════════════════════════════════

class TestUserRepository:

    # ── get_by_id ─────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_by_id_returns_user_when_found(self):
        user = MagicMock()
        session = _mock_session(user)
        repo = UserRepository(session)

        result = await repo.get_by_id("user-123")

        assert result is user
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_by_id_returns_none_when_not_found(self):
        session = _mock_session(None)
        repo = UserRepository(session)

        result = await repo.get_by_id("nonexistent")

        assert result is None

    # ── get_by_email ──────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_by_email_returns_user_when_found(self):
        user = MagicMock()
        session = _mock_session(user)
        repo = UserRepository(session)

        result = await repo.get_by_email("alice@example.com")

        assert result is user

    @pytest.mark.asyncio
    async def test_get_by_email_returns_none_when_not_found(self):
        session = _mock_session(None)
        repo = UserRepository(session)

        result = await repo.get_by_email("nobody@example.com")

        assert result is None

    # ── get_by_github_id ──────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_by_github_id_returns_user_when_found(self):
        user = MagicMock()
        session = _mock_session(user)
        repo = UserRepository(session)

        result = await repo.get_by_github_id("gh-123")

        assert result is user

    @pytest.mark.asyncio
    async def test_get_by_github_id_returns_none_when_not_found(self):
        session = _mock_session(None)
        repo = UserRepository(session)

        result = await repo.get_by_github_id("gh-unknown")

        assert result is None

    # ── get_by_google_id ──────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_by_google_id_returns_user_when_found(self):
        user = MagicMock()
        session = _mock_session(user)
        repo = UserRepository(session)

        result = await repo.get_by_google_id("g-456")

        assert result is user

    @pytest.mark.asyncio
    async def test_get_by_google_id_returns_none_when_not_found(self):
        session = _mock_session(None)
        repo = UserRepository(session)

        result = await repo.get_by_google_id("g-unknown")

        assert result is None

    # ── create ────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_adds_user_to_session_and_flushes(self):
        session = AsyncMock()
        session.refresh = AsyncMock(side_effect=lambda u: None)
        repo = UserRepository(session)

        from app.auth.models import User
        with patch.object(User, "__init__", lambda self, **kw: None):
            # We can't easily test the real ORM model without a DB,
            # so we verify that add + flush + refresh are all called.
            fake_user = MagicMock(spec=User)
            with patch("app.auth.repository.User", return_value=fake_user):
                result = await repo.create(email="a@b.com", display_name="A")

        session.add.assert_called_once_with(fake_user)
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(fake_user)
        assert result is fake_user

    # ── update ────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_update_sets_attributes_and_flushes(self):
        session = AsyncMock()
        session.refresh = AsyncMock(side_effect=lambda u: None)
        repo = UserRepository(session)

        user = MagicMock()
        result = await repo.update(user, display_name="New Name", avatar_url="http://x.com/a.png")

        assert user.display_name == "New Name"
        assert user.avatar_url == "http://x.com/a.png"
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(user)
        assert result is user

    @pytest.mark.asyncio
    async def test_update_with_no_kwargs_leaves_user_unchanged(self):
        session = AsyncMock()
        session.refresh = AsyncMock(side_effect=lambda u: None)
        repo = UserRepository(session)

        user = MagicMock()
        original_email = user.email

        result = await repo.update(user)

        assert result is user
        assert user.email == original_email
        session.flush.assert_awaited_once()