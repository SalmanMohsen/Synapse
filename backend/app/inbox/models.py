import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InboxItemType(str, PyEnum):
    workspace_invite = "workspace_invite"
    project_invite = "project_invite"
    channel_invite = "channel_invite"
    notification = "notification"


class InboxItemStatus(str, PyEnum):
    # Invite lifecycle
    pending = "pending"
    accepted = "accepted"
    declined = "declined"
    expired = "expired"
    # Notification lifecycle (no action needed — just read/unread)
    unread = "unread"
    read = "read"


class InboxItem(Base):
    """
    Single table for every item that lands in a user's inbox:
    - workspace/project/channel invites (status cycles through pending → accepted/declined/expired)
    - system notifications (status cycles through unread → read)

    FK columns are SET NULL on delete so the item survives as a historical
    record even if the workspace/project/channel is later removed.
    """

    __tablename__ = "inbox_items"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Recipient
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[InboxItemType] = mapped_column(
        Enum(InboxItemType, name="inboxitemtype"), nullable=False
    )
    status: Mapped[InboxItemStatus] = mapped_column(
        Enum(InboxItemStatus, name="inboxitemstatus"), nullable=False
    )

    # Who sent this (NULL for system-generated notifications)
    sender_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Scope — which workspace / project / channel this item concerns.
    # All SET NULL so items survive entity deletion.
    workspace_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True
    )
    project_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    channel_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("channels.id", ondelete="SET NULL"), nullable=True
    )

    # Role being offered (invites only; NULL for notifications)
    role: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Human-readable content shown in the inbox UI
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # For notifications: what entity triggered this (e.g. entity_type="project", entity_id="...")
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # Invites only; NULL for notifications
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )