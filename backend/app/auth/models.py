import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # nullable — only set for email/password users
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # nullable — set when the user connects via OAuth
    github_user_id: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True, index=True
    )
    google_user_id: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True, index=True
    )
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )