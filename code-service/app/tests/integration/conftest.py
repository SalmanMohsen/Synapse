"""Phase 0 integration test infrastructure (code-service).

Redis is the priority here — it's where locks/guardrails/fencing tokens
live (Phase 2b #1/#2). Postgres is secondary: code-service reads/writes a
handful of shared tables through its own Core table mirror in app.db.

CRITICAL ORDERING NOTE — read before touching this file:
app/config.py reads REDIS_URL and CODE_DATABASE_URL from os.environ at
MODULE IMPORT time, and app/locks.py does `from app.config import
REDIS_URL` — a value copy, not a live reference to app.config. Any test
module in this directory that imports app.locks (or anything importing
app.config transitively) freezes onto whatever REDIS_URL/CODE_DATABASE_URL
were set to AT THAT IMPORT.

Pytest imports a directory's conftest.py before it imports that directory's
sibling test_*.py files. A @pytest.fixture doesn't run until the "call"
phase, well after collection/import has already finished — too late to
matter here. So the container startup below is bare module-level code, not
a fixture, specifically so it executes during conftest.py's own import,
before any test module gets a chance to import app.config with the wrong
values baked in.
"""

import os

from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

_pg = PostgresContainer("postgres:17-alpine", driver="asyncpg")
_pg.start()
os.environ["CODE_DATABASE_URL"] = _pg.get_connection_url()

_redis = RedisContainer("redis:7-alpine")
_redis.start()
os.environ["REDIS_URL"] = (
    f"redis://{_redis.get_container_host_ip()}:{_redis.get_exposed_port(_redis.port)}/0"
)


def pytest_sessionfinish(session, exitstatus):
    _redis.stop()
    _pg.stop()


# --- Safe to import app.* below this line: env vars point at the containers.

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import (
    agent_run_status_enum,
    agent_run_step_phase_enum,
    agent_run_step_status_enum,
    check_tier_enum,
    message_type_enum,
    metadata,
    ticket_status_enum,
)

_ENUMS = [
    agent_run_status_enum,
    agent_run_step_status_enum,
    check_tier_enum,
    agent_run_step_phase_enum,
    message_type_enum,
    ticket_status_enum,
]


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_schema():
    """Builds the schema from code-service's OWN Core table definitions,
    not backend's Alembic chain — per the locked Phase 0.3 decision
    (code-service doesn't own migrations).

    Trade-off, stated plainly rather than left implicit: this proves
    code-service's Core layer is internally self-consistent. It does NOT
    prove this mirror still matches backend's actual migrated schema —
    that drift risk is exactly the "unvalidated GitProvider path" class of
    gap already flagged in memory, and Phase 0 doesn't close it. If that
    guarantee is wanted, the alternative is pointing this fixture at
    backend's real Alembic migrations instead — flag it back if you'd
    rather have that instead of this lighter-weight version.

    Uses its own throwaway engine, disposed immediately after setup —
    deliberately not the module-level app.db.engine — so nothing async
    created here is still alive for a later test to inherit across a
    different event loop (see pg_conn's docstring below for why that
    matters).
    """
    setup_engine = create_async_engine(os.environ["CODE_DATABASE_URL"])
    try:
        async with setup_engine.begin() as conn:
            for enum in _ENUMS:
                values = ", ".join(f"'{v}'" for v in enum.enums)
                await conn.execute(text(f"CREATE TYPE {enum.name} AS ENUM ({values})"))
            await conn.run_sync(metadata.create_all)
    finally:
        await setup_engine.dispose()
    yield


@pytest_asyncio.fixture
async def pg_conn():
    """A fresh engine + connection + rolled-back transaction for THIS test
    only — not the module-level app.db.engine, and not shared with any
    other test. An earlier version reused app.db.engine across tests and
    hit "attached to a different loop" errors from asyncpg in a real run
    (reproducible with real Postgres, not with a toy asyncio repro) —
    apparently from anyio's own pytest plugin (pulled in transitively by
    httpx) interacting with pytest-asyncio's loop management. Rather than
    keep chasing that interaction, every fixture here is fully
    self-contained per test."""
    engine = create_async_engine(os.environ["CODE_DATABASE_URL"])
    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                yield conn
            finally:
                await trans.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def redis_client():
    """A fresh client for THIS test only — deliberately NOT app.locks's
    get_redis_client(), which caches a single client in a module-level
    global and reuses it across every call. That's fine in production
    (one process, one loop) but is exactly the shared-across-tests pattern
    that caused the loop-mismatch failures noted above."""
    import redis.asyncio as aioredis

    client = aioredis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    try:
        yield client
        await client.flushdb()
    finally:
        await client.aclose()