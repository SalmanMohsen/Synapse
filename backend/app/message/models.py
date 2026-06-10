import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MessageType(str, PyEnum):
    human = "human"
    system = "system"
    approval_card = "approval_card"  # enum value defined now, business logic Phase 4
    plan_card = "plan_card"          # enum value defined now, business logic Phase 4
    blocker_card = "blocker_card"    # enum value defined now, business logic Phase 4


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    ticket_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Null for system messages (author_id=None signals agent/system origin).
    author_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[MessageType] = mapped_column(
        Enum(MessageType, name="messagetype"),
        nullable=False,
        default=MessageType.human,
    )
    # Structured payload for system messages and agent cards (see plan Section 4).
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Soft delete — content is preserved in DB, null means not deleted.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set when the author edits the content after creation.
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