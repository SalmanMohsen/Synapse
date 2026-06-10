import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GitIntegration(Base):
    __tablename__ = "git_integrations"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # One GitHub repo per Synapse project.
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    github_app_installation_id: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True
    )
    # e.g. "owner/repo"
    repo_full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    default_branch: Mapped[str] = mapped_column(
        String(100), nullable=False, default="main"
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


class WebhookEventStatus(str, PyEnum):
    pending = "pending"
    processing = "processing"
    processed = "processed"
    failed = "failed"


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # X-GitHub-Delivery header value — unique constraint enforces idempotency.
    delivery_id: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True
    )
    # e.g. "issues", "pull_request"
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # e.g. "opened", "reopened", "closed"
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[WebhookEventStatus] = mapped_column(
        Enum(WebhookEventStatus, name="webhookeventstatus"),
        nullable=False,
        default=WebhookEventStatus.pending,
    )
    # Populated on failure.
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Set when status transitions to processed or failed.
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )