"""Git-hosting-vendor adapters (GitProvider) and the factory that selects
one per provider string. See base.py for the interface and the rationale."""

from app.git_providers.base import GitProvider, InstallationRepo, NormalizedGitEvent
from app.git_providers.factory import get_git_provider

__all__ = ["GitProvider", "InstallationRepo", "NormalizedGitEvent", "get_git_provider"]