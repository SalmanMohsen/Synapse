"""Phase 0 integration test infrastructure (planning-service).

Same ordering constraint as code-service's conftest — read that docstring
first if you haven't. Short version: app/config.py reads PLANNING_DATABASE_URL
/ QDRANT_URL from os.environ, some as frozen module-level names imported
elsewhere (must be set before first app.* import), some read live inside
functions at call time (QDRANT_URL in qdrant_store.get_client() — more
forgiving, but we set it early regardless for consistency). Containers are
started as bare module-level code for the same reason: this file is
imported by pytest before any sibling test_*.py file gets a chance to.
"""

import os

from testcontainers.community.postgres import PostgresContainer
from testcontainers.qdrant import QdrantContainer

_pg = PostgresContainer("postgres:17-alpine", driver="asyncpg")
_pg.start()
os.environ["PLANNING_DATABASE_URL"] = _pg.get_connection_url()

# app/config.py requires REDIS_URL, LLM_BASE_URL, LLM_MODEL_NAME
# unconditionally at import time (os.environ["X"], no default) even though
# none of Phase 0's tests touch Redis or the LLM client. Nothing here
# starts a real Redis container or LLM server — these are placeholders
# only so `from app.db import ...` (which pulls in app.config transitively)
# doesn't crash before it even gets to what this test actually needs.
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("LLM_BASE_URL", "http://localhost:0")
os.environ.setdefault("LLM_MODEL_NAME", "unused-in-phase-0")

# Pinned to match docker-compose's qdrant/qdrant:v1.10.0 and the
# qdrant-client<1.16.0 pin in requirements.txt — NOT testcontainers'
# default (v1.16.2 at time of writing), which is newer than the pinned
# client supports.
_qdrant = QdrantContainer(image="qdrant/qdrant:v1.10.0")
_qdrant.start()
os.environ["QDRANT_URL"] = f"http://{_qdrant.rest_host_address}"


def pytest_sessionfinish(session, exitstatus):
    _qdrant.stop()
    _pg.stop()


# --- Safe to import app.* below this line: env vars point at the containers.

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import (
    agent_run_status_enum,
    agent_run_step_phase_enum,
    agent_run_step_status_enum,
    message_type_enum,
    metadata,
    ticket_status_enum,
)

_ENUMS = [
    agent_run_status_enum,
    agent_run_step_status_enum,
    agent_run_step_phase_enum,
    message_type_enum,
    ticket_status_enum,
]


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_schema():
    """Same trade-off as code-service's conftest: built from planning-
    service's own Core table mirror, not backend's Alembic chain. Proves
    internal consistency, not drift-freedom against the real migrated
    schema. See code-service/tests/integration/conftest.py's docstring for
    the fuller version of this note — not repeating it twice in full.

    Own throwaway engine, disposed right after setup — see pg_conn's
    docstring for why nothing async is shared across tests here."""
    setup_engine = create_async_engine(os.environ["PLANNING_DATABASE_URL"])
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
    only. See code-service/tests/integration/conftest.py's pg_conn
    docstring for why this isn't a shared/module-level engine — the short
    version: a session-scoped shared async engine reused across tests hit
    real "attached to a different loop" errors from asyncpg in an actual
    run, apparently from an interaction with anyio's own pytest plugin."""
    engine = create_async_engine(os.environ["PLANNING_DATABASE_URL"])
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
async def qdrant_client():
    from qdrant_client import AsyncQdrantClient

    client = AsyncQdrantClient(url=os.environ["QDRANT_URL"])
    yield client
    for collection in (await client.get_collections()).collections:
        await client.delete_collection(collection.name)
    await client.close()