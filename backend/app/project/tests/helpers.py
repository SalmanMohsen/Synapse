import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.project.models import Project, ProjectMember

def make_project(**overrides) -> MagicMock:
    """Return a Project ORM-like object with sensible defaults."""
    project = MagicMock(spec=Project)
    project.id = overrides.get("id", str(uuid.uuid4()))
    project.workspace_id = overrides.get("workspace_id", str(uuid.uuid4()))
    project.name = overrides.get("name", "Test Project")
    project.github_app_installation_id = overrides.get(
        "github_app_installation_id", None
    )
    project.default_branch = overrides.get("default_branch", "main")
    project.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    project.updated_at = overrides.get("updated_at", datetime.now(timezone.utc))
    return project

def make_project_member(**overrides) -> MagicMock:
    """Return a ProjectMember ORM-like object with sensible defaults."""
    member = MagicMock(spec=ProjectMember)
    member.id = overrides.get("id", str(uuid.uuid4()))
    member.project_id = overrides.get("project_id", str(uuid.uuid4()))
    member.user_id = overrides.get("user_id", str(uuid.uuid4()))
    return member