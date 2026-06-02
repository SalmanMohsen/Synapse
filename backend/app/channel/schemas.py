from datetime import datetime

from pydantic import BaseModel, field_validator

from app.auth.schemas import UserRead

from .models import ApprovalPolicy, ChannelDiscipline, ChannelMemberRole


# ------------------------------------------------------------------ #
# Channel                                                              #
# ------------------------------------------------------------------ #


class ChannelCreate(BaseModel):
    name: str
    discipline: ChannelDiscipline
    approval_policy: ApprovalPolicy = ApprovalPolicy.lead_only

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Channel name must be at least 2 characters")
        if len(v) > 100:
            raise ValueError("Channel name must be at most 100 characters")
        return v


class ChannelUpdate(BaseModel):
    name: str | None = None
    approval_policy: ApprovalPolicy | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Channel name must be at least 2 characters")
        if len(v) > 100:
            raise ValueError("Channel name must be at most 100 characters")
        return v


class ChannelRead(BaseModel):
    id: str
    project_id: str
    name: str
    discipline: ChannelDiscipline | None
    is_leads_channel: bool
    approval_policy: ApprovalPolicy
    created_at: datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------ #
# ChannelMember                                                        #
# ------------------------------------------------------------------ #


class ChannelMemberAdd(BaseModel):
    user_id: str
    role: ChannelMemberRole = ChannelMemberRole.member


class ChannelMemberUpdate(BaseModel):
    role: ChannelMemberRole


class ChannelMemberRead(BaseModel):
    id: str
    channel_id: str
    user_id: str
    role: ChannelMemberRole
    joined_at: datetime
    user: UserRead | None = None
    model_config = {"from_attributes": True}