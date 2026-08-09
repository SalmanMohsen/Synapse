"""Phase 0 checkpoint: prove the fixtures actually work before anything is
built on top of them. Run with: pytest -m integration
"""

from sqlalchemy import text

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_container_migrates_and_table_exists(db_session):
    """Postgres container starts, Alembic runs to head, a real table exists."""
    result = await db_session.execute(
        text("SELECT to_regclass('public.tickets')")
    )
    assert result.scalar() is not None, "tickets table missing — did Alembic run?"


@pytest.mark.asyncio
async def test_session_rolls_back_between_tests(db_session):
    """Companion to the test above: if isolation were broken, a leftover
    row from another test inserted directly against `users` would show up
    here. Asserting the table is empty is the isolation proof, not the
    tickets-table check above (which only proves migrations ran)."""
    result = await db_session.execute(text("SELECT count(*) FROM users"))
    assert result.scalar() == 0


@pytest.mark.asyncio
async def test_redis_container_reachable(redis_client):
    assert await redis_client.ping() is True


@pytest.mark.asyncio
async def test_client_fixture_reaches_the_real_app(client):
    """No auth cookie set, so this should 401, not 500 — proves the app
    booted, routing works, and get_db/get_redis overrides didn't blow up
    dependency resolution. GET /{workspace_id} chosen specifically because
    it takes no request body, so get_current_user is the only thing that
    can reject the request."""
    response = await client.get("/api/v1/workspaces/nonexistent-id")
    assert response.status_code == 401