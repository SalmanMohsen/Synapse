"""Stuck-loop guardrail: feeds emitted events into a per-step
StuckLoopDetector, injects a warning into the live conversation if the
budget is getting close, and requests an abort once it's exhausted.

Promoted out of runner.py's stuck_loop_subscriber closure and
abort_due_to_stuck_loop helper. abort_due_to_stuck_loop no longer calls
teardown_sandbox itself (see the race-condition note in
guardrails/context.py) -- it only posts the blocker card / status update,
then hands off to ctx.request_abort(), leaving the sandbox teardown to
run_agent_plan's own finally block.
"""

import asyncio
import logging

from app.guardrails.context import RunContext
from app.loops_detector import StuckLoopTriggered
from app.openhands.events import AgentEvent

logger = logging.getLogger(__name__)


async def _abort_due_to_stuck_loop(ctx: RunContext, evidence: str) -> None:
    """Posts the blocker card and status updates for a stuck-loop abort.
    Does NOT touch the sandbox -- import is local to avoid a runner <->
    guardrails circular import, since these DB/messaging helpers still live
    in runner.py."""
    from app.runner import insert_blocker_card, update_run_status, update_ticket_status

    logger.error("Forcibly aborting execution due to stuck loop pattern: %s", evidence)
    await update_ticket_status(ctx.ticket_id, "blocked")
    await update_run_status(ctx.agent_run_id, "failed")
    await insert_blocker_card(
        ticket_id=ctx.ticket_id,
        channel_id=ctx.channel_id,
        step_desc=ctx.current_step_description,
        category="StuckLoop",
        evidence=evidence,
        repo_full_name=ctx.repo_full_name,
        branch=ctx.branch,
    )


class StuckLoopSubscriber:
    def __init__(self, ctx: RunContext, inject_warning):
        """inject_warning: async callable(warning_msg: str) -> None, used to
        send a warning into the live OpenHands conversation. Passed in by
        the orchestrator rather than imported, since it needs to close over
        the specific open `conversation` object run_agent_plan holds."""
        self._ctx = ctx
        self._inject_warning = inject_warning

    def handle(self, event: AgentEvent) -> None:
        ctx = self._ctx
        if not ctx.active_detector:
            return

        try:
            warning_msg = ctx.active_detector.process_event(event)
            if warning_msg:
                asyncio.run_coroutine_threadsafe(
                    self._inject_warning(warning_msg), ctx.main_loop
                )
        except StuckLoopTriggered as triggered:

            async def _abort() -> None:
                await _abort_due_to_stuck_loop(ctx, str(triggered))
                # Previously: teardown_sandbox(sandbox_handle) directly here.
                # Now: signal only -- the orchestrator owns the teardown.
                ctx.request_abort(triggered)

            asyncio.run_coroutine_threadsafe(_abort(), ctx.main_loop)