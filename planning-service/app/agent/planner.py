import json  
import logging
from typing import List, Tuple

from openai import AsyncOpenAI

from app.prompt.assembly import CountTokensFn, assemble_prompt, batch_messages_for_summary
from app.prompt.templates import (
    PLANNER_SYSTEM_PROMPT,
    CRITIQUE_SYSTEM_PROMPT,
    SUMMARIZER_REFINE_SYSTEM_PROMPT,
    SUMMARIZER_SYSTEM_PROMPT
)
from app.llm.client import get_completion
from app.schemas.plan import DevelopmentPlan
from app.db import create_agent_run_step, complete_agent_run_step, fail_agent_run_step

logger = logging.getLogger(__name__)


async def _run_sequential_summarization(
    messages: List[str],
    count_tokens_fn: CountTokensFn,
    client: AsyncOpenAI,
    model_name: str,
) -> str:
    """Execute a chronological, refine-style batch loop to compress oversized discussion threads."""
    batches = batch_messages_for_summary(messages, count_tokens_fn)
    logger.info("Thread size exceeded limit. Initiating refine-style loop across %s batches.", len(batches))

    # Process first batch
    first_batch_text = "\n".join(batches[0])
    running_summary = await get_completion(
        client=client,
        model_name=model_name,
        system_prompt=SUMMARIZER_SYSTEM_PROMPT,
        user_prompt=f"Please summarize the following team discussion:\n\n{first_batch_text}"
    )

    # Process subsequent batches sequentially (refine-style)
    for i, batch in enumerate(batches[1:], start=2):
        batch_text = "\n".join(batch)
        user_prompt = (
            f"Running Summary of previous discussion:\n{running_summary}\n\n"
            f"New Chronological Messages:\n{batch_text}\n\n"
            "Please refine and update the running summary based on these new messages."
        )
        running_summary = await get_completion(
            client=client,
            model_name=model_name,
            system_prompt=SUMMARIZER_REFINE_SYSTEM_PROMPT,
            user_prompt=user_prompt
        )
        logger.info("Completed refine summary step %s of %s", i, len(batches))

    return running_summary


async def generate_development_plan(
    client: AsyncOpenAI,
    model_name: str,
    count_tokens_fn: CountTokensFn,
    specialty_skill: str,
    technology_skill: str,
    ticket_title: str,
    ticket_description: str,
    retrieved_chunks: List[Tuple[str, str]],
    thread_messages: List[str],
    agent_run_id: str,
    step_counter: List[int],
    job_try: int = 1,
) -> DevelopmentPlan:
    """Coordinate prompt assembly, conditional summarization, and the two-call sequence."""

    assembly = assemble_prompt(
        specialty_skill=specialty_skill,
        technology_skill=technology_skill,
        ticket_title=ticket_title,
        ticket_description=ticket_description,
        retrieved_chunks=retrieved_chunks,
        thread_messages=thread_messages,
        count_tokens_fn=count_tokens_fn,
    )

    thread_summary: str | None = None

    if assembly.needs_summarization:
        step_id = await create_agent_run_step(
            agent_run_id,
            step_number=step_counter[0],
            description=f"Chronological thread summarization loop (attempt {job_try})",
        )
        step_counter[0] += 1
        try:
            thread_summary = await _run_sequential_summarization(
                assembly.messages_to_summarize, count_tokens_fn, client, model_name
            )
            await complete_agent_run_step(
                step_id,
                model_prompt=f"Summarize chronological message logs. Total overflow messages: {len(assembly.messages_to_summarize)}",
                model_response=thread_summary,
            )
        except Exception as e:
            await fail_agent_run_step(step_id, error=str(e))
            raise

        assembly = assemble_prompt(
            specialty_skill=specialty_skill,
            technology_skill=technology_skill,
            ticket_title=ticket_title,
            ticket_description=ticket_description,
            retrieved_chunks=retrieved_chunks,
            thread_messages=assembly.messages_verbatim,
            count_tokens_fn=count_tokens_fn,
            thread_summary=thread_summary,
        )

    logger.info("Initiating Draft Plan generation call (Step 9)...")
    draft_step_id = await create_agent_run_step(
        agent_run_id,
        step_number=step_counter[0],
        description=f"Draft Plan generation (attempt {job_try})",
    )
    step_counter[0] += 1

    try:
        draft_plan: DevelopmentPlan = await get_completion(
            client=client,
            model_name=model_name,
            system_prompt=PLANNER_SYSTEM_PROMPT,
            user_prompt=assembly.prompt,
            response_model=DevelopmentPlan,
            temperature=0.2,
        )
        draft_plan_json = json.dumps(draft_plan.model_dump(), indent=2)
        await complete_agent_run_step(draft_step_id, model_prompt=assembly.prompt, model_response=draft_plan_json)
    except Exception as e:
        await fail_agent_run_step(draft_step_id, error=str(e), model_prompt=assembly.prompt)
        raise

    critique_user_prompt = (
        f"Original Context and Ticket instructions:\n\n{assembly.prompt}\n\n"
        f"Proposed Draft Development Plan to critique:\n\n{draft_plan_json}"
    )

    logger.info("Initiating Critique and Revision call (Step 10)...")
    critique_step_id = await create_agent_run_step(
        agent_run_id,
        step_number=step_counter[0],
        description=f"Critique and revision of draft plan (attempt {job_try})",
    )
    step_counter[0] += 1

    try:
        final_plan: DevelopmentPlan = await get_completion(
            client=client,
            model_name=model_name,
            system_prompt=CRITIQUE_SYSTEM_PROMPT,
            user_prompt=critique_user_prompt,
            response_model=DevelopmentPlan,
            temperature=0.2,
        )
        final_plan_json = json.dumps(final_plan.model_dump(), indent=2)
        await complete_agent_run_step(critique_step_id, model_prompt=critique_user_prompt, model_response=final_plan_json)
    except Exception as e:
        await fail_agent_run_step(critique_step_id, error=str(e), model_prompt=critique_user_prompt)
        raise

    return final_plan