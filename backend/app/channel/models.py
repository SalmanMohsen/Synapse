import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ChannelDiscipline(str, PyEnum):
    frontend = "frontend"
    backend = "backend"
    database = "database"
    devops = "devops"
    infrastructure = "infrastructure"
    mobile = "mobile"
    security = "security"
    qa_testing = "qa_testing"
    data_engineering = "data_engineering"
    ai_ml = "ai_ml"
    blockchain = "blockchain"
    embedded = "embedded"
    desktop = "desktop"
    platform_sdk = "platform_sdk"
    technical_writing = "technical_writing"


class ApprovalPolicy(str, PyEnum):
    lead_only = "lead_only"
    any_member = "any_member"


class ChannelMemberRole(str, PyEnum):
    channel_lead = "channel_lead"
    member = "member"


class Channel(Base):
    __tablename__ = "channels"
    # Prevents two regular channels with the same discipline in one project.
    # PostgreSQL treats NULLs as distinct in unique constraints, so the
    # leads channel (discipline=NULL) does not trigger this constraint.
    # One-leads-channel-per-project is enforced at the service layer.
    __table_args__ = (
        UniqueConstraint(
            "project_id", "discipline", name="uq_channels_project_discipline"
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # NULL for the auto-created leads channel; set for all discipline channels.
    discipline: Mapped[ChannelDiscipline | None] = mapped_column(
        Enum(ChannelDiscipline, name="channeldiscipline"), nullable=True
    )
    is_leads_channel: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # Set at creation by the Team Lead; applies to all tickets in this channel.
    approval_policy: Mapped[ApprovalPolicy] = mapped_column(
        Enum(ApprovalPolicy, name="approvalpolicy"),
        nullable=False,
        default=ApprovalPolicy.lead_only,
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

    members: Mapped[list["ChannelMember"]] = relationship(
        "ChannelMember", back_populates="channel", cascade="all, delete-orphan"
    )


class ChannelMember(Base):
    __tablename__ = "channel_members"
    __table_args__ = (
        UniqueConstraint(
            "channel_id", "user_id", name="uq_channel_members_channel_user"
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    channel_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[ChannelMemberRole] = mapped_column(
        Enum(ChannelMemberRole, name="channelmemberrole"), nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    channel: Mapped["Channel"] = relationship("Channel", back_populates="members")