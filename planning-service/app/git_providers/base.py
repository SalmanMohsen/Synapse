"""GitProvider interface for planning-service.

Narrower than code-service's version of the same interface: ingestion only
ever needs to authenticate and clone (read-only, for RAG indexing) -- it
never opens a pull/merge request, so that method isn't here. Keeping the
two interfaces separately scoped per service, rather than sharing one
"one true GitProvider" across services, is deliberate: this service has no
business being able to open a PR even by accident, and there's no shared
package between the two services to import from anyway (separate
deployables, separate requirements.txt).
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GitIntegrationRef:
    provider: str
    external_ref: str
    repo_full_name: str


class GitProvider(Protocol):
    async def get_access_token(self, integration: GitIntegrationRef) -> str:
        """Short-lived token authorized to clone this repo."""
        ...

    def build_authenticated_clone_url(self, integration: GitIntegrationRef, token: str) -> str:
        """Clone URL with the token embedded, ready for `git clone`."""
        ...