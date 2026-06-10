from datetime import datetime

from pydantic import BaseModel, field_validator

from .models import TicketPriority, TicketSource, TicketStatus


class TicketCreate(BaseModel):
    title: str
    description: str | None = None
    priority: TicketPriority = TicketPriority.medium

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 1:
            raise ValueError("Title must not be empty.")
        if len(v) > 500:
            raise ValueError("Title must be at most 500 characters.")
        return v


class TicketUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: TicketPriority | None = None

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if len(v) < 1:
            raise ValueError("Title must not be empty.")
        if len(v) > 500:
            raise ValueError("Title must be at most 500 characters.")
        return v


class TicketRead(BaseModel):
    id: str
    channel_id: str
    title: str
    description: str | None
    status: TicketStatus
    source: TicketSource
    priority: TicketPriority
    creator_id: str | None
    github_issue_number: int | None
    github_author_login: str | None
    github_pr_number: int | None
    parent_ticket_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}