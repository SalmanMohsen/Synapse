"""GitProvider interface: the seam every git-hosting-vendor call goes
through, instead of calling GitHub's (or later GitLab's / Azure DevOps's)
API directly from runner.py.

Adding a second or third provider means writing one new class that
implements GitProvider and registering it in factory.py. Nothing in
runner.py, the step loop, or PR-creation logic needs to change -- that's
the whole point of putting the seam here.

Plain `git` operations (clone/branch/commit/push in app.git.operations) are
NOT part of this interface. They're already vendor-agnostic -- they're just
`git` CLI calls against a URL, and that works identically no matter who
hosts the remote. Only the three things that differ per vendor are here:
getting a token, building an authenticated clone URL, and opening a
pull/merge request through that vendor's API.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GitIntegrationRef:
    """Whatever a provider needs to act on one repo.

    `external_ref` is deliberately generic: today it's always a GitHub App
    installation id, but it's named generically because a GitLab adapter
    would put a group/project access token id there, and an Azure DevOps
    adapter would put an org/project reference there -- each adapter
    interprets it its own way, callers never need to know which.
    """

    provider: str
    external_ref: str
    repo_full_name: str


class GitProvider(Protocol):
    async def get_access_token(self, integration: GitIntegrationRef) -> str:
        """Short-lived token authorized to act on this repo. Never stored by
        the caller -- fetched fresh at job time (platform-wide rule)."""
        ...

    def build_authenticated_clone_url(self, integration: GitIntegrationRef, token: str) -> str:
        """Clone URL with the token embedded, ready for `git clone`."""
        ...

    async def open_pull_request(
        self,
        integration: GitIntegrationRef,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> dict:
        """Opens the change request (pull request on GitHub/Azure DevOps,
        merge request on GitLab) and returns the created object's payload.
        Callers only ever read `number`/`html_url`-shaped fields off the
        result -- if a future adapter's payload uses different field names,
        normalize them here, not at the call site."""
        ...