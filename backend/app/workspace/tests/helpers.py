"""
Test helpers for app.workspace tests.

Kept as a plain importable module (not conftest) so tests can do:
    from app.workspace.tests.helpers import make_workspace
without relying on pytest's sys.path injection of conftest.py.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.workspace.models import ProjectCreationPolicy, Workspace, WorkspaceMember


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