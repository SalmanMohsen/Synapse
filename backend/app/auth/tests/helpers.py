"""
Test helpers for app.auth tests.

Kept as a plain importable module (not conftest) so tests can do:
    from app.auth.tests.helpers import make_user
without relying on pytest's sys.path injection of conftest.py.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock


def make_user(**overrides):
    """Return a User ORM-like object (MagicMock) with sensible defaults."""
    from app.auth.models import User

    user = MagicMock(spec=User)
    user.id = overrides.get("id", str(uuid.uuid4()))
    user.email = overrides.get("email", "alice@example.com")
    user.display_name = overrides.get("display_name", "Alice")
    user.hashed_password = overrides.get("hashed_password", None)
    user.github_user_id = overrides.get("github_user_id", None)
    user.google_user_id = overrides.get("google_user_id", None)
    user.avatar_url = overrides.get("avatar_url", None)
    user.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    return user