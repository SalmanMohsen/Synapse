"""Phase 0 checkpoint for code-service. Run with: pytest -m integration"""

import asyncio

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.mark.asyncio
async def test_redis_container_reachable(redis_client):
    assert await redis_client.ping() is True


@pytest.mark.asyncio
async def test_schema_created(pg_conn):
    """Postgres container starts, code-service's own Core metadata.create_all()
    ran, a real table exists — the code-service equivalent of backend's
    'migration ran' smoke check (no Alembic here, see conftest docstring)."""
    from sqlalchemy import text

    result = await pg_conn.execute(text("SELECT to_regclass('public.agent_runs')"))
    assert result.scalar() is not None


@pytest.mark.asyncio
async def test_real_lock_acquire_and_release(redis_client):
    """Not a fake — a fake can't prove mutual exclusion across real workers.
    Acquire with SET NX, confirm a second acquire attempt is correctly
    rejected while held, release, confirm a third attempt then succeeds."""
    key = "lock:repo_id:smoke_test_file.py"

    first = await redis_client.set(key, "worker-1", nx=True, ex=30)
    assert first is True

    second = await redis_client.set(key, "worker-2", nx=True, ex=30)
    assert second is None  # rejected: worker-1 still holds it

    await redis_client.delete(key)

    third = await redis_client.set(key, "worker-2", nx=True, ex=30)
    assert third is True


@pytest.mark.asyncio
async def test_concurrent_workers_race_the_same_lock(redis_client):
    """The actual claim under test in Phase 2b #1: two real concurrent
    asyncio tasks racing SET NX on the same key — exactly one wins."""
    key = "lock:repo_id:concurrent_smoke.py"
    results = []

    async def try_acquire(worker_id: str):
        acquired = await redis_client.set(key, worker_id, nx=True, ex=30)
        results.append((worker_id, acquired))

    await asyncio.gather(try_acquire("a"), try_acquire("b"))

    winners = [r for r in results if r[1] is True]
    assert len(winners) == 1