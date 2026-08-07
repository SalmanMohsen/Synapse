import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from app.loops_detector import StuckLoopDetector, StuckLoopTriggered
from app.guardrails.stuck_loop import StuckLoopSubscriber
from app.guardrails.context import RunContext
from app.openhands.events import AgentEvent, AgentEventKind


def test_loops_detector_pattern_matching_lifecycle():
    detector = StuckLoopDetector()

    # Step 1-2: Normal unique tool executions (within sliding budget)
    event1 = AgentEvent(kind=AgentEventKind.ACTION, tool_name="grep", args={"pattern": "User"})
    event2 = AgentEvent(kind=AgentEventKind.ACTION, tool_name="grep", args={"pattern": "Workspace"})

    assert detector.process_event(event1) is None
    assert detector.process_event(event2) is None

    # Step 3: Start looping behavior (same signature)
    loop_event = AgentEvent(kind=AgentEventKind.ACTION, tool_name="edit", args={"path": "main.py"})
    
    # First 2 executions are permitted under threshold rules
    assert detector.process_event(loop_event) is None
    assert detector.process_event(loop_event) is None

    # Third execution of exact same footprint triggers the warning
    warning = detector.process_event(loop_event)
    assert warning is not None
    assert "Please try a different approach" in warning

    # Subsequent loop executions count against the loop correction budget (STUCK_LOOP_BUDGET = 5)
    # Re-executing 4 more times should be permitted
    for _ in range(4):
        detector.process_event(loop_event)

    # Fifth post-warning execution triggers budget exhaustion exception
    with pytest.raises(StuckLoopTriggered) as exc_info:
        detector.process_event(loop_event)
    assert "Stuck loop budget exhausted" in str(exc_info.value)


@pytest.mark.asyncio
async def test_stuck_loop_subscriber_abort_delegation():
    main_loop = asyncio.get_running_loop()
    ctx = RunContext(
        agent_run_id="run-1",
        project_id="proj-1",
        ticket_id="ticket-1",
        channel_id="chan-1",
        repo_full_name="org/repo",
        branch="dev",
        main_loop=main_loop
    )
    ctx.active_detector = StuckLoopDetector()
    ctx.current_step_description = "Configure main module"
    ctx.current_step_record_id = "step-1"

    # Seed loop threshold inside detector to trigger immediate budget failure
    loop_event = AgentEvent(kind=AgentEventKind.ACTION, tool_name="edit", args={"path": "main.py"})
    for _ in range(7):
        ctx.active_detector.window.append(loop_event.fingerprint())
    ctx.active_detector.warning_sent.add(loop_event.fingerprint())
    ctx.active_detector.escalated_counts[loop_event.fingerprint()] = 4

    inject_warning_mock = AsyncMock()
    subscriber = StuckLoopSubscriber(ctx, inject_warning_mock)

    # Patch run_coroutine_threadsafe to schedule tasks directly in the current loop thread
    with patch("app.guardrails.stuck_loop.asyncio.run_coroutine_threadsafe") as mock_run_threadsafe, \
         patch("app.guardrails.stuck_loop._abort_due_to_stuck_loop", new_callable=AsyncMock) as mock_abort:
        
        mock_run_threadsafe.side_effect = lambda coro, loop: asyncio.create_task(coro)

        subscriber.handle(loop_event)

        # Allow the event loop to run the scheduled task
        await asyncio.sleep(0.1)

        # Verify abort flow was executed cleanly
        mock_abort.assert_called_once_with(ctx, ctx.step_exception.__str__())
        assert isinstance(ctx.step_exception, StuckLoopTriggered)
        assert ctx.abort_event.is_set() is True
    main_loop = asyncio.get_running_loop()
    ctx = RunContext(
        agent_run_id="run-1",
        project_id="proj-1",
        ticket_id="ticket-1",
        channel_id="chan-1",
        repo_full_name="org/repo",
        branch="dev",
        main_loop=main_loop
    )
    ctx.active_detector = StuckLoopDetector()
    ctx.current_step_description = "Configure main module"
    ctx.current_step_record_id = "step-1"

    # Seed loop threshold inside detector to trigger immediate budget failure
    loop_event = AgentEvent(kind=AgentEventKind.ACTION, tool_name="edit", args={"path": "main.py"})
    for _ in range(7):
        ctx.active_detector.window.append(loop_event.fingerprint())
    ctx.active_detector.warning_sent.add(loop_event.fingerprint())
    ctx.active_detector.escalated_counts[loop_event.fingerprint()] = 4

    inject_warning_mock = AsyncMock()
    subscriber = StuckLoopSubscriber(ctx, inject_warning_mock)

    # Patch the thread-safe DB/message triggers inside StuckLoopSubscriber module
    with patch("app.guardrails.stuck_loop._abort_due_to_stuck_loop", new_callable=AsyncMock) as mock_abort:
        subscriber.handle(loop_event)
        
        # Allow the event loop to run background thread callbacks
        await asyncio.sleep(0.1)

        # Verify abort flow was executed cleanly
        mock_abort.assert_called_once_with(ctx, ctx.step_exception.__str__())
        assert isinstance(ctx.step_exception, StuckLoopTriggered)
        assert ctx.abort_event.is_set() is True