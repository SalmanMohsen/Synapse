from fastapi import APIRouter, Depends, status

from app.auth.models import User

from .dependencies import get_current_user, get_workspace_service
from .schemas import (
    WorkspaceMemberRead,
    WorkspaceCreate,
    WorkspaceRead,
    WorkspaceUpdate,
)
from .service import WorkspaceService

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


# ------------------------------------------------------------------ #
# Workspace CRUD                                                       #
# ------------------------------------------------------------------ #


@router.post("", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    data: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    return await service.create_workspace(current_user.id, data)


@router.get("/{workspace_id}", response_model=WorkspaceRead)
async def get_workspace(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    return await service.get_workspace(workspace_id, current_user.id)


@router.patch("/{workspace_id}", response_model=WorkspaceRead)
async def update_workspace(
    workspace_id: str,
    data: WorkspaceUpdate,
    current_user: User = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    return await service.update_workspace(workspace_id, data, current_user.id)

@router.get("", response_model=list[WorkspaceRead])
async def list_workspaces(
    current_user: User = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    return await service.list_workspaces(current_user.id)

@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    await service.delete_workspace(workspace_id, current_user.id)


# ------------------------------------------------------------------ #
# Member management                                                    #
# ------------------------------------------------------------------ #


@router.get("/{workspace_id}/members", response_model=list[WorkspaceMemberRead])
async def list_members(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    return await service.list_members(workspace_id, current_user.id)


@router.post(
    "/{workspace_id}/members/{user_id}/promote",
    response_model=WorkspaceMemberRead,
)
async def add_owner(
    workspace_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    return await service.add_owner(workspace_id, user_id, current_user.id)


@router.delete(
    "/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_member(
    workspace_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service),
):
    await service.remove_member(workspace_id, user_id, current_user.id)