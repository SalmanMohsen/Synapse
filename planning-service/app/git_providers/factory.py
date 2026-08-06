"""Selects the GitProvider implementation for a given integration.

Adding GitLab or Azure DevOps later means writing one new adapter class
and adding one line to _PROVIDERS below.
"""

from app.git_providers.base import GitProvider
from app.git_providers.github import GitHubProvider

_PROVIDERS: dict[str, GitProvider] = {
    "github": GitHubProvider(),
    # "gitlab": GitLabProvider(),
    # "azure_devops": AzureDevOpsProvider(),
}


def get_git_provider(provider: str) -> GitProvider:
    try:
        return _PROVIDERS[provider]
    except KeyError:
        raise ValueError(
            f"No GitProvider registered for '{provider}'. "
            f"Registered: {sorted(_PROVIDERS)}"
        )