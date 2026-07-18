import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentRunStatus(str, PyEnum):
    pending = "pending"
    running = "running"
    awaiting_review = "awaiting_review"  # generation succeeded, plan_review gate
    approved = "approved"                # Team Lead approved (hand-off semantics: Code Agent scoping)
    rejected = "rejected"
    failed = "failed"


class AgentRunStepStatus(str, PyEnum):
    running = "running"
    completed = "completed"
    failed = "failed"
    
class AgentRunStepPhase(str, PyEnum):
    planning = "planning"
    execution = "execution"

class CheckTier(str, PyEnum):
    repo_test_suite = "repo_test_suite"
    generic_validator = "generic_validator"
    sanity_only = "sanity_only"

class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        # One active (pending/running) run per ticket — DB-level concurrency guard.
        # See Planning Agent build plan -> Locked Decisions -> Concurrency.
        Index(
            "uq_agent_runs_ticket_active",
            "ticket_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    ticket_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # No server_default — always set explicitly (matches Ticket.status convention).
    status: Mapped[AgentRunStatus] = mapped_column(
        Enum(AgentRunStatus, name="agentrunstatus"), nullable=False
    )
    # Null until the draft/critique calls succeed.
    plan_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Hard-technical-failure retry counter (exponential backoff: 1/5/15 min, 3 attempts).
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Reserved for Code Agent's step-based resume (per Synapse_Project_Context data
    # model). Unused by the Planning Agent, which is non-looping and re-runs from
    # scratch on failure rather than resuming from a checkpoint.
    checkpoint_state_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Set when a Team Lead inline-edits the plan (build plan -> Edit/Reject semantics).
    edited_by_user_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    edited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AgentRunStep(Base):
    __tablename__ = "agent_run_steps"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    agent_run_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Free text, e.g. "draft", "critique", "summarization batch 2/3",
    # "file-grounding validation" — no separate step-type enum (matches the
    # original data model's field list).
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[AgentRunStepStatus] = mapped_column(
        Enum(AgentRunStepStatus, name="agentrunstepstatus"), nullable=False
    )
    model_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Code Agent additions (Step 6) — which validation tier actually ran for
    # this step; must be visible to a human reviewer.
    check_tier: Mapped[CheckTier | None] = mapped_column(
        Enum(CheckTier, name="checktier"), nullable=True
    )
    # Flagged when a step touches migration/alembic paths (observability).
    requires_human_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # arq attempt number this step record was produced under.
    job_try: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Discriminates Planning Agent bookkeeping rows (draft/critique/grounding
    # validation) from real Code Agent execution steps — checkpoint resume
    # must only ever look at 'execution' rows.
    phase: Mapped[AgentRunStepPhase] = mapped_column(
        Enum(AgentRunStepPhase, name="agentrunstepphase"),
        nullable=False,
        default=AgentRunStepPhase.execution,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )