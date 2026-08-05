"""Self-committing AgentRunStep logging (Step 6).

Reuses the transaction-isolation pattern locked for the Planning Agent: every
step record commits independently, never bundled inside the main run
transaction, so a step's audit trail survives a later failure of the run.

Adds the code-agent fields: check_tier, requires_human_review, job_try.
"""

import uuid
from datetime import datetime, timezone

from app.db import agent_run_steps, get_connection


async def create_agent_run_step(
    agent_run_id: str,
    step_number: int,
    description: str,
    job_try: int | None = None,
    requires_human_review: bool = False,
) -> str:
    """Create a step in 'running' status, committing immediately."""
    step_id = str(uuid.uuid4())
    async with get_connection() as conn:
        await conn.execute(
            agent_run_steps.insert().values(
                id=step_id,
                agent_run_id=agent_run_id,
                step_number=step_number,
                description=description[:200],
                status="running",
                job_try=job_try,
                requires_human_review=requires_human_review,
                created_at=datetime.now(timezone.utc),
            )
        )
    return step_id


async def complete_agent_run_step(
    step_id: str,
    check_tier: str | None = None,
    model_prompt: str | None = None,
    model_response: str | None = None,
    requires_human_review: bool | None = None,
) -> None:
    """Mark a step completed, tagging which validation tier actually ran."""
    values: dict = {"status": "completed"}
    if check_tier is not None:
        values["check_tier"] = check_tier
    if model_prompt is not None:
        values["model_prompt"] = model_prompt
    if model_response is not None:
        values["model_response"] = model_response
    if requires_human_review is not None:
        values["requires_human_review"] = requires_human_review

    async with get_connection() as conn:
        await conn.execute(
            agent_run_steps.update()
            .where(agent_run_steps.c.id == step_id)
            .values(**values)
        )


async def fail_agent_run_step(
    step_id: str,
    error: str,
    check_tier: str | None = None,
    model_prompt: str | None = None,
    model_response: str | None = None,
) -> None:
    """Mark a step failed with structured evidence."""
    values: dict = {"status": "failed", "error": error}
    if check_tier is not None:
        values["check_tier"] = check_tier
    if model_prompt is not None:
        values["model_prompt"] = model_prompt
    if model_response is not None:
        values["model_response"] = model_response

    async with get_connection() as conn:
        await conn.execute(
            agent_run_steps.update()
            .where(agent_run_steps.c.id == step_id)
            .values(**values)
        )


async def flag_requires_human_review(step_id: str) -> None:
    """Set requires_human_review=True on an existing step (migration or protected CI/CD path touch)."""
    async with get_connection() as conn:
        await conn.execute(
            agent_run_steps.update()
            .where(agent_run_steps.c.id == step_id)
            .values(requires_human_review=True)
        )