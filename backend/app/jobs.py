"""Shared arq producer helper for enqueueing jobs to planning-service.

Replaces an earlier BullMQ-based draft — BullMQ is a Node.js library, and
using it from a pure-Python stack (this backend + planning-service, both
FastAPI/SQLAlchemy/asyncio) added a cross-language dependency neither service
needed. arq is async-native: job functions are `async def` and run directly
on the worker's event loop (no per-task event-loop wrapping), and it needs
nothing beyond the Redis already provisioned.

Job (function) names below are what planning-service's worker (step 6) will
register in its WorkerSettings.functions list — an implementation choice on
my part, not pulled from a locked spec.
"""

import os

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

JOB_INGEST_REPOSITORY = "ingest_repository_job"
JOB_GENERATE_PLAN = "generate_plan"  
JOB_EXECUTE_PLAN = "execute_plan_job" 

_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis:
    """Lazily creates a single shared arq connection pool for this process.

    Ideally created once via FastAPI's lifespan and torn down on shutdown
    rather than lazily here — wire that into main.py when convenient; I don't
    have visibility into that file to edit it blindly. This mirrors the same
    lazy-singleton pattern already used in planning-service's qdrant_store.py.
    """
    global _pool
    if _pool is None:
        redis_url = os.environ["REDIS_URL"]
        _pool = await create_pool(RedisSettings.from_dsn(redis_url))
    return _pool