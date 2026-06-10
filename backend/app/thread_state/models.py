import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ThreadState(Base):
    __tablename__ = "thread_states"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # 1:1 with Ticket — only discipline channel tickets have a ThreadState.
    ticket_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # Updated every 12 messages by Observer Agent (Phase 3 — null until then).
    rolling_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Proposals, objections, consensus score — managed by Observer Agent (Phase 3).
    structured_state_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Observer Agent's processing watermark (Phase 3 — null until then).
    last_processed_message_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("messages.id", ondelete="SET NULL"),
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