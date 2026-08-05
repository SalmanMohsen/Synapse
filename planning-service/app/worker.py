"""arq worker entrypoint for planning-service.

Run via: arq app.worker.WorkerSettings

Job names/payloads must match what the backend enqueues:
- ingest_repository_job: {project_id} — backend/app/github/service.py
- generate_plan_job: {ticket_id, agent_run_id} — backend/app/ticket/service.py
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from arq import Retry, func
from arq.connections import RedisSettings
from openai import AsyncOpenAI
from sqlalchemy import select, update, insert
from transformers import AutoTokenizer

from app import config
from app.db import (
    close_engine,
    get_engine,
    get_connection,
    tickets,
    channels,
    messages,
    skill_files,
    skill_assignments,
    agent_runs,
    create_agent_run_step,
    complete_agent_run_step,
    fail_agent_run_step,
)
from app.ingestion.service import ingest_repository
from app.ingestion.embeddings import _get_model, embed_query
from app.ingestion.qdrant_store import retrieve_chunks
from app.agent.planner import generate_development_plan, run_scope_gate, ScopeGateRejected
from app.agent.validation import validate_development_plan_grounding, FileGroundingValidationError

# Set up logging format for long-running worker output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


# --- Helper: Serialize Datetime for WebSocket Redis Pub/Sub ---
def _json_dumps(obj: Any) -> str:
    return json.dumps(
        obj,
        default=lambda x: x.isoformat() if isinstance(x, datetime) else str(x)
    )


async def startup(ctx: Dict[Any, Any]) -> None:
    """Pre-initialize shared connections and weights on worker startup."""
    logger.info("Starting up planning-service arq worker...")

    # 1. Warm up the database engine pool
    ctx["db_engine"] = get_engine()

    # 2. Warm up the SentenceTransformer embedding model
    logger.info(
        "Pre-loading SentenceTransformer weights (%s)...",
        config.EMBEDDING_MODEL_NAME,
    )
    ctx["embeddings_model"] = _get_model()

    # 3. vLLM client + Qwen tokenizer
    llm_base_url = config.LLM_BASE_URL
    llm_model_name = config.LLM_MODEL_NAME

    ctx["llm_client"] = AsyncOpenAI(base_url=llm_base_url, api_key="not-needed")
    ctx["llm_model_name"] = llm_model_name

    logger.info("Loading Qwen tokenizer (%s)...", llm_model_name)
    tokenizer = AutoTokenizer.from_pretrained(llm_model_name)
    ctx["tokenizer"] = tokenizer
    ctx["count_tokens_fn"] = lambda text: len(tokenizer.encode(text))

    logger.info("Planning-service worker startup complete and ready to process jobs.")


async def shutdown(ctx: Dict[Any, Any]) -> None:
    """Gracefully release connection pools and file handles on exit."""
    logger.info("Shutting down planning-service worker...")

    llm_client = ctx.get("llm_client")
    if llm_client is not None:
        await llm_client.close()

    await close_engine()

    logger.info("Planning-service worker shutdown complete.")


# ------------------------------------------------------------------ #
# Async Job Task Wrappers                                              #
# ------------------------------------------------------------------ #

async def ingest_repository_job(ctx: Dict[Any, Any], project_id: str) -> None:
    """Wrapper calling the Step 3 ingestion pipeline."""
    logger.info("Processing repository ingestion job for project: %s", project_id)
    try:
        await ingest_repository(project_id)
        logger.info("Successfully completed ingestion for project: %s", project_id)
    except Exception as e:
        logger.error(
            "Failed to complete ingestion job for project %s: %s",
            project_id,
            e,
            exc_info=True
        )
        raise


async def generate_plan_job(ctx: Dict[Any, Any], ticket_id: str, agent_run_id: str) -> None:
    """Executes the full planning agent pipeline (Steps 7-13, and 15)."""
    logger.info("Processing plan generation job for ticket: %s (agent_run_id: %s)", ticket_id, agent_run_id)

    # Gather resources from startup context
    client = ctx["llm_client"]
    model_name = ctx["llm_model_name"]
    count_tokens_fn = ctx["count_tokens_fn"]
    redis_client = ctx["redis"]

    job_try = ctx.get("job_try", 1)
    defer_seconds = config.job_backoff_seconds(job_try)

    channel_id = None  

    try:
        async with get_connection() as conn:
            # Check current status of the agent run
            res = await conn.execute(
                select(agent_runs).where(agent_runs.c.id == agent_run_id)
            )
            run_row = res.mappings().first()
            if not run_row:
                logger.error("AgentRun %s not found in database.", agent_run_id)
                return

            # Mark AgentRun as running and increment its local DB attempt counter
            await conn.execute(
                update(agent_runs)
                .where(agent_runs.c.id == agent_run_id)
                .values(
                    status="running",
                    attempt_count=job_try,
                    updated_at=datetime.now(timezone.utc)
                )
            )

            # Retrieve ticket metadata
            res = await conn.execute(
                select(tickets).where(tickets.c.id == ticket_id)
            )
            ticket_row = res.mappings().first()
            if not ticket_row:
                raise ValueError(f"Ticket {ticket_id} not found in database.")

            # Resolve project ID and channel mapping
            res = await conn.execute(
                select(channels).where(channels.c.id == ticket_row["channel_id"])
            )
            channel_row = res.mappings().first()
            if not channel_row:
                raise ValueError(f"Channel {ticket_row['channel_id']} not found in database.")
            project_id = channel_row["project_id"]
            channel_id = channel_row["id"]

            # Load non-deleted chronological messages to form conversation thread
            res = await conn.execute(
                select(messages.c.content)
                .where(messages.c.ticket_id == ticket_id, messages.c.deleted_at.is_(None))
                .order_by(messages.c.created_at.asc())
            )
            thread_messages = [r[0] for r in res.all()]

            # Load specialty and technology configurations
            res = await conn.execute(
                select(skill_assignments).where(skill_assignments.c.channel_id == channel_id)
            )
            assignment_row = res.mappings().first()

            specialty_skill = ""
            if assignment_row and assignment_row["specialty_file_id"]:
                res = await conn.execute(
                    select(skill_files.c.file_content).where(skill_files.c.id == assignment_row["specialty_file_id"])
                )
                f_row = res.first()
                if f_row:
                    specialty_skill = f_row[0]

            technology_skill = ""
            if assignment_row and assignment_row["technology_file_id"]:
                res = await conn.execute(
                    select(skill_files.c.file_content).where(skill_files.c.id == assignment_row["technology_file_id"])
                )
                f_row = res.first()
                if f_row:
                    technology_skill = f_row[0]

    except Exception as e:
        logger.error("Initialization failure during generate_plan_job setup: %s", e, exc_info=True)
        if job_try < config.MAX_JOB_ATTEMPTS:
            logger.info("Scheduling backoff retry #%s in %s seconds...", job_try + 1, defer_seconds)
            raise Retry(defer=defer_seconds)
        else:
            await _handle_terminal_failure(redis_client, ticket_id, channel_id, agent_run_id, f"Database or setup initialization failed: {e}")
            return

    # Coordinate retrieval and LLM call pipeline
    step_counter = [1]
    try:
        # Guardrail 2 (build plan): pre-flight scope/actionability gate,
        # AgentRunStep #0 — runs before the Qdrant RAG query and before the
        # draft/critique pair. Raises ScopeGateRejected (caught below) if the
        # ticket text isn't actionable engineering work.
        await run_scope_gate(
            client=client,
            model_name=model_name,
            ticket_title=ticket_row["title"],
            ticket_description=ticket_row["description"] or "",
            thread_messages=thread_messages,
            agent_run_id=agent_run_id,
            job_try=job_try,
        )

        retrieval_query = (
            f"Title: {ticket_row['title']}\n"
            f"Description: {ticket_row['description'] or ''}\n\n"
            "Discussion:\n" + "\n".join(thread_messages)
        )
        query_vector = embed_query(retrieval_query)
        retrieved_chunks = await retrieve_chunks(project_id, query_vector, limit=config.RETRIEVAL_TOP_K)

        # Draft -> critique. Each internal step commits itself as it goes
        # (see planner.py) — no shared transaction with what follows.
        final_plan = await generate_development_plan(
            client=client,
            model_name=model_name,
            count_tokens_fn=count_tokens_fn,
            specialty_skill=specialty_skill,
            technology_skill=technology_skill,
            ticket_title=ticket_row["title"],
            ticket_description=ticket_row["description"] or "",
            retrieved_chunks=retrieved_chunks,
            thread_messages=thread_messages,
            agent_run_id=agent_run_id,
            step_counter=step_counter,
            job_try=job_try,
        )

        # Step 11: File-grounding validation — also self-committing now.
        validation_step_id = await create_agent_run_step(
            agent_run_id,
            step_number=step_counter[0],
            description=f"File-grounding validation pass (attempt {job_try})",
        )
        step_counter[0] += 1

        try:
            await validate_development_plan_grounding(project_id, final_plan)
            await complete_agent_run_step(
                validation_step_id,
                model_prompt="Validate modify/delete targets exist, create targets do not exist",
                model_response="Grounding validation completed cleanly.",
            )
        except FileGroundingValidationError as exc:
            await fail_agent_run_step(
                validation_step_id,
                error=str(exc),
                model_prompt="Validate modify/delete targets exist, create targets do not exist",
            )
            raise exc

        # Terminal state change: this is the one thing that DOES need to be
        # atomic as a group. Commit it, THEN publish.
        system_msg_id = str(uuid.uuid4())
        msg_content = f"AI Planning Agent completed a Development Plan.\n\nSummary: {final_plan.summary}"
        created_at = datetime.now(timezone.utc)

        async with get_connection() as conn:
            await conn.execute(
                update(agent_runs)
                .where(agent_runs.c.id == agent_run_id)
                .values(status="awaiting_review", plan_json=final_plan.model_dump(), updated_at=created_at)
            )
            await conn.execute(
                update(tickets).where(tickets.c.id == ticket_id).values(status="plan_review")
            )
            await conn.execute(
                messages.insert().values(
                    id=system_msg_id,
                    ticket_id=ticket_id,
                    author_id=None,
                    content=msg_content,
                    type="system",
                    metadata_json={"event": "plan_generated", "agent_run_id": agent_run_id},
                    created_at=created_at,
                )
            )
        # conn block has exited -> committed. Publish now, not before.
        if redis_client:
            await redis_client.publish(
                f"channel:{channel_id}:events",
                _json_dumps({
                    "event": "ticket.status_change",
                    "ticket_id": ticket_id,
                    "channel_id": channel_id,
                    "old_status": "consensus_reached",
                    "new_status": "plan_review",
                }),
            )
            message_payload = {
                "id": system_msg_id,
                "ticket_id": ticket_id,
                "author_id": None,
                "author": None,
                "content": msg_content,
                "type": "system",
                "metadata_json": {"event": "plan_generated", "agent_run_id": agent_run_id},
                "deleted_at": None,
                "edited_at": None,
                "created_at": created_at,
                "updated_at": created_at,
            }
            await redis_client.publish(
                f"channel:{channel_id}:events",
                _json_dumps({
                    "event": "message.new",
                    "ticket_id": ticket_id,
                    "channel_id": channel_id,
                    "message": message_payload,
                }),
            )

        logger.info("Successfully completed plan generation for ticket %s", ticket_id)

    except ScopeGateRejected as exc:
        logger.info(
            "Pre-flight scope gate rejected ticket %s as out of scope: %s",
            ticket_id, exc.reason,
        )
        system_msg_id = str(uuid.uuid4())
        msg_content = f"AI Planning Agent rejected this ticket as out of scope: {exc.reason}"
        created_at = datetime.now(timezone.utc)

        async with get_connection() as conn:
            await conn.execute(
                update(tickets).where(tickets.c.id == ticket_id).values(status="consensus_reached")
            )
            await conn.execute(
                update(agent_runs)
                .where(agent_runs.c.id == agent_run_id)
                .values(status="rejected_out_of_scope", updated_at=created_at)
            )
            await conn.execute(
                messages.insert().values(
                    id=system_msg_id,
                    ticket_id=ticket_id,
                    author_id=None,
                    content=msg_content,
                    type="system",
                    metadata_json={
                        "event": "plan_rejected_out_of_scope",
                        "agent_run_id": agent_run_id,
                        "reason": exc.reason,
                    },
                    created_at=created_at,
                )
            )
        # commit done -> now publish
        if redis_client:
            await redis_client.publish(
                f"channel:{channel_id}:events",
                _json_dumps({
                    "event": "ticket.status_change",
                    "ticket_id": ticket_id,
                    "channel_id": channel_id,
                    "old_status": "consensus_reached",
                    "new_status": "consensus_reached",
                }),
            )
            message_payload = {
                "id": system_msg_id,
                "ticket_id": ticket_id,
                "author_id": None,
                "author": None,
                "content": msg_content,
                "type": "system",
                "metadata_json": {
                    "event": "plan_rejected_out_of_scope",
                    "agent_run_id": agent_run_id,
                    "reason": exc.reason,
                },
                "deleted_at": None,
                "edited_at": None,
                "created_at": created_at,
                "updated_at": created_at,
            }
            await redis_client.publish(
                f"channel:{channel_id}:events",
                _json_dumps({
                    "event": "message.new",
                    "ticket_id": ticket_id,
                    "channel_id": channel_id,
                    "message": message_payload,
                }),
            )

    except FileGroundingValidationError as exc:
        logger.error("Logical validation fail: %s. Reverting ticket and run states.", exc)
        system_msg_id = str(uuid.uuid4())
        msg_content = f"AI Planning validation failed: {str(exc)}"
        created_at = datetime.now(timezone.utc)

        async with get_connection() as conn:
            await conn.execute(
                update(tickets).where(tickets.c.id == ticket_id).values(status="consensus_reached")
            )
            await conn.execute(
                update(agent_runs)
                .where(agent_runs.c.id == agent_run_id)
                .values(status="failed", updated_at=created_at)
            )
            await conn.execute(
                messages.insert().values(
                    id=system_msg_id,
                    ticket_id=ticket_id,
                    author_id=None,
                    content=msg_content,
                    type="system",
                    metadata_json={"event": "plan_failed", "agent_run_id": agent_run_id, "error": str(exc)},
                    created_at=created_at,
                )
            )
        # commit done -> now publish
        if redis_client:
            await redis_client.publish(
                f"channel:{channel_id}:events",
                _json_dumps({
                    "event": "ticket.status_change",
                    "ticket_id": ticket_id,
                    "channel_id": channel_id,
                    "old_status": "consensus_reached",
                    "new_status": "consensus_reached",
                }),
            )
            message_payload = {
                "id": system_msg_id,
                "ticket_id": ticket_id,
                "author_id": None,
                "author": None,
                "content": msg_content,
                "type": "system",
                "metadata_json": {"event": "plan_failed", "agent_run_id": agent_run_id, "error": str(exc)},
                "deleted_at": None,
                "edited_at": None,
                "created_at": created_at,
                "updated_at": created_at,
            }
            await redis_client.publish(
                f"channel:{channel_id}:events",
                _json_dumps({
                    "event": "message.new",
                    "ticket_id": ticket_id,
                    "channel_id": channel_id,
                    "message": message_payload,
                }),
            )

    except Exception as exc:
        logger.error("Technical failure encountered: %s", exc, exc_info=True)
        if job_try < config.MAX_JOB_ATTEMPTS:
            logger.info("Scheduling backoff retry #%s in %s seconds...", job_try + 1, defer_seconds)
            raise Retry(defer=defer_seconds)
        else:
            await _handle_terminal_failure(redis_client, ticket_id, channel_id, agent_run_id, f"Technical failures exhausted: {exc}")

async def _handle_terminal_failure(redis_client: Any, ticket_id: str, channel_id: str, agent_run_id: str, error_msg: str) -> None:
    """Helper to revert database states and publish WebSocket notifications when retries are permanently exhausted."""
    logger.error("Terminal failure ceiling hit. Finalizing fail state for run %s", agent_run_id)
    
    system_msg_id = str(uuid.uuid4())
    msg_content = f"Planning generation failed permanently: {error_msg}"
    created_at = datetime.now(timezone.utc)
    
    try:
        async with get_connection() as conn:
            # Revert Ticket back to consensus_reached
            await conn.execute(
                update(tickets)
                .where(tickets.c.id == ticket_id)
                .values(status="consensus_reached")
            )
            # Update AgentRun state
            await conn.execute(
                update(agent_runs)
                .where(agent_runs.c.id == agent_run_id)
                .values(
                    status="failed",
                    updated_at=created_at
                )
            )
            # Post failure notification system message card
            await conn.execute(
                messages.insert().values(
                    id=system_msg_id,
                    ticket_id=ticket_id,
                    author_id=None,
                    content=msg_content,
                    type="system",
                    metadata_json={
                        "event": "plan_failed",
                        "agent_run_id": agent_run_id,
                        "error": error_msg,
                    },
                    created_at=created_at
                )
            )
    except Exception as e:
        logger.error("Database connections or updates failed during terminal failure handling: %s", e)

    # Real-Time Event Publishing (Executed even if DB operations fail)
    if redis_client:
        await redis_client.publish(
            f"channel:{channel_id}:events",
            _json_dumps({
                "event": "ticket.status_change",
                "ticket_id": ticket_id,
                "channel_id": channel_id,
                "old_status": "consensus_reached",
                "new_status": "consensus_reached",
            })
        )
        message_payload = {
            "id": system_msg_id,
            "ticket_id": ticket_id,
            "author_id": None,
            "author": None,
            "content": msg_content,
            "type": "system",
            "metadata_json": {
                "event": "plan_failed",
                "agent_run_id": agent_run_id,
                "error": error_msg,
            },
            "deleted_at": None,
            "edited_at": None,
            "created_at": created_at,
            "updated_at": created_at,
        }
        await redis_client.publish(
            f"channel:{channel_id}:events",
            _json_dumps({
                "event": "message.new",
                "ticket_id": ticket_id,
                "channel_id": channel_id,
                "message": message_payload,
            })
        )


# ------------------------------------------------------------------ #
# Arq Worker Settings Class                                            #
# ------------------------------------------------------------------ #

class WorkerSettings:
    """Settings class parsed directly by the arq command-line runner."""
    redis_settings = RedisSettings.from_dsn(config.REDIS_URL)

    functions = [
        ingest_repository_job,
        func(generate_plan_job, name="generate_plan")
    ]

    on_startup = startup
    on_shutdown = shutdown

    job_timeout = config.JOB_TIMEOUT_SECONDS  # Give plan generation tasks up to 10 minutes to run
    max_jobs = config.WORKER_MAX_CONCURRENT_JOBS