"""Normalized agent event model (build plan Step 5).

The build plan makes the OpenHands Action/Observation event stream the SINGLE
source of truth: all logging, progress publishing, stuck-loop detection, and
dangerous-action flagging subscribe to the SAME stream — no stdout/CLI parsing
anywhere.

To keep the rest of the service decoupled from the exact OpenHands SDK event
classes (whose surface varies across versions), the adapter (conversation.py)
translates raw SDK events into these normalized dataclasses. Steps 6/9/10/11
subscribe to these, not to SDK internals.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class AgentEventKind(str, Enum):
    ACTION = "action"          # the agent decided to do something (tool call)
    OBSERVATION = "observation"  # the result of an action
    MESSAGE = "message"        # agent/user natural-language message
    ERROR = "error"            # the agent reported an internal error
    FINISH = "finish"          # the agent signalled the step/task is complete


@dataclass
class AgentEvent:
    """A single normalized event from the agent's stream."""
    kind: AgentEventKind
    # Tool/action name for ACTION events (e.g. "run", "edit", "read", "grep").
    tool_name: str | None = None
    # Serialized arguments the action was invoked with.
    args: dict[str, Any] = field(default_factory=dict)
    # A short preview of the observation/result text.
    result_preview: str = ""
    # Any file paths this event touched (writes), used for locking + manifest.
    touched_paths: list[str] = field(default_factory=list)
    # Free-form text payload (messages, errors).
    text: str = ""
    # The raw SDK event, retained for audit/debugging only.
    raw: Any = None

    def fingerprint(self) -> str:
        """SHA-256(tool_name + serialized_args + result_preview) — the stuck-loop
        fingerprint defined in the build plan (Step 11)."""
        serialized_args = json.dumps(self.args, sort_keys=True, default=str)
        material = f"{self.tool_name or ''}|{serialized_args}|{self.result_preview}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


# A subscriber is any callable taking one AgentEvent. Subscribers must be cheap
# and non-blocking-ish; heavy work should be offloaded. They must never raise —
# a raising subscriber must not break the agent's event loop.
EventSubscriber = Callable[[AgentEvent], None]


class EventBus:
    """Fan-out dispatcher. The conversation adapter publishes normalized events
    here; Steps 6/9/10/11 register subscribers."""

    def __init__(self) -> None:
        self._subscribers: list[EventSubscriber] = []

    def subscribe(self, subscriber: EventSubscriber) -> None:
        self._subscribers.append(subscriber)

    def publish(self, event: AgentEvent) -> None:
        for sub in self._subscribers:
            try:
                sub(event)
            except Exception:  # noqa: BLE001 - a bad subscriber must not kill the run
                import logging

                logging.getLogger(__name__).exception(
                    "Event subscriber raised; continuing"
                )
