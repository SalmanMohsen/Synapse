from datetime import datetime

from pydantic import BaseModel, field_validator

from .models import ProjectCreationPolicy


# ------------------------------------------------------------------ #
# Workspace                                                           #
# ------------------------------------------------------------------ #


class WorkspaceCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Workspace name must be at least 2 characters")
        if len(v) > 100:
            raise ValueError("Workspace name must be at most 100 characters")
        return v


class WorkspaceUpdate(BaseModel):
    name: str | None = None
    project_creation_policy: ProjectCreationPolicy | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Workspace name must be at least 2 characters")
        if len(v) > 100:
            raise ValueError("Workspace name must be at most 100 characters")
        return v


class WorkspaceRead(BaseModel):
    id: str
    name: str
    project_creation_policy: ProjectCreationPolicy
    created_at: datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------ #
# WorkspaceMember                                                     #
# ------------------------------------------------------------------ #


class WorkspaceMemberRead(BaseModel):
    id: str
    workspace_id: str
    user_id: str
    is_owner: bool
    joined_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceMemberUpdate(BaseModel):
    is_owner: bool