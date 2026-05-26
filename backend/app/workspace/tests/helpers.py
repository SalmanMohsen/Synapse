"""
Test helpers for app.workspace tests.

Kept as a plain importable module (not conftest) so tests can do:
    from app.workspace.tests.helpers import make_workspace
without relying on pytest's sys.path injection of conftest.py.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.workspace.models import ProjectCreationPolicy, Workspace, WorkspaceInvite, WorkspaceMember


def make_workspace(**overrides) -> MagicMock:
    """Return a Workspace ORM-like object with sensible defaults."""
    ws = MagicMock(spec=Workspace)
    ws.id = overrides.get("id", str(uuid.uuid4()))
    ws.name = overrides.get("name", "Test Workspace")
    ws.project_creation_policy = overrides.get(
        "project_creation_policy", ProjectCreationPolicy.restricted
    )
    ws.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    ws.updated_at = overrides.get("updated_at", datetime.now(timezone.utc))
    return ws


def make_workspace_member(**overrides) -> MagicMock:
    """Return a WorkspaceMember ORM-like object with sensible defaults."""
    member = MagicMock(spec=WorkspaceMember)
    member.id = overrides.get("id", str(uuid.uuid4()))
    member.workspace_id = overrides.get("workspace_id", str(uuid.uuid4()))
    member.user_id = overrides.get("user_id", str(uuid.uuid4()))
    member.is_owner = overrides.get("is_owner", False)
    member.joined_at = overrides.get("joined_at", datetime.now(timezone.utc))
    return member


def make_workspace_invite(**overrides) -> MagicMock:
    """Return a WorkspaceInvite ORM-like object with sensible defaults."""
    invite = MagicMock(spec=WorkspaceInvite)
    invite.id = overrides.get("id", str(uuid.uuid4()))
    invite.token = overrides.get("token", "test-token-" + str(uuid.uuid4()))
    invite.workspace_id = overrides.get("workspace_id", str(uuid.uuid4()))
    invite.project_id = overrides.get("project_id", None)
    invite.channel_id = overrides.get("channel_id", None)
    invite.role = overrides.get("role", "member")
    invite.invited_by = overrides.get("invited_by", None)
    invite.expires_at = overrides.get(
        "expires_at", datetime.now(timezone.utc) + timedelta(days=30)
    )
    invite.used_at = overrides.get("used_at", None)
    invite.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    return invite