"""Shared mutable state passed to every guardrail subscriber for a single
Code Agent run.

The three guardrails (dynamic locking, stuck-loop detection, protected-path
enforcement) each react to AgentEvents emitted while the OpenHands
conversation runs in a background thread. Before this module existed they
were closures inside run_agent_plan(), reading and writing that coroutine's
local variables directly via `nonlocal`. Promoting them to standalone
classes means they need an explicit shared object instead -- this is that
object. One instance is created per run_agent_plan() call and passed by
reference to the orchestrator and all three guardrails.

request_abort() is also where the sandbox-teardown race condition is fixed:
guardrails call it instead of touching the sandbox themselves. Only
run_agent_plan's own orchestration code ever calls teardown_sandbox -- see
runner.py's _run_conversation_or_abort and its finally block.
"""

import asyncio
from dataclasses import dataclass, field

from app.loops_detector import StuckLoopDetector


@dataclass
class RunContext:
    agent_run_id: str
    project_id: str
    ticket_id: str
    channel_id: str
    repo_full_name: str
    branch: str
    main_loop: asyncio.AbstractEventLoop

    # Set by the orchestrator's step loop as each step starts.
    current_step_locks: set = field(default_factory=set)
    active_fencing_token: int = 0
    active_detector: StuckLoopDetector | None = None
    current_step_description: str = ""
    current_step_record_id: str = ""

    # Cross-thread signaling only -- guardrails never touch the sandbox.
    step_exception: Exception | None = None
    abort_event: asyncio.Event = field(default_factory=asyncio.Event)

    def request_abort(self, exc: Exception) -> None:
        """Called by a guardrail (possibly from an OpenHands callback thread)
        to signal that the run must stop. Records the exception and wakes
        the orchestrator via the event loop; does NOT call teardown_sandbox.
        Only run_agent_plan's own finally block tears the sandbox down, and
        only once -- that ownership rule is the actual fix for the known
        race condition, where a guardrail previously tore the sandbox down
        directly from its own callback, with no coordination against
        whatever the main coroutine was doing at that moment (mid-commit,
        mid manifest-update, etc.).
        """
        if self.step_exception is None:
            self.step_exception = exc
        self.main_loop.call_soon_threadsafe(self.abort_event.set)