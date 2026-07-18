"""arq worker entrypoint for code-service

Coordinates step execution, monitors run failures, manages job-level retry backoffs,
and handles terminal hard-technical-failure escalations to the blocked ticket status.
"""

import logging

from arq import Retry
from arq.connections import RedisSettings

from app.config import MAX_JOB_ATTEMPTS, REDIS_URL, job_backoff_seconds
from app.db import close_engine, get_engine

logger = logging.getLogger(__name__)


async def execute_plan_job(ctx: dict, agent_run_id: str) -> None:
    """Drive one AgentRun through the execution pipeline with arq retries and escalations."""
    job_try = ctx["job_try"]
    logger.info(
        "execute_plan_job starting: agent_run_id=%s job_try=%d",
        agent_run_id,
        job_try,
    )
    
    try:
        from app.runner import run_agent_plan
        await run_agent_plan(agent_run_id, job_try)
        logger.info("execute_plan_job completed successfully for agent_run_id=%s", agent_run_id)
        
    except Exception as exc:
        # Check if this exception represents an already-escalated logical error
        from app.git.operations import PushRejectedError
        from app.locks import LockError
        from app.loops_detector import StuckLoopTriggered
        from app.runner import SoftAIFailureError
        
        escalated_types = (LockError, StuckLoopTriggered, PushRejectedError, SoftAIFailureError)
        if isinstance(exc, escalated_types):
            logger.info("Logical budget failure captured; already escalated to blocked status.")
            raise
            
        # Hard Technical failure retry evaluation
        if job_try < MAX_JOB_ATTEMPTS:
            backoff = job_backoff_seconds(job_try)
            logger.warning(
                "execute_plan_job encountered a system failure on attempt %d. "
                "Retrying in %d seconds. Error: %s",
                job_try,
                backoff,
                exc,
            )
            # Raise arq's Retry exception to defer and schedule the next attempt
            raise Retry(defer=backoff) from exc
        else:
            # Permanent Hard Technical Failure Escalation
            logger.error(
                "execute_plan_job exhausted all %d attempts due to Hard Technical failure. Escalating to blocked.",
                MAX_JOB_ATTEMPTS,
            )
            
            # Fetch ticket context to mark as blocked and insert the blocker card
            from app.git.operations import branch_name
            from app.runner import (
                fetch_execution_context,
                insert_blocker_card,
                update_run_status,
                update_ticket_status,
            )
            
            context = await fetch_execution_context(agent_run_id)
            if context:
                ticket_id = context["ticket_id"]
                channel_id = context["channel_id"]
                repo_name = context["repo_full_name"]
                ticket_title = context["ticket_title"]
                branch = branch_name(ticket_id, ticket_title)
                
                await update_ticket_status(ticket_id, "blocked")
                await update_run_status(agent_run_id, "failed")
                
                await insert_blocker_card(
                    ticket_id=ticket_id,
                    channel_id=channel_id,
                    step_desc="System-level execution run",
                    category="HardTechnicalFailure",
                    evidence=f"Exhausted {MAX_JOB_ATTEMPTS} attempts on job runner.\nLast error:\n{exc}",
                    repo_full_name=repo_name,
                    branch=branch
                )
            raise


async def on_startup(ctx: dict) -> None:
    """Create the DB engine pool once, at worker boot, not on first use."""
    get_engine()
    logger.info("code-service arq worker started")


async def on_shutdown(ctx: dict) -> None:
    await close_engine()
    logger.info("code-service arq worker shut down")


class WorkerSettings:
    functions = [execute_plan_job]
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    on_startup = on_startup
    on_shutdown = on_shutdown
    
    # Isolate the queue to prevent code-service from racing with planning-service
    queue_name = "code_queue"

    max_tries = MAX_JOB_ATTEMPTS
    job_timeout = 3600
    keep_result = 0