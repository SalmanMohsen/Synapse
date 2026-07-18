"""Distributed locking, fencing tokens, and active job registration (Step 8).

Implements exclusive resource locks ordered alphabetically, monotonically increasing
fencing tokens, active run registry tracking, and semantic conflict checks using
the Codebase Manifest and local LLM reasoning.
"""

import json
import logging
from typing import Any, Dict, List
from openai import AsyncOpenAI

from app.config import LOCK_TTL_SECONDS, LLM_BASE_URL, LLM_MODEL_NAME
from app.db import codebase_manifest, get_connection

logger = logging.getLogger(__name__)


class LockError(RuntimeError):
    """Base distributed lock exception."""


class LockConflictError(LockError):
    """Raised when a target file is already exclusively locked."""


class SemanticConflictError(LockError):
    """Raised when another in-flight run addresses the same underlying purpose."""


class StaleTokenError(LockError):
    """Raised when a fencing token is found to be stale (fenced out)."""


import redis.asyncio as aioredis
from app.config import REDIS_URL

_redis: aioredis.Redis | None = None


def get_redis_client() -> aioredis.Redis:
    """Returns a shared, lazily initialized async Redis client connection."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


async def fetch_file_purposes(project_id: str, file_paths: List[str]) -> List[str]:
    """Queries the codebase manifest for the purpose summaries of the target files."""
    if not file_paths:
        return []
    from sqlalchemy import select

    async with get_connection() as conn:
        stmt = (
            select(codebase_manifest.c.purpose_summary)
            .where(
                codebase_manifest.c.project_id == project_id,
                codebase_manifest.c.file_path.in_(file_paths)
            )
        )
        result = await conn.execute(stmt)
        return [row[0] for row in result if row[0]]


async def check_semantic_conflict(purpose_a: str, purpose_b: str) -> bool:
    """Asks the local LLM if two tasks conflict or address the same underlying logic.

    Uses zero-temperature instruction matching to enforce consistency.
    """
    client = AsyncOpenAI(base_url=LLM_BASE_URL, api_key="not-needed")
    try:
        response = await client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a Senior Technical Architect analyzing concurrent agent executions.\n"
                        "Your task is to determine if two engineering descriptions are addressing the same "
                        "underlying issue, feature, or code correction (which would cause a logical/semantic conflict).\n"
                        "Respond with EXACTLY 'YES' if they conflict or have the same underlying purpose, "
                        "and EXACTLY 'NO' if they are unrelated and can safely run concurrently."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Task A:\n{purpose_a}\n\n"
                        f"Task B:\n{purpose_b}\n\n"
                        "Do these tasks conflict or address the same underlying purpose? Answer strictly YES or NO."
                    )
                }
            ],
            temperature=0.0,
            max_tokens=5,
        )
        ans = response.choices[0].message.content.strip().upper()
        return "YES" in ans
    except Exception as e:
        logger.warning("LLM semantic conflict check failed: %s. Proceeding conservatively.", e)
        return False


async def register_step_and_acquire_locks(
    run_id: str,
    project_id: str,
    ticket_id: str,
    step_number: int,
    file_paths: List[str],
    purpose_summary: str,
) -> int:
    """Registers the active step, runs concurrency checks, and locks files.

    Alphabetically orders file acquisition to prevent deadlocks.
    Generates a monotonically increasing fencing token using Redis INCR.
    """
    redis = get_redis_client()

    # 1. Active Job Registry & Semantic Conflict Verification
    active_keys = await redis.keys("synapse:active_job:*")
    for key in active_keys:
        other_run_id = key.split(":")[-1]
        if other_run_id == run_id:
            continue

        val = await redis.get(key)
        if not val:
            continue

        other_job = json.loads(val)
        # Symmetrical project isolation: only evaluate concurrent runs on the same project
        if other_job.get("project_id") != project_id:
            continue

        # Check physical file lock overlap
        other_files = set(other_job.get("files", []))
        overlap = set(file_paths).intersection(other_files)
        if overlap:
            raise LockConflictError(
                f"File conflict detected! Target file(s) {list(overlap)} are already locked "
                f"by concurrent active run {other_run_id} (ticket {other_job.get('ticket_id')})."
            )

        # Check semantic purposes via manifest file summaries
        other_files_list = list(other_files)
        other_file_purposes = await fetch_file_purposes(project_id, other_files_list)

        combined_other_purpose = other_job.get("purpose_summary", "")
        if other_file_purposes:
            combined_other_purpose += "\nFile purposes:\n" + "\n".join(other_file_purposes)

        is_conflict = await check_semantic_conflict(purpose_summary, combined_other_purpose)
        if is_conflict:
            raise SemanticConflictError(
                f"Semantic conflict detected! Concurrent run {other_run_id} is active on different "
                f"files but addresses the same underlying intent: '{other_job.get('purpose_summary')}'"
            )

    # 2. Monotonic fencing counter generation
    fencing_token = await redis.incr("synapse:fencing:counter")

    # 3. Add to Registry
    job_data = {
        "run_id": run_id,
        "project_id": project_id,
        "ticket_id": ticket_id,
        "step_number": step_number,
        "files": file_paths,
        "purpose_summary": purpose_summary,
        "fencing_token": fencing_token,
    }
    await redis.set(
        f"synapse:active_job:{run_id}",
        json.dumps(job_data),
        ex=LOCK_TTL_SECONDS
    )

    # 4. Exclusive lock acquisition in alphabetical order (deadlock prevention)
    sorted_files = sorted(list(file_paths))
    for fp in sorted_files:
        lock_key = f"synapse:lock:file:{project_id}:{fp}"
        lock_data = {
            "run_id": run_id,
            "token": fencing_token,
        }
        # NX=True guarantees mutual exclusion (set if not exists)
        success = await redis.set(
            lock_key,
            json.dumps(lock_data),
            nx=True,
            ex=LOCK_TTL_SECONDS
        )
        if not success:
            # Symmetrical rollback: release any acquired lock keys if acquisition fails midway
            await release_locks(run_id, project_id, file_paths)
            raise LockConflictError(f"Failed to acquire exclusive file lock on path: {fp}")

    return fencing_token


async def acquire_dynamic_locks(
    run_id: str,
    project_id: str,
    file_paths: List[str],
    fencing_token: int,
) -> None:
    """Locks newly discovered files mid-step, maintaining order and registry hygiene."""
    redis = get_redis_client()
    sorted_files = sorted(list(file_paths))

    for fp in sorted_files:
        lock_key = f"synapse:lock:file:{project_id}:{fp}"
        lock_data = {
            "run_id": run_id,
            "token": fencing_token,
        }
        success = await redis.set(
            lock_key,
            json.dumps(lock_data),
            nx=True,
            ex=LOCK_TTL_SECONDS
        )
        if not success:
            raise LockConflictError(
                f"Dynamic locking failed: path {fp} is locked by another run."
            )

    # Update active registry with new files
    registry_key = f"synapse:active_job:{run_id}"
    val = await redis.get(registry_key)
    if val:
        job_data = json.loads(val)
        existing_files = set(job_data.get("files", []))
        existing_files.update(file_paths)
        job_data["files"] = list(existing_files)
        await redis.set(registry_key, json.dumps(job_data), ex=LOCK_TTL_SECONDS)


async def assert_token_is_latest(project_id: str, file_paths: List[str], fencing_token: int) -> None:
    """Enforces Martin Kleppmann's fencing token validations right before writes."""
    redis = get_redis_client()
    for fp in file_paths:
        lock_key = f"synapse:lock:file:{project_id}:{fp}"
        val = await redis.get(lock_key)
        if not val:
            raise StaleTokenError(f"File lock lease on {fp} has expired or was removed.")
        data = json.loads(val)
        if data.get("token", 0) > fencing_token:
            raise StaleTokenError(
                f"Fencing violation: lock on {fp} has been overtaken by a newer run "
                f"(active token {data['token']} > ours {fencing_token})."
            )


async def release_locks(run_id: str, project_id: str, file_paths: List[str]) -> None:
    """Safely clears active job status and releases all owned file leases."""
    redis = get_redis_client()
    for fp in file_paths:
        lock_key = f"synapse:lock:file:{project_id}:{fp}"
        val = await redis.get(lock_key)
        if val:
            data = json.loads(val)
            if data.get("run_id") == run_id:
                await redis.delete(lock_key)

    await redis.delete(f"synapse:active_job:{run_id}")