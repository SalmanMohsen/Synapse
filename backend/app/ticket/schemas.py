from datetime import datetime

from pydantic import BaseModel, field_validator
from app.message.schemas import MessageListResponse
from app.thread_state.schemas import ThreadStateRead

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

class TicketRouteRequest(BaseModel):
    channel_id: str
 
 
class TicketSplitRequest(BaseModel):
    child_ticket_ids: list[str]
 
    @field_validator("child_ticket_ids")
    @classmethod
    def validate_child_tickets(cls, v: list[str]) -> list[str]:
        if len(v) < 2:
            raise ValueError("A split requires at least 2 child tickets.")
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

class TicketDetailResponse(BaseModel):
    """Composite response for GET /tickets/{ticket_id}.
 
    Returns the ticket, its latest page of messages (50, newest last), and
    the thread state if one exists.  Clients use GET /tickets/{id}/messages
    with a before_id cursor to page further back in history.
    """
 
    ticket: TicketRead
    messages: MessageListResponse
    thread_state: ThreadStateRead | None