"""Stuck loop detection and budget control for Code Agent runs (Build Plan Step 11).

Maintains a sliding window of recent tool call events and processes SHA-256 fingerprints
to identify looping behaviors, dispatch warnings, and raise budget exhaustion errors.
"""

import logging
from collections import deque
from typing import Deque, Dict, Set

from app.config import STUCK_LOOP_BUDGET, STUCK_LOOP_THRESHOLD, STUCK_LOOP_WINDOW
from app.openhands.events import AgentEvent, AgentEventKind

logger = logging.getLogger(__name__)


class StuckLoopTriggered(RuntimeError):
    """Raised when the stuck-loop budget is completely exhausted."""


class StuckLoopDetector:
    """Detects stuck loops during agent tool execution (Build Plan Step 11)."""

    def __init__(self) -> None:
        # Sliding window of fingerprints of the last 20 tool calls (ACTIONS)
        self.window: Deque[str] = deque(maxlen=STUCK_LOOP_WINDOW)
        # Keeps track of tool details for error reporting
        self.fingerprint_meta: Dict[str, str] = {}
        # Count of recurrences of a fingerprint AFTER warning has been sent
        self.escalated_counts: Dict[str, int] = {}
        # Set of fingerprints for which warnings have been dispatched
        self.warning_sent: Set[str] = set()

    def process_event(self, event: AgentEvent) -> str | None:
        """Processes an event.

        Returns a warning message if a loop pattern is identified,
        or raises StuckLoopTriggered if the action budget is exhausted.
        """
        # Only analyze tool actions (tool calls)
        if event.kind != AgentEventKind.ACTION:
            return None

        fp = event.fingerprint()
        self.window.append(fp)
        
        # Capture metadata for evidence logs
        self.fingerprint_meta[fp] = f"Tool: {event.tool_name}, Arguments: {event.args}"

        # Count occurrences in the current sliding window
        count_in_window = self.window.count(fp)

        if count_in_window >= STUCK_LOOP_THRESHOLD:
            if fp not in self.warning_sent:
                self.warning_sent.add(fp)
                logger.warning("Stuck loop pattern detected for fingerprint %s. Preparing warning.", fp)
                return (
                    f"Warning: A repeating pattern has been detected. You have called "
                    f"the tool '{event.tool_name}' with the same arguments {count_in_window} times. "
                    f"Please try a different approach or tool instead of repeating this call."
                )
            else:
                # Fingerprint recurred AFTER warning was sent -> count against stuck-loop budget
                self.escalated_counts[fp] = self.escalated_counts.get(fp, 0) + 1
                logger.warning(
                    "Stuck loop recurred for fingerprint %s (recurrence %d/%d)",
                    fp,
                    self.escalated_counts[fp],
                    STUCK_LOOP_BUDGET
                )
                if self.escalated_counts[fp] >= STUCK_LOOP_BUDGET:
                    raise StuckLoopTriggered(
                        f"Stuck loop budget exhausted. Loop details:\n{self.fingerprint_meta[fp]}"
                    )
        return None