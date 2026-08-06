"""Orchestrator for the execution of Code Agent runs (Build Plan Steps 7 to 18 with async bug patches).

Coordinates cloning, sandbox setup, locking, conflict prevention, OpenHands
conversation flow, step validation, soft-failure correction loops, stuck-loop detection,
dangerous-action boundaries (migration/CI-CD path observers), checkpoint-resumes, step commit & push,
codebase manifest updates, PR creation, progress events, and blocker escalations.
Tears down the sandbox.
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

from app.config import CORRECTION_ATTEMPT_BUDGET, REPO_WORK_ROOT, REPO_WORK_ROOT_HOST
from app.db import (
    agent_runs,
    get_connection,
    messages,
    tickets,
)
from app.git_providers import GitIntegrationRef, get_git_provider
from app.git.operations import (
    PushRejectedError,
    branch_name,
    changed_files,
    clone_and_checkout,
    commit_all,
    has_changes,
    push,
)
from app.guardrails import (
    DynamicLockSubscriber,
    ProtectedPathSubscriber,
    RunContext,
    StuckLoopSubscriber,
)
from app.locks import (
    LockConflictError,
    LockError,
    SemanticConflictError,
    get_redis_client,
    register_step_and_acquire_locks,
    release_locks,
)
from app.loops_detector import StuckLoopDetector, StuckLoopTriggered
from app.manifest import update_codebase_manifest_incremental
from app.openhands.conversation import open_conversation
from app.openhands.events import AgentEvent, EventBus
from app.sandbox.container import create_sandbox, teardown_sandbox
from app.steps import (
    complete_agent_run_step,
    create_agent_run_step,
    fail_agent_run_step,
)
from app.validation import validate_step_changes

logger = logging.getLogger(__name__)


class SoftAIFailureError(RuntimeError):
    """Raised when the soft-failure correction budget is exhausted."""


def wrap_untrusted(content: str) -> str:
    """Delimits content that did not originate from code-service's own
    generation — plan/ticket-derived task text, or file content read back
    from the repo — so the agent treats it as reference material, never as
    instructions (Guardrail 1, build plan).

    The meaning of this boundary is established once, in the agent's system
    prompt (see UNTRUSTED_CONTEXT_SYSTEM_SUFFIX in openhands/conversation.py);
    this function only wraps the untrusted span at each call site.
    """
    return f"<untrusted_context>\n{content}\n</untrusted_context>"


async def cleanup_unfinished_steps(agent_run_id: str) -> None:
    """Deletes any step records that were left in 'running' status due to a crash."""
    from app.db import agent_run_steps
    async with get_connection() as conn:
        await conn.execute(
            agent_run_steps.delete()
            .where(
                agent_run_steps.c.agent_run_id == agent_run_id,
                agent_run_steps.c.status == "running"
            )
        )


async def fetch_completed_step_numbers(agent_run_id: str) -> Set[int]:
    """Queries Postgres for step numbers that successfully completed in previous run tries."""
    from app.db import agent_run_steps
    from sqlalchemy import select

    async with get_connection() as conn:
        stmt = (
            select(agent_run_steps.c.step_number)
            .where(
                agent_run_steps.c.agent_run_id == agent_run_id,
                agent_run_steps.c.status == "completed",
                agent_run_steps.c.phase == "execution",
            )
        )
        result = await conn.execute(stmt)
        return {row[0] for row in result}


async def fetch_completed_steps_details(agent_run_id: str) -> List[Dict[str, Any]]:
    """Queries Postgres for step details (description, status, check_tier) of completed run steps."""
    from app.db import agent_run_steps
    from sqlalchemy import select

    async with get_connection() as conn:
        stmt = (
            select(
                agent_run_steps.c.step_number,
                agent_run_steps.c.description,
                agent_run_steps.c.check_tier
            )
            .where(
                agent_run_steps.c.agent_run_id == agent_run_id,
                agent_run_steps.c.status == "completed",
                agent_run_steps.c.phase == "execution",
            )
            .order_by(agent_run_steps.c.step_number.asc())
        )
        result = await conn.execute(stmt)
        return [dict(row._mapping) for row in result]


def assemble_pr_body(
    ticket_title: str,
    ticket_description: str,
    completed_steps: List[Dict[str, Any]]
) -> str:
    """Assembles a structured PR body from completed run step records."""
    body = f"# {ticket_title}\n\n"
    body += "## Ticket Description\n"
    body += f"{ticket_description or 'No description provided.'}\n\n"
    body += "## Implementation Steps Completed\n"
    body += "The Synapse Code Agent has completed the following steps and passed validation checks:\n\n"
    
    for step in completed_steps:
        step_num = step.get("step_number", "?")
        desc = step.get("description", "")
        tier = step.get("check_tier", "unknown")
        
        tier_display = {
            "repo_test_suite": "✅ Repo Test Suite (`make lint/test` or package.json)",
            "generic_validator": "✅ Generic Fallback Validator",
            "sanity_only": "⚠️ Bare Sanity Check Only"
        }.get(tier, f"✅ Check Tier: {tier}")
        
        body += f"- **Step {step_num}**: {desc}\n"
        body += f"  - *Validation*: {tier_display}\n"
        
    body += "\n---\n"
    body += "*Generated automatically by the Synapse Code Agent.*"
    return body


async def fetch_execution_context(agent_run_id: str) -> Dict[str, Any] | None:
    """Fetch all context needed for the plan execution using a high-performance join."""
    from sqlalchemy import select
    from app.db import channels, git_integrations

    async with get_connection() as conn:
        stmt = (
            select(
                agent_runs.c.id.label("run_id"),
                agent_runs.c.plan_json,
                agent_runs.c.status.label("run_status"),
                tickets.c.id.label("ticket_id"),
                tickets.c.title.label("ticket_title"),
                tickets.c.description.label("ticket_description"),
                channels.c.id.label("channel_id"),
                channels.c.project_id,
                git_integrations.c.provider, 
                git_integrations.c.github_app_installation_id,
                git_integrations.c.repo_full_name,
                git_integrations.c.default_branch,
            )
            .select_from(
                agent_runs
                .join(tickets, agent_runs.c.ticket_id == tickets.c.id)
                .join(channels, tickets.c.channel_id == channels.c.id)
                .join(git_integrations, channels.c.project_id == git_integrations.c.project_id)
            )
            .where(agent_runs.c.id == agent_run_id)
        )
        result = await conn.execute(stmt)
        row = result.first()
        if not row:
            return None
        return dict(row._mapping)


async def update_run_status(agent_run_id: str, status: str) -> None:
    """Safely transition the status of the agent run in Postgres."""
    async with get_connection() as conn:
        await conn.execute(
            agent_runs.update()
            .where(agent_runs.c.id == agent_run_id)
            .values(status=status)
        )


async def update_ticket_status(ticket_id: str, status: str) -> None:
    """Safely transition the ticket status."""
    async with get_connection() as conn:
        await conn.execute(
            tickets.update()
            .where(tickets.c.id == ticket_id)
            .values(status=status)
        )


async def update_ticket_pr_details(ticket_id: str, pr_number: int) -> None:
    """Updates the ticket record with the newly created GitHub PR number."""
    async with get_connection() as conn:
        await conn.execute(
            tickets.update()
            .where(tickets.c.id == ticket_id)
            .values(github_pr_number=pr_number)
        )


async def publish_thread_message(
    ticket_id: str,
    channel_id: str,
    content: str,
    msg_type: str,
    metadata_json: Dict[str, Any] | None = None
) -> str:
    """Inserts a thread message in Postgres and live-streams it to WebSockets over Redis."""
    message_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    
    async with get_connection() as conn:
        await conn.execute(
            messages.insert().values(
                id=message_id,
                ticket_id=ticket_id,
                author_id=None,
                content=content,
                type=msg_type,
                metadata_json=metadata_json,
                created_at=now,
            )
        )
        
    redis = get_redis_client()
    try:
        payload = {
            "event": "message.new",
            "ticket_id": ticket_id,
            "channel_id": channel_id,
            "message": {
                "id": message_id,
                "ticket_id": ticket_id,
                "content": content,
                "type": msg_type,
                "metadata_json": metadata_json or {},
                "created_at": now.isoformat(),
            }
        }
        channel_key = f"project_channel:{channel_id}"
        await redis.publish(channel_key, json.dumps(payload))
    except Exception as e:
        logger.warning("WebSocket real-time broadcast failed over Redis: %s", e)
        
    return message_id


async def insert_blocker_card(
    ticket_id: str,
    channel_id: str,
    step_desc: str,
    category: str,
    evidence: str,
    repo_full_name: str,
    branch: str
) -> None:
    """Inserts an evidence-rich blocker_card with a hyperlink to the code branch."""
    branch_url = f"https://github.com/{repo_full_name}/tree/{branch}"
    
    content = (
        f"❌ **Execution Blocked**\n"
        f"**Failed Step**: {step_desc}\n"
        f"**Failure Category**: {category}\n"
        f"**Code Branch**: [{branch}]({branch_url})\n\n"
        f"**Evidence**:\n```\n{evidence}\n```"
    )
    
    await publish_thread_message(
        ticket_id=ticket_id,
        channel_id=channel_id,
        content=content,
        msg_type="blocker_card",
        metadata_json={
            "event": "execution_blocked",
            "category": category,
            "evidence": evidence,
            "step_description": step_desc,
            "branch_name": branch,
            "branch_url": branch_url
        }
    )


def format_step_prompt(step: Dict[str, Any]) -> str:
    """Format step task with clear context boundaries for the smaller local model."""
    step_num = step.get("step_number", "?")
    description = step.get("description", "")
    target_file = step.get("target_file_path", "")
    action_type = step.get("action_type", "")

    prompt = f"Executing Plan Step {step_num}:\n"
    prompt += f"Task description: {wrap_untrusted(description)}\n"
    if target_file:
        # Strip any leading slashes and resolve the absolute path inside the sandbox mount
        clean_target_file = target_file.lstrip("/")
        absolute_target_file = f"/workspace/repo/{clean_target_file}"
        prompt += f"Target File: {target_file} (Absolute path in the sandbox environment: {absolute_target_file})\n"
    if action_type:
        prompt += f"Expected Action Type: {action_type}\n"
    prompt += "\n"
    prompt += "Please edit or modify the codebase to accomplish this specific step. "
    prompt += "Keep your changes strictly within scope. Focus only on completing this target task."
    
    # Concise directive to avoid str_replace mismatches on whole-file replacements
    prompt += "\n\nCRITICAL DIRECTIVE:\n"
    prompt += "To completely replace or write the contents of a file, use a terminal write command (e.g., cat << 'EOF' > path) instead of 'str_replace' to avoid verbatim string matching failures."
    prompt += (
        "\nNever include markdown code fences (```) in file content you write or edit. "
        "old_str/new_str and any file content must be the exact raw source code with no "
        "surrounding fence markers, language tags, or backticks that aren't part of the actual code."
    )
    return prompt


async def inject_loop_warning_async(conversation: Any, warning_msg: str) -> None:
    """Async thread helper to inject stuck-loop warnings to the agent."""
    logger.info("Injecting stuck-loop warning into active conversation: %s", warning_msg)
    await asyncio.to_thread(conversation.send_message, warning_msg)


async def _run_conversation_or_abort(conversation: Any, ctx: RunContext) -> None:
    """Runs conversation.run() in a worker thread, racing it against a
    guardrail-requested abort (ctx.abort_event).

    This is the fix for the known race condition: a guardrail (dynamic lock
    conflict, stuck loop) used to call teardown_sandbox() directly from its
    own callback, with no coordination against whatever this coroutine (or
    the commit/push/manifest-update steps right after it) was doing at that
    exact moment. Now a guardrail only sets ctx.step_exception and wakes
    ctx.abort_event -- it never touches the sandbox. If the abort wins the
    race, this function returns as soon as the signal arrives instead of
    waiting for the OpenHands thread to finish on its own; that thread is
    left to finish in the background (its result, if any, is discarded and
    only logged), and control returns immediately so the orchestrator can
    unwind through its normal exception handling and tear the sandbox down
    itself, exactly once, in run_agent_plan's finally block.
    """
    run_task = asyncio.create_task(asyncio.to_thread(conversation.run))
    abort_task = asyncio.create_task(ctx.abort_event.wait())

    done, _ = await asyncio.wait({run_task, abort_task}, return_when=asyncio.FIRST_COMPLETED)

    if abort_task in done:
        def _log_orphaned_run(f: asyncio.Task) -> None:
            if f.cancelled():
                return
            exc = f.exception()
            if exc is not None:
                logger.warning(
                    "OpenHands conversation.run() raised after an abort was "
                    "already requested (result discarded): %s", exc
                )

        run_task.add_done_callback(_log_orphaned_run)
        raise ctx.step_exception or RuntimeError("Run aborted by a guardrail with no exception recorded.")

    abort_task.cancel()
    await run_task  # propagate any exception from conversation.run itself
    if ctx.step_exception is not None:
        raise ctx.step_exception


async def run_agent_plan(agent_run_id: str, job_try: int) -> None:
    """Executes the complete development plan step-by-step with safety guards."""
    logger.info("Starting execution of Agent Run %s (Try %d)", agent_run_id, job_try)

    # 1. Clean up stale steps & load Completed Checkpoints
    await cleanup_unfinished_steps(agent_run_id)
    completed_steps = await fetch_completed_step_numbers(agent_run_id)
    logger.info("Completed steps already recorded in Postgres: %s", completed_steps)

    # 2. Load Context
    ctx = await fetch_execution_context(agent_run_id)
    if not ctx:
        raise ValueError(f"Agent Run {agent_run_id} or associated Git integration not found.")

    await update_run_status(agent_run_id, "running")

    # 3. Extract configuration
    plan_json = ctx["plan_json"] or {}
    steps: List[Dict[str, Any]] = plan_json.get("steps", [])
    if not steps:
        logger.warning("No steps defined for agent run %s. Finishing.", agent_run_id)
        return

    steps = sorted(steps, key=lambda s: s.get("step_number", 0))

    project_id = ctx["project_id"]
    default_branch = ctx["default_branch"]
    ticket_id = ctx["ticket_id"]
    ticket_title = ctx["ticket_title"]
    ticket_description = ctx["ticket_description"]
    channel_id = ctx["channel_id"]
    branch = branch_name(ticket_id, ticket_title)

    integration = GitIntegrationRef(
        provider=ctx["provider"],
        external_ref=ctx["github_app_installation_id"],
        repo_full_name=ctx["repo_full_name"],
    )
    repo_name = integration.repo_full_name
    git_provider = get_git_provider(integration.provider)

    # 4. Retrieve authentication and clone branch
    token = await git_provider.get_access_token(integration)
    clone_url = git_provider.build_authenticated_clone_url(integration, token)

    host_repo_path, _ = await clone_and_checkout(
        agent_run_id=agent_run_id,
        clone_url=clone_url,
        ticket_id=ticket_id,
        ticket_title=ticket_title,
        default_branch=default_branch,
    )

    # 5. Spin up sandbox container
    logger.info("Initializing Docker Sandbox for run %s", agent_run_id)

    relative_repo_path = os.path.relpath(host_repo_path, REPO_WORK_ROOT)
    resolved_host_repo_path = os.path.join(REPO_WORK_ROOT_HOST, relative_repo_path)

    sandbox_handle = create_sandbox(agent_run_id=agent_run_id, host_repo_path=resolved_host_repo_path)

    try:
        main_loop = asyncio.get_running_loop()

        # Shared state read/written by the step loop below and by the three
        # guardrail subscribers -- see guardrails/context.py. Guardrails only
        # ever call ctx.request_abort(); they never touch sandbox_handle.
        # This object is what used to be a set of closure-captured local
        # variables (current_step_locks, active_fencing_token, etc.) plus a
        # `nonlocal step_exception` -- now they're fields on ctx instead.
        # Constructed before bus/conversation setup so it's guaranteed to
        # exist for the except clauses below even if open_conversation itself
        # fails.
        ctx = RunContext(
            agent_run_id=agent_run_id,
            project_id=project_id,
            ticket_id=ticket_id,
            channel_id=channel_id,
            repo_full_name=repo_name,
            branch=branch,
            main_loop=main_loop,
        )

        bus = EventBus()
        logger.info("Opening long-lived OpenHands conversation inside Sandbox")
        conversation = await asyncio.to_thread(open_conversation, sandbox_handle, bus)

        async def inject_warning(warning_msg: str) -> None:
            await inject_loop_warning_async(conversation, warning_msg)

        bus.subscribe(DynamicLockSubscriber(ctx).handle)
        bus.subscribe(StuckLoopSubscriber(ctx, inject_warning).handle)
        bus.subscribe(ProtectedPathSubscriber(ctx).handle)

        # 6. Step Loop execution
        for step in steps:
            step_num = step.get("step_number", 0)
            
            if step_num in completed_steps:
                logger.info("Step %d already completed in previous run attempt. Skipping.", step_num)
                continue

            description = step.get("description", "")
            target_file = step.get("target_file_path", "")
            action_type = step.get("action_type", "")

            # Reset step context safely
            ctx.current_step_description = description
            ctx.current_step_locks.clear()
            if target_file:
                ctx.current_step_locks.add(target_file)

            ctx.active_detector = StuckLoopDetector()

            # Insert initial Postgres run step record
            step_record_id = await create_agent_run_step(
                agent_run_id=agent_run_id,
                step_number=step_num,
                description=description,
                job_try=job_try,
            )
            ctx.current_step_record_id = step_record_id

            # Lock Acquisition
            try:
                ctx.active_fencing_token = await register_step_and_acquire_locks(
                    run_id=agent_run_id,
                    project_id=project_id,
                    ticket_id=ticket_id,
                    step_number=step_num,
                    file_paths=list(ctx.current_step_locks),
                    purpose_summary=f"Ticket: {ticket_title}. Step {step_num}: {description}",
                )
                logger.info("Locks acquired successfully. Counter token: %d", ctx.active_fencing_token)
            except (LockConflictError, SemanticConflictError) as conflict:
                logger.warning("Execution blocked for run %s step %d: %s", agent_run_id, step_num, conflict)
                await update_ticket_status(ticket_id, "blocked")
                await update_run_status(agent_run_id, "failed")
                await insert_blocker_card(
                    ticket_id=ticket_id,
                    channel_id=channel_id,
                    step_desc=description,
                    category=type(conflict).__name__,
                    evidence=str(conflict),
                    repo_full_name=repo_name,
                    branch=branch
                )
                await fail_agent_run_step(
                    step_id=step_record_id,
                    error=str(conflict),
                    model_prompt=format_step_prompt(step)
                )
                raise

            # Thread progress notification (Step Started)
            step_start_content = f"🔄 Code Agent starting Step {step_num}: {description}"
            await publish_thread_message(
                ticket_id=ticket_id,
                channel_id=channel_id,
                content=step_start_content,
                msg_type="system",
                metadata_json={
                    "event": "agent.progress",
                    "status": "started",
                    "step_number": step_num,
                    "description": description
                }
            )

            prompt = format_step_prompt(step)

            check_tier_logged = "sanity_only"
            passed_validation = False
            validation_failures = []
            correction_budget = CORRECTION_ATTEMPT_BUDGET

            # Initial Agent Run execution
            try:
                logger.info("Executing agent runner for step %d", step_num)
                await asyncio.to_thread(conversation.send_message, prompt)
                await _run_conversation_or_abort(conversation, ctx)

            except Exception as run_exc:
                # Capture and elevate logical exceptions recorded by a guardrail
                if ctx.step_exception is not None:
                    run_exc = ctx.step_exception

                logger.exception("Agent execution crashed for step %d", step_num)
                await fail_agent_run_step(
                    step_id=step_record_id,
                    error=f"Agent execution crashed: {run_exc}",
                    check_tier="sanity_only",
                    model_prompt=prompt,
                )
                await release_locks(agent_run_id, project_id, list(ctx.current_step_locks))
                raise

            # --- Soft-Failure Correction Loop ---
            try:
                for attempt in range(1, correction_budget + 1):
                    # Check if a guardrail registered an abort since the last attempt
                    if ctx.step_exception is not None:
                        raise ctx.step_exception

                    touched_this_step = await changed_files(host_repo_path)
                    logger.info(
                        "Step %d (Attempt %d) completed on disk. Touched files: %s. Validating...",
                        step_num,
                        attempt,
                        touched_this_step,
                    )

                    valid, check_tier_logged, err_details = await validate_step_changes(
                        sandbox_handle, host_repo_path, touched_this_step, action_type
                    )

                    if valid:
                        passed_validation = True
                        logger.info(
                            "Step %d passed validation at Attempt %d (Tier: %s)",
                            step_num,
                            attempt,
                            check_tier_logged,
                        )
                        break

                    validation_failures.append(err_details)
                    logger.warning(
                        "Step %d validation failed at Attempt %d. Error:\n%s",
                        step_num,
                        attempt,
                        err_details,
                    )

                    if attempt == correction_budget:
                        break

                    # Thread progress notification (Step Correcting)
                    step_corr_content = (
                        f"⚠️ Step {step_num} failed validation (Tier: {check_tier_logged}). "
                        f"Initiating correction attempt {attempt} of {correction_budget}..."
                    )
                    await publish_thread_message(
                        ticket_id=ticket_id,
                        channel_id=channel_id,
                        content=step_corr_content,
                        msg_type="system",
                        metadata_json={
                            "event": "agent.progress",
                            "status": "correcting",
                            "step_number": step_num,
                            "attempt": attempt,
                            "check_tier": check_tier_logged
                        }
                    )

                    if attempt == 1:
                        touched_content = ""
                        for f in touched_this_step:
                            full_path = os.path.join(host_repo_path, f)
                            if os.path.isfile(full_path):
                                with open(full_path, "r", encoding="utf-8") as fh:
                                    touched_content += f"\n--- CURRENT CONTENT OF {f} ---\n{fh.read()}\n"

                        feedback_prompt = (
                            "The changes made in your previous action failed validation checks. "
                            "Please review the exact, raw failure logs below and make the required corrections "
                            "in the codebase:\n\n"
                            f"=== FAILURE LOG ===\n{err_details}\n===================\n"
                            f"{wrap_untrusted(touched_content)}\n"
                            "Resolve these errors directly. Do not exceed the scope of the target task."
                        )
                    else:
                        cumulative_history = ""
                        for idx, fail in enumerate(validation_failures):
                            cumulative_history += f"--- FAILURE ATTEMPT {idx + 1} ---\n{fail}\n\n"

                        feedback_prompt = (
                            "Your previous correction also failed validation. Your first fix did NOT resolve the issues.\n"
                            "Below is the cumulative error history of all validation failures:\n\n"
                            f"{cumulative_history}"
                            "Analyze these logs carefully. Refactor your approach, resolve the conflicts, "
                            "and ensure all tests pass cleanly."
                        )

                    logger.info("Injecting soft-failure feedback to agent (Attempt %d)", attempt + 1)
                    await asyncio.to_thread(conversation.send_message, feedback_prompt)
                    await _run_conversation_or_abort(conversation, ctx)

                if not passed_validation:
                    all_errors_log = "\n---\n".join(validation_failures)
                    raise SoftAIFailureError(
                        f"Validation failed after exhausting correction budget of {correction_budget} attempts.\n"
                        f"Cumulative error logs:\n{all_errors_log}"
                    )

                # --- Step 14: Commit & Push Logic ---
                if await has_changes(host_repo_path):
                    commit_msg = f"ai/ticket-{ticket_id}: Step {step_num} - {description[:100]}"
                    logger.info("Step passed validation. Committing changes with msg: '%s'", commit_msg)
                    
                    commit_sha = await commit_all(host_repo_path, commit_msg)
                    logger.info("Step %d committed. SHA: %s. Pushing to branch %s...", step_num, commit_sha, branch)
                    
                    try:
                        await push(host_repo_path, branch)
                        logger.info("Branch %s pushed successfully.", branch)
                    except PushRejectedError as push_err:
                        logger.error("Push rejected for branch %s: %s", branch, push_err)
                        await update_ticket_status(ticket_id, "blocked")
                        await update_run_status(agent_run_id, "failed")
                        await insert_blocker_card(
                            ticket_id=ticket_id,
                            channel_id=channel_id,
                            step_desc=description,
                            category="PushRejected",
                            evidence=str(push_err),
                            repo_full_name=repo_name,
                            branch=branch
                        )
                        await fail_agent_run_step(
                            step_id=step_record_id,
                            error=str(push_err),
                            check_tier=check_tier_logged,
                            model_prompt=prompt,
                        )
                        raise

                    # --- Step 15: Codebase Manifest Incremental Updates ---
                    logger.info("Incremental codebase manifest update initiated for step %d.", step_num)
                    try:
                        await update_codebase_manifest_incremental(
                            project_id=project_id,
                            ticket_id=ticket_id,
                            host_repo_path=host_repo_path,
                            file_paths=touched_this_step
                        )
                        logger.info("Codebase manifest updated successfully for step %d.", step_num)
                    except Exception as manifest_err:
                        logger.exception("Incremental codebase manifest update failed; absorbing and continuing: %s", manifest_err)
                else:
                    logger.info("No modifications detected on disk for step %d. Skipping commit, push & manifest update.", step_num)

                # Successfully completed step
                logger.info("Step %d completed successfully and passed validation", step_num)
                await complete_agent_run_step(
                    step_id=step_record_id,
                    check_tier=check_tier_logged,
                    model_prompt=prompt,
                    model_response=(
                        f"Step completed successfully and passed validation. "
                        f"Completed with {len(validation_failures)} correction attempts."
                    ),
                )

                # Thread progress notification (Step Completed)
                step_comp_content = f"✅ Step {step_num} completed successfully! Passed validation via {check_tier_logged}."
                await publish_thread_message(
                    ticket_id=ticket_id,
                    channel_id=channel_id,
                    content=step_comp_content,
                    msg_type="system",
                    metadata_json={
                        "event": "agent.progress",
                        "status": "completed",
                        "step_number": step_num,
                        "check_tier": check_tier_logged
                    }
                )

            except Exception as step_exc:
                # Capture and elevate logical exceptions recorded by a guardrail
                if ctx.step_exception is not None:
                    step_exc = ctx.step_exception
                logger.exception("Step %d execution failed", step_num)
                raise
            finally:
                logger.info("Releasing step locks for run %s", agent_run_id)
                await release_locks(agent_run_id, project_id, list(ctx.current_step_locks))

        # Completed all steps successfully
        logger.info("All plan steps for Agent Run %s completed successfully", agent_run_id)

        # --- Step 16: Pull/Merge Request Creation ---
        pr_title = f"ai/ticket-{ticket_id}: {ticket_title}"
        completed_steps_details = await fetch_completed_steps_details(agent_run_id)
        
        pr_body = assemble_pr_body(
            ticket_title=ticket_title,
            ticket_description=ticket_description,
            completed_steps=completed_steps_details
        )
        
        logger.info("Opening pull request for branch: %s targeting base: %s", branch, default_branch)
        pr_payload = await git_provider.open_pull_request(
            integration,
            head_branch=branch,
            base_branch=default_branch,
            title=pr_title,
            body=pr_body
        )
        
        pr_number = pr_payload.get("number")
        pr_html_url = pr_payload.get("html_url", "")
        logger.info("Pull request #%s created successfully: %s", pr_number, pr_html_url)
        
        # Save PR number in Postgres and transition ticket state
        if pr_number:
            await update_ticket_pr_details(ticket_id, pr_number)

        await update_ticket_status(ticket_id, "in_review")
        await update_run_status(agent_run_id, "approved")

        # --- Step 17: Completion Card Event ---
        completion_card_content = (
            f" **Implementation Complete!** Pull Request #{pr_number} has been opened: "
            f"[View Pull Request]({pr_html_url})\n\n"
            "This completes the agent's automated execution loop. The code is ready for human review."
        )
        await publish_thread_message(
            ticket_id=ticket_id,
            channel_id=channel_id,
            content=completion_card_content,
            msg_type="approval_card",
            metadata_json={
                "event": "agent.card",
                "status": "finished",
                "pr_number": pr_number,
                "pr_url": pr_html_url,
                "title": pr_title
            }
        )

    except (LockConflictError, SemanticConflictError, StuckLoopTriggered, PushRejectedError):
        # Re-raise so the job terminates without scheduling arq retries (since these are logical blocks)
        raise
        
    except SoftAIFailureError as soft_err:
        # Step 18: Soft failure escalation (no retries)
        logger.error("Soft AI Failure captured: correction budget exhausted. Escalating run %s.", agent_run_id)
        await update_ticket_status(ticket_id, "blocked")
        await update_run_status(agent_run_id, "failed")
        await insert_blocker_card(
            ticket_id=ticket_id,
            channel_id=channel_id,
            step_desc=ctx.current_step_description or "Step execution block",
            category="SoftAIFailure",
            evidence=str(soft_err),
            repo_full_name=repo_name,
            branch=branch
        )
        raise

    except Exception as exc:
        # Unexpected technical exception; propagate up to arq worker to trigger retry schedules
        if ctx.step_exception is not None:
            exc = ctx.step_exception
        logger.error("Hard Technical system failure captured for run %s: %s", agent_run_id, exc)
        raise

    finally:
        logger.info("Tearing down Sandbox for run %s", agent_run_id)
        teardown_sandbox(sandbox_handle)