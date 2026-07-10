import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import Enum, ForeignKey, String, Text, UniqueConstraint, func, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.channel.models import ChannelDiscipline

class SkillDimension(str, PyEnum):
    specialty = "specialty"
    technology = "technology"

class SkillFile(Base):
    __tablename__ = "skill_files"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "dimension", "discipline", 
            name="uq_skill_files_workspace_dimension_discipline"
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(
        String, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    dimension: Mapped[SkillDimension] = mapped_column(
        Enum(SkillDimension, name="skilldimension"), nullable=False
    )
    discipline: Mapped[ChannelDiscipline | None] = mapped_column(
        Enum(ChannelDiscipline, name="channeldiscipline"), nullable=True
    )
    file_content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

class SkillAssignment(Base):
    __tablename__ = "skill_assignments"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    channel_id: Mapped[str] = mapped_column(
        String, ForeignKey("channels.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    specialty_file_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("skill_files.id", ondelete="SET NULL"), nullable=True
    )
    technology_file_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("skill_files.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )