import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TicketStatus(str, PyEnum):
    backlog = "backlog"
    routed = "routed"
    active = "active"
    in_discussion = "in_discussion"
    consensus_reached = "consensus_reached"  # Phase 4
    plan_review = "plan_review"              # Phase 4
    agent_working = "agent_working"          # Phase 4
    in_review = "in_review"                  # Phase 4
    split = "split"    # terminal — ticket split into children
    closed = "closed"  # terminal — work done


class TicketSource(str, PyEnum):
    synapse = "synapse"
    github = "github"


class TicketPriority(str, PyEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Mutable on routing — points to leads channel (backlog) or discipline channel (routed+).
    channel_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # No server_default — status is always set explicitly at creation.
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, name="ticketstatus"), nullable=False
    )
    source: Mapped[TicketSource] = mapped_column(
        Enum(TicketSource, name="ticketsource"),
        nullable=False,
        default=TicketSource.synapse,
    )
    priority: Mapped[TicketPriority] = mapped_column(
        Enum(TicketPriority, name="ticketpriority"),
        nullable=False,
        default=TicketPriority.medium,
    )
    # Null for unmatched GitHub tickets (no Synapse account found for the GitHub author).
    creator_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Populated for GitHub-sourced tickets.
    github_issue_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # GitHub login — always set for github-sourced tickets, null for synapse-sourced.
    github_author_login: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    # Set when the Code Agent opens a PR (Phase 4).
    github_pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Set when this ticket is a child of a split parent.
    parent_ticket_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("tickets.id", ondelete="SET NULL"),
        nullable=True,
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