"""Guardrail subscribers wired onto the Code Agent's EventBus.

Each guardrail reacts to AgentEvents emitted while the OpenHands
conversation runs and can request that the run stop (RunContext.request_abort),
but never touches the sandbox directly -- only run_agent_plan's orchestrator
owns sandbox_handle and calls teardown_sandbox. See context.py for the
race-condition rationale.
"""

from app.guardrails.context import RunContext
from app.guardrails.dynamic_locking import DynamicLockSubscriber
from app.guardrails.protected_paths import (
    ProtectedPathSubscriber,
    is_migration_path,
    is_protected_ci_path,
)
from app.guardrails.stuck_loop import StuckLoopSubscriber

__all__ = [
    "RunContext",
    "DynamicLockSubscriber",
    "ProtectedPathSubscriber",
    "StuckLoopSubscriber",
    "is_migration_path",
    "is_protected_ci_path",
]