from datetime import datetime

from pydantic import BaseModel, field_validator

from app.auth.schemas import UserRead

from .models import ProjectRole


# ------------------------------------------------------------------ #
# Project                                                              #
# ------------------------------------------------------------------ #


class ProjectCreate(BaseModel):
    name: str
    github_app_installation_id: str | None = None
    default_branch: str = "main"

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Project name must be at least 2 characters")
        if len(v) > 100:
            raise ValueError("Project name must be at most 100 characters")
        return v

    @field_validator("default_branch")
    @classmethod
    def branch_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Default branch cannot be empty")
        return v


class ProjectUpdate(BaseModel):
    name: str | None = None
    default_branch: str | None = None
    github_app_installation_id: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Project name must be at least 2 characters")
        if len(v) > 100:
            raise ValueError("Project name must be at most 100 characters")
        return v

    @field_validator("default_branch")
    @classmethod
    def branch_not_empty(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Default branch cannot be empty")
        return v


class ProjectRead(BaseModel):
    id: str
    workspace_id: str
    name: str
    github_app_installation_id: str | None
    default_branch: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------ #
# ProjectMember                                                        #
# ------------------------------------------------------------------ #


class ProjectMemberAdd(BaseModel):
    """Body for adding a workspace member to a project."""

    user_id: str
    role: ProjectRole = ProjectRole.member


class ProjectMemberUpdate(BaseModel):
    role: ProjectRole


class ProjectMemberRead(BaseModel):
    id: str
    project_id: str
    user_id: str
    role: ProjectRole
    joined_at: datetime
    user: UserRead | None = None
    model_config = {"from_attributes": True}