from fastapi import APIRouter, Depends, status

from app.auth.dependencies import get_current_user
from app.auth.models import User

from .dependencies import get_inbox_service
from .schemas import (
    InboxItemRead,
    SendChannelInvite,
    SendProjectInvite,
    SendWorkspaceInvite,
)
from .service import InboxService

# Personal inbox endpoints
inbox_router = APIRouter(prefix="/api/v1/inbox", tags=["inbox"])

# Invite-sending endpoints (scoped under the entities they target)
workspace_invite_router = APIRouter(prefix="/api/v1/workspaces", tags=["invites"])
project_invite_router = APIRouter(prefix="/api/v1/projects", tags=["invites"])
channel_invite_router = APIRouter(prefix="/api/v1/channels", tags=["invites"])


# ------------------------------------------------------------------ #
# Personal inbox                                                       #
# ------------------------------------------------------------------ #


@inbox_router.get("", response_model=list[InboxItemRead])
async def list_inbox(
    current_user: User = Depends(get_current_user),
    service: InboxService = Depends(get_inbox_service),
):
    """Return all inbox items (invites + notifications) for the authenticated user."""
    return await service.list_inbox(current_user.id)


@inbox_router.post(
    "/invites/{item_id}/accept",
    response_model=InboxItemRead,
)
async def accept_invite(
    item_id: str,
    current_user: User = Depends(get_current_user),
    service: InboxService = Depends(get_inbox_service),
):
    return await service.accept_invite(item_id, current_user.id)


@inbox_router.post(
    "/invites/{item_id}/decline",
    response_model=InboxItemRead,
)
async def decline_invite(
    item_id: str,
    current_user: User = Depends(get_current_user),
    service: InboxService = Depends(get_inbox_service),
):
    return await service.decline_invite(item_id, current_user.id)


@inbox_router.patch(
    "/{item_id}/read",
    response_model=InboxItemRead,
)
async def mark_read(
    item_id: str,
    current_user: User = Depends(get_current_user),
    service: InboxService = Depends(get_inbox_service),
):
    return await service.mark_read(item_id, current_user.id)


# ------------------------------------------------------------------ #
# Send invites                                                         #
# ------------------------------------------------------------------ #


@workspace_invite_router.post(
    "/{workspace_id}/invites",
    response_model=InboxItemRead,
    status_code=status.HTTP_201_CREATED,
)
async def send_workspace_invite(
    workspace_id: str,
    data: SendWorkspaceInvite,
    current_user: User = Depends(get_current_user),
    service: InboxService = Depends(get_inbox_service),
):
    return await service.send_workspace_invite(
        workspace_id, data.target_user_id, data.role, current_user.id
    )


@project_invite_router.post(
    "/{project_id}/invites",
    response_model=InboxItemRead,
    status_code=status.HTTP_201_CREATED,
)
async def send_project_invite(
    project_id: str,
    data: SendProjectInvite,
    current_user: User = Depends(get_current_user),
    service: InboxService = Depends(get_inbox_service),
):
    return await service.send_project_invite(
        project_id, data.target_user_id, data.role, current_user.id
    )


@channel_invite_router.post(
    "/{channel_id}/invites",
    response_model=InboxItemRead,
    status_code=status.HTTP_201_CREATED,
)
async def send_channel_invite(
    channel_id: str,
    data: SendChannelInvite,
    current_user: User = Depends(get_current_user),
    service: InboxService = Depends(get_inbox_service),
):
    return await service.send_channel_invite(
        channel_id, data.target_user_id, data.role, current_user.id
    )