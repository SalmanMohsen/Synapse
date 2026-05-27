from fastapi import APIRouter, Depends, status

from app.auth.dependencies import get_current_user
from app.auth.models import User

from .dependencies import get_channel_service
from .schemas import (
    ChannelCreate,
    ChannelMemberAdd,
    ChannelMemberRead,
    ChannelMemberUpdate,
    ChannelRead,
    ChannelUpdate,
)
from .service import ChannelService

# Project-scoped: create + list channels under a project
project_channels_router = APIRouter(
    prefix="/api/v1/projects",
    tags=["channels"],
)

# Channel-scoped: operate on a specific channel
channels_router = APIRouter(
    prefix="/api/v1/channels",
    tags=["channels"],
)


# ------------------------------------------------------------------ #
# Project-scoped endpoints                                             #
# ------------------------------------------------------------------ #


@project_channels_router.post(
    "/{project_id}/channels",
    response_model=ChannelRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_channel(
    project_id: str,
    data: ChannelCreate,
    current_user: User = Depends(get_current_user),
    service: ChannelService = Depends(get_channel_service),
):
    return await service.create_channel(project_id, current_user.id, data)


@project_channels_router.post(
    "/{project_id}/leads-channel",
    response_model=ChannelRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_leads_channel(
    project_id: str,
    current_user: User = Depends(get_current_user),
    service: ChannelService = Depends(get_channel_service),
):
    return await service.create_leads_channel(project_id, current_user.id)


@project_channels_router.get(
    "/{project_id}/channels",
    response_model=list[ChannelRead],
)
async def list_channels(
    project_id: str,
    current_user: User = Depends(get_current_user),
    service: ChannelService = Depends(get_channel_service),
):
    return await service.list_channels(project_id, current_user.id)


# ------------------------------------------------------------------ #
# Channel-scoped endpoints                                             #
# ------------------------------------------------------------------ #


@channels_router.get("/{channel_id}", response_model=ChannelRead)
async def get_channel(
    channel_id: str,
    current_user: User = Depends(get_current_user),
    service: ChannelService = Depends(get_channel_service),
):
    return await service.get_channel(channel_id, current_user.id)


@channels_router.patch("/{channel_id}", response_model=ChannelRead)
async def update_channel(
    channel_id: str,
    data: ChannelUpdate,
    current_user: User = Depends(get_current_user),
    service: ChannelService = Depends(get_channel_service),
):
    return await service.update_channel(channel_id, current_user.id, data)


@channels_router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: str,
    current_user: User = Depends(get_current_user),
    service: ChannelService = Depends(get_channel_service),
):
    await service.delete_channel(channel_id, current_user.id)


# ------------------------------------------------------------------ #
# Member management                                                    #
# ------------------------------------------------------------------ #


@channels_router.get(
    "/{channel_id}/members",
    response_model=list[ChannelMemberRead],
)
async def list_members(
    channel_id: str,
    current_user: User = Depends(get_current_user),
    service: ChannelService = Depends(get_channel_service),
):
    return await service.list_members(channel_id, current_user.id)


@channels_router.post(
    "/{channel_id}/members",
    response_model=ChannelMemberRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    channel_id: str,
    data: ChannelMemberAdd,
    current_user: User = Depends(get_current_user),
    service: ChannelService = Depends(get_channel_service),
):
    return await service.add_member(channel_id, current_user.id, data)


@channels_router.patch(
    "/{channel_id}/members/{user_id}",
    response_model=ChannelMemberRead,
)
async def update_member_role(
    channel_id: str,
    user_id: str,
    data: ChannelMemberUpdate,
    current_user: User = Depends(get_current_user),
    service: ChannelService = Depends(get_channel_service),
):
    return await service.update_member_role(channel_id, current_user.id, user_id, data)


@channels_router.delete(
    "/{channel_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    channel_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
    service: ChannelService = Depends(get_channel_service),
):
    await service.remove_member(channel_id, current_user.id, user_id)