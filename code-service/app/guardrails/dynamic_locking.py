"""Dynamic-lock guardrail: reacts to files touched mid-step that weren't
part of the step's declared target, acquiring locks for them on the fly.

Promoted out of runner.py's dynamic_lock_subscriber closure. Previously,
failure to acquire a lock called teardown_sandbox() directly from this
callback; now it only calls ctx.request_abort(), and the orchestrator
performs the actual teardown once, at a point it controls (see the
race-condition note in guardrails/context.py).
"""

import asyncio
import logging

from app.guardrails.context import RunContext
from app.locks import acquire_dynamic_locks
from app.openhands.events import AgentEvent

logger = logging.getLogger(__name__)


class DynamicLockSubscriber:
    def __init__(self, ctx: RunContext):
        self._ctx = ctx

    def handle(self, event: AgentEvent) -> None:
        ctx = self._ctx
        if not event.touched_paths:
            return

        new_files = [fp for fp in event.touched_paths if fp not in ctx.current_step_locks]
        if not new_files:
            return

        logger.info("Mid-step edits detected. Acquiring locks: %s", new_files)
        fut = asyncio.run_coroutine_threadsafe(
            acquire_dynamic_locks(
                run_id=ctx.agent_run_id,
                project_id=ctx.project_id,
                file_paths=new_files,
                fencing_token=ctx.active_fencing_token,
            ),
            ctx.main_loop,
        )

        def on_lock_complete(f) -> None:
            try:
                f.result()
            except Exception as e:
                # Previously: teardown_sandbox(sandbox_handle) directly here.
                # Now: signal only -- the orchestrator owns the teardown.
                ctx.request_abort(e)

        fut.add_done_callback(on_lock_complete)
        ctx.current_step_locks.update(new_files)