from fastapi import APIRouter, Depends, Query, status

from app.auth.dependencies import get_current_user
from app.auth.models import User

from .dependencies import get_message_service
from .schemas import MessageCreate, MessageListResponse, MessageRead, MessageUpdate
from .service import MessageService

messages_router = APIRouter(
    prefix="/api/v1/tickets",
    tags=["messages"],
)


@messages_router.post(
    "/{ticket_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_message(
    ticket_id: str,
    data: MessageCreate,
    current_user: User = Depends(get_current_user),
    service: MessageService = Depends(get_message_service),
) -> MessageRead:
    return await service.create_message(ticket_id, current_user.id, data)


@messages_router.get(
    "/{ticket_id}/messages",
    response_model=MessageListResponse,
)
async def list_messages(
    ticket_id: str,
    before_id: str | None = Query(default=None, description="Cursor — ID of the oldest message in the previous page"),
    current_user: User = Depends(get_current_user),
    service: MessageService = Depends(get_message_service),
) -> MessageListResponse:
    return await service.list_messages(ticket_id, current_user.id, before_id=before_id)


@messages_router.patch(
    "/{ticket_id}/messages/{message_id}",
    response_model=MessageRead,
)
async def edit_message(
    ticket_id: str,
    message_id: str,
    data: MessageUpdate,
    current_user: User = Depends(get_current_user),
    service: MessageService = Depends(get_message_service),
) -> MessageRead:
    return await service.edit_message(ticket_id, message_id, current_user.id, data)


@messages_router.delete(
    "/{ticket_id}/messages/{message_id}",
    response_model=MessageRead,
    summary="Soft-delete a message — content is preserved in the DB but masked in API responses",
)
async def delete_message(
    ticket_id: str,
    message_id: str,
    current_user: User = Depends(get_current_user),
    service: MessageService = Depends(get_message_service),
) -> MessageRead:
    return await service.delete_message(ticket_id, message_id, current_user.id)