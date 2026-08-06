"""Git-hosting-vendor adapters (GitProvider) and the factory that selects
one per integration. See base.py for the interface and the rationale."""

from app.git_providers.base import GitIntegrationRef, GitProvider
from app.git_providers.factory import get_git_provider

__all__ = ["GitIntegrationRef", "GitProvider", "get_git_provider"]