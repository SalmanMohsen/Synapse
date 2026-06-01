from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from .models import InboxItemStatus, InboxItemType

# ------------------------------------------------------------------ #
# Read schema (returned for every inbox item)                          #
# ------------------------------------------------------------------ #


class InboxItemRead(BaseModel):
    id: str
    user_id: str
    type: InboxItemType
    status: InboxItemStatus
    sender_id: str | None
    workspace_id: str | None
    project_id: str | None
    channel_id: str | None
    role: str | None
    title: str
    body: str | None
    entity_type: str | None
    entity_id: str | None
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------ #
# Send-invite request bodies                                           #
# ------------------------------------------------------------------ #

WorkspaceInviteRole = Literal["member", "owner"]
ProjectInviteRole = Literal["team_lead", "member", "advisor", "viewer"]
ChannelInviteRole = Literal["channel_lead", "member"]


class SendWorkspaceInvite(BaseModel):
    """Body for POST /workspaces/{workspace_id}/invites"""

    target_user_id: str
    role: WorkspaceInviteRole = "member"


class SendProjectInvite(BaseModel):
    """Body for POST /projects/{project_id}/invites"""

    target_user_id: str
    role: ProjectInviteRole = "member"


class SendChannelInvite(BaseModel):
    """Body for POST /channels/{channel_id}/invites"""

    target_user_id: str
    role: ChannelInviteRole = "member"