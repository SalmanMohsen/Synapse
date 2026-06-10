from fastapi import APIRouter, Depends, status

from app.auth.dependencies import get_current_user
from app.auth.models import User

from .dependencies import get_ticket_service
from .schemas import TicketCreate, TicketRead, TicketUpdate
from .service import TicketService

# Channel-scoped: create + list tickets for a channel
channel_tickets_router = APIRouter(
    prefix="/api/v1/channels",
    tags=["tickets"],
)

# Ticket-scoped: operate on a specific ticket
tickets_router = APIRouter(
    prefix="/api/v1/tickets",
    tags=["tickets"],
)


# ------------------------------------------------------------------ #
# Channel-scoped endpoints                                             #
# ------------------------------------------------------------------ #


@channel_tickets_router.post(
    "/{channel_id}/tickets",
    response_model=TicketRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_ticket(
    channel_id: str,
    data: TicketCreate,
    current_user: User = Depends(get_current_user),
    service: TicketService = Depends(get_ticket_service),
):
    return await service.create_ticket(channel_id, current_user.id, data)


@channel_tickets_router.get(
    "/{channel_id}/tickets",
    response_model=list[TicketRead],
)
async def list_tickets(
    channel_id: str,
    current_user: User = Depends(get_current_user),
    service: TicketService = Depends(get_ticket_service),
):
    return await service.list_tickets(channel_id, current_user.id)


# ------------------------------------------------------------------ #
# Ticket-scoped endpoints                                              #
# ------------------------------------------------------------------ #


@tickets_router.get("/{ticket_id}", response_model=TicketRead)
async def get_ticket(
    ticket_id: str,
    current_user: User = Depends(get_current_user),
    service: TicketService = Depends(get_ticket_service),
):
    return await service.get_ticket(ticket_id, current_user.id)


@tickets_router.patch("/{ticket_id}", response_model=TicketRead)
async def update_ticket(
    ticket_id: str,
    data: TicketUpdate,
    current_user: User = Depends(get_current_user),
    service: TicketService = Depends(get_ticket_service),
):
    return await service.update_ticket(ticket_id, current_user.id, data)