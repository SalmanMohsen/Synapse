"""
Test helpers for app.channel tests.

Kept as a plain importable module (not conftest) so tests can do:
    from app.channel.tests.helpers import make_channel, make_channel_member
without relying on pytest's sys.path injection of conftest.py.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.channel.models import (
    ApprovalPolicy,
    Channel,
    ChannelDiscipline,
    ChannelMember,
    ChannelMemberRole,
)


def make_channel(**overrides) -> MagicMock:
    """Return a Channel ORM-like object with sensible defaults."""
    channel = MagicMock(spec=Channel)
    channel.id = overrides.get("id", str(uuid.uuid4()))
    channel.project_id = overrides.get("project_id", str(uuid.uuid4()))
    channel.name = overrides.get("name", "backend")
    channel.discipline = overrides.get("discipline", ChannelDiscipline.backend)
    channel.is_leads_channel = overrides.get("is_leads_channel", False)
    channel.approval_policy = overrides.get("approval_policy", ApprovalPolicy.lead_only)
    channel.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    channel.updated_at = overrides.get("updated_at", datetime.now(timezone.utc))
    return channel


def make_channel_member(**overrides) -> MagicMock:
    """Return a ChannelMember ORM-like object with sensible defaults."""
    member = MagicMock(spec=ChannelMember)
    member.id = overrides.get("id", str(uuid.uuid4()))
    member.channel_id = overrides.get("channel_id", str(uuid.uuid4()))
    member.user_id = overrides.get("user_id", str(uuid.uuid4()))
    member.role = overrides.get("role", ChannelMemberRole.member)
    member.joined_at = overrides.get("joined_at", datetime.now(timezone.utc))
    return member