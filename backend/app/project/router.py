from fastapi import APIRouter, Depends, status

from app.auth.dependencies import get_current_user
from app.auth.models import User

from .dependencies import get_project_service
from .schemas import (
    ProjectCreate,
    ProjectMemberAdd,
    ProjectMemberRead,
    ProjectMemberUpdate,
    ProjectRead,
    ProjectUpdate,
)
from .service import ProjectService

# Workspace-scoped: create + list projects under a workspace
workspace_projects_router = APIRouter(
    prefix="/api/v1/workspaces",
    tags=["projects"],
)

# Project-scoped: operate on a specific project
projects_router = APIRouter(
    prefix="/api/v1/projects",
    tags=["projects"],
)


# ------------------------------------------------------------------ #
# Workspace-scoped endpoints                                           #
# ------------------------------------------------------------------ #


@workspace_projects_router.post(
    "/{workspace_id}/projects",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    workspace_id: str,
    data: ProjectCreate,
    current_user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
):
    return await service.create_project(workspace_id, current_user.id, data)


@workspace_projects_router.get(
    "/{workspace_id}/projects",
    response_model=list[ProjectRead],
)
async def list_projects(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
):
    return await service.list_projects(workspace_id, current_user.id)


# ------------------------------------------------------------------ #
# Project-scoped endpoints                                             #
# ------------------------------------------------------------------ #


@projects_router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
):
    return await service.get_project(project_id, current_user.id)


@projects_router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: str,
    data: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
):
    return await service.update_project(project_id, current_user.id, data)


@projects_router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
):
    await service.delete_project(project_id, current_user.id)


# ------------------------------------------------------------------ #
# Member management                                                    #
# ------------------------------------------------------------------ #


@projects_router.get(
    "/{project_id}/members",
    response_model=list[ProjectMemberRead],
)
async def list_members(
    project_id: str,
    current_user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
):
    return await service.list_members(project_id, current_user.id)


@projects_router.post(
    "/{project_id}/members",
    response_model=ProjectMemberRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    project_id: str,
    data: ProjectMemberAdd,
    current_user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
):
    return await service.add_member(project_id, current_user.id, data)


@projects_router.patch(
    "/{project_id}/members/{user_id}",
    response_model=ProjectMemberRead,
)
async def update_member_role(
    project_id: str,
    user_id: str,
    data: ProjectMemberUpdate,
    current_user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
):
    return await service.update_member_role(project_id, current_user.id, user_id, data)


@projects_router.delete(
    "/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    project_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
):
    await service.remove_member(project_id, current_user.id, user_id)