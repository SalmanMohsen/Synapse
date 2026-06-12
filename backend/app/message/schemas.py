from datetime import datetime

from pydantic import BaseModel, field_validator

from .models import MessageType


class AuthorRead(BaseModel):
    id: str
    display_name: str
    avatar_url: str | None

    model_config = {"from_attributes": True}


class MessageCreate(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Content must not be empty.")
        return v


class MessageUpdate(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Content must not be empty.")
        return v


class MessageRead(BaseModel):
    id: str
    ticket_id: str
    author_id: str | None
    # Embedded author; null for system messages and when author account
    # has been deleted (author_id SET NULL on users.id delete).
    author: AuthorRead | None
    # Null when message has been soft-deleted — content is preserved in DB
    # but masked at the API boundary.
    content: str | None
    type: MessageType
    metadata_json: dict | None
    deleted_at: datetime | None
    edited_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MessageListResponse(BaseModel):
    items: list[MessageRead]
    has_more: bool
    # ID of the oldest message in this page — pass as before_id to fetch
    # the next (older) page.  Null when there are no more pages.
    next_cursor: str | None