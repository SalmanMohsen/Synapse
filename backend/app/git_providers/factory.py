"""Selects the GitProvider implementation for a given provider string.

Adding GitLab or Azure DevOps later means writing one new adapter class,
adding one line to _PROVIDERS below, and adding that provider's own
webhook route in router.py (each vendor's webhook settings UI needs its
own URL to point at) -- GitIntegrationService itself doesn't change.
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