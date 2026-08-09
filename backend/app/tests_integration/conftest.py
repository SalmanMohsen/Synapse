"""Phase 0 integration test infrastructure (backend).

Real Postgres + Redis via testcontainers. No fakes here — that's what the
existing `*/tests` unit suites already cover; this directory exists to prove
things a fake can't (real FK/constraint enforcement, real Alembic-migrated
schema, real dependency-injected FastAPI app).

Import-order note (read before editing):
`app.database` builds its global `engine`/`AsyncSessionFactory` from
`get_settings().database_url` AT MODULE IMPORT TIME, and `get_settings` is
`@lru_cache`d. `backend/alembic/env.py` also unconditionally re-reads
`get_settings().database_url` on every `command.upgrade()` invocation. So the
container has to be started and `DATABASE_URL` set + the settings cache
cleared BEFORE anything under `app.*` is imported, or those modules will
freeze in the wrong URL. That's why the `app.*` imports below are deferred
into the fixture bodies instead of sitting at module top.

No session-scoped async engine, on purpose:
An earlier version shared one AsyncEngine across the whole test session
(session-scoped fixture) with `asyncio_default_fixture_loop_scope = session`
to keep every test on one event loop. That's the textbook-correct pattern,
and it worked in isolation — but broke in a real run alongside `anyio`'s own
pytest plugin (installed transitively via httpx), producing "attached to a
different loop" errors that weren't reproducible in a minimal repro. Rather
than chase that interaction further, every fixture below creates and
disposes its own engine/connection within a single test. Slightly slower
(a fresh connection pool per test), but nothing is ever handed from one
test's event loop to another's, so there's no scope to get wrong.
"""

import os
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

BACKEND_ROOT = Path(__file__).resolve().parents[2]  # backend/


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as pg:
        yield pg


@pytest.fixture(scope="session")
def redis_container():
    with RedisContainer("redis:7-alpine") as rc:
        yield rc


@pytest.fixture(scope="session")
def migrated_db_url(postgres_container):
    """Point Settings at the container, then run the real Alembic migrations
    once for the whole session. This fixture only ever produces a URL
    string — it doesn't hold onto any connection object, so there's nothing
    here for a later test to inherit across a different event loop.

    Runs command.upgrade() from a sync fixture on purpose: env.py's
    run_migrations_online() does its own asyncio.run() internally, which
    raises if called from inside an already-running event loop.

    Uses pytest.MonkeyPatch (not raw os.environ[...] = ...) specifically so
    DATABASE_URL is restored and the settings cache is cleared again at
    teardown. Without that, this fixture's side effects are process-wide
    and permanent for the rest of the run — which is exactly what broke
    auth/tests' JWT tests when the full suite (not just -m integration) was
    run: get_settings.cache_clear() firing here forced a fresh Settings()
    read elsewhere in the same process, and if that read picked up a
    different JWT_SECRET_KEY than whatever was active when a token was
    signed, verification failed downstream in an unrelated test. This
    fixture's job is to affect ONLY the tests that ask for it.
    """
    url = postgres_container.get_connection_url()

    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", url)
    from app.config import get_settings

    get_settings.cache_clear()
    assert get_settings().database_url == url  # fail loudly, not silently, if this drifts

    alembic_cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(alembic_cfg, "head")

    yield url

    mp.undo()
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def db_session(migrated_db_url):
    """A fresh engine, connection, and transaction for THIS test only.

    join_transaction_mode="create_savepoint" means the UoW's own
    session.commit() calls (which the app code calls unconditionally) land
    as SAVEPOINT releases, not real commits — the trans.rollback() below
    undoes everything regardless of how many times the app "committed"
    during the test.
    """
    engine = create_async_engine(migrated_db_url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            session_factory = async_sessionmaker(
                bind=conn,
                join_transaction_mode="create_savepoint",
                expire_on_commit=False,
            )
            session = session_factory()
            try:
                yield session
            finally:
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def redis_client(redis_container):
    import redis.asyncio as aioredis

    client = aioredis.Redis(
        host=redis_container.get_container_host_ip(),
        port=int(redis_container.get_exposed_port(redis_container.port)),
        decode_responses=True,
    )
    try:
        yield client
        await client.flushdb()
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def client(db_session, redis_client):
    """httpx AsyncClient over the real app, with get_db/get_redis overridden.

    Deliberately does NOT run FastAPI's lifespan (ASGITransport skips it by
    default), so app.main's own `app.state.redis = aioredis.from_url(...)`
    never runs. That's fine: get_redis is fully overridden below, and no
    router reads app.state.redis directly — they all go through the
    get_redis dependency.
    """
    from app.database import get_db
    from app.auth.dependencies import get_redis
    from app.main import app

    async def override_get_db():
        yield db_session

    async def override_get_redis():
        return redis_client

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()