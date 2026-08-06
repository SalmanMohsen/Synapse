"""Planning Agent pipeline: composes the pipeline stages in a fixed order.

Pipes-and-Filters composition of the Planning Agent's runtime path:

    scope gate  ->  retrieval  ->  draft/critique  ->  grounding validation

This module owns *only* the stage sequence. It knows nothing about arq, job
retries, or Redis pub/sub -- that's app.worker's job. Each stage is a plain
async function imported from its own module (app.agent.planner,
app.agent.validation, app.ingestion.embeddings / app.ingestion.qdrant_store);
this file's only responsibility is to call them in the right order and let
their exceptions (ScopeGateRejected, FileGroundingValidationError, or
anything else) propagate unchanged to the caller.
"""

import logging
from typing import List

from openai import AsyncOpenAI

from app import config
from app.agent.planner import generate_development_plan, run_scope_gate
from app.agent.validation import FileGroundingValidationError, validate_development_plan_grounding
from app.db import complete_agent_run_step, create_agent_run_step, fail_agent_run_step
from app.ingestion.embeddings import embed_query
from app.ingestion.qdrant_store import retrieve_chunks
from app.prompt.assembly import CountTokensFn
from app.schemas.plan import DevelopmentPlan

logger = logging.getLogger(__name__)


async def run_planning_pipeline(
    *,
    client: AsyncOpenAI,
    model_name: str,
    count_tokens_fn: CountTokensFn,
    ticket_title: str,
    ticket_description: str,
    thread_messages: List[str],
    specialty_skill: str,
    technology_skill: str,
    project_id: str,
    agent_run_id: str,
    job_try: int,
    step_counter: List[int],
) -> DevelopmentPlan:
    """Runs the four pipeline stages in order and returns the final plan.

    Raises ScopeGateRejected (app.agent.planner) if the pre-flight gate
    rejects the ticket, or FileGroundingValidationError (app.agent.validation)
    if the drafted plan doesn't ground cleanly. Both propagate to the caller
    untouched -- app.worker.generate_plan_job decides how to react to each
    (status transitions, blocker messages, retries); this module only runs
    the stages.
    """
    # Stage 1: pre-flight scope/actionability gate (AgentRunStep #0). Runs
    # before the Qdrant RAG query and before the draft/critique pair.
    await run_scope_gate(
        client=client,
        model_name=model_name,
        ticket_title=ticket_title,
        ticket_description=ticket_description,
        thread_messages=thread_messages,
        agent_run_id=agent_run_id,
        job_try=job_try,
    )

    # Stage 2: retrieval -- single shared Qdrant collection, project_id
    # mandatory filter, top-k from config (locked decision).
    retrieval_query = (
        f"Title: {ticket_title}\n"
        f"Description: {ticket_description or ''}\n\n"
        "Discussion:\n" + "\n".join(thread_messages)
    )
    query_vector = embed_query(retrieval_query)
    retrieved_chunks = await retrieve_chunks(project_id, query_vector, limit=config.RETRIEVAL_TOP_K)

    # Stage 3: draft -> self-critique (each internal step self-commits its
    # own AgentRunStep -- see app.agent.planner).
    final_plan = await generate_development_plan(
        client=client,
        model_name=model_name,
        count_tokens_fn=count_tokens_fn,
        specialty_skill=specialty_skill,
        technology_skill=technology_skill,
        ticket_title=ticket_title,
        ticket_description=ticket_description,
        retrieved_chunks=retrieved_chunks,
        thread_messages=thread_messages,
        agent_run_id=agent_run_id,
        step_counter=step_counter,
        job_try=job_try,
    )

    # Stage 4: file-grounding validation -- hard-fail and escalate on
    # failure (locked decision; no third LLM call). Self-commits its own
    # AgentRunStep, same convention as every other stage.
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
        raise

    return final_plan