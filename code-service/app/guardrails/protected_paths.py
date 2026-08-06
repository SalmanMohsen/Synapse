"""Protected-path guardrail: flags any step that touches migration or
CI/CD config paths for mandatory human review (Guardrail 1, build plan).

Unlike the other two guardrails, this one never requests an abort or
touches the sandbox -- it only flags the step record. Promoted out of
runner.py's protected_path_subscriber closure, plus the two path-predicate
helpers it used (is_migration_path, is_protected_ci_path), which weren't
used anywhere else in runner.py.
"""

import asyncio
import logging

from app.guardrails.context import RunContext
from app.openhands.events import AgentEvent
from app.steps import flag_requires_human_review

logger = logging.getLogger(__name__)


def is_migration_path(path: str) -> bool:
    """Checks if a file path belongs to migrations or alembic directories."""
    normalized = path.replace("\\", "/").lower()
    parts = normalized.split("/")
    return "migrations" in parts or "alembic" in parts


def is_protected_ci_path(path: str) -> bool:
    """Checks if a file path belongs to CI/CD workflow or pipeline config.

    Added to the same protected list as migrations (Guardrail 1, build
    plan): a prompt injection that isn't neutralized by the untrusted-
    context boundary should still not be able to reach outside the
    ticket's actual scope by rewriting the pipeline that would otherwise
    catch it (e.g. disabling tests in CI).
    """
    normalized = path.replace("\\", "/").lower()
    parts = normalized.split("/")

    for i in range(len(parts) - 1):
        if parts[i] == ".github" and parts[i + 1] == "workflows":
            return True

    if "circleci" in parts or ".circleci" in parts:
        return True

    protected_ci_filenames = {
        ".gitlab-ci.yml",
        ".gitlab-ci.yaml",
        "azure-pipelines.yml",
        "jenkinsfile",
        ".travis.yml",
    }
    return bool(parts) and parts[-1] in protected_ci_filenames


class ProtectedPathSubscriber:
    def __init__(self, ctx: RunContext):
        self._ctx = ctx

    def handle(self, event: AgentEvent) -> None:
        ctx = self._ctx
        if not (event.touched_paths and ctx.current_step_record_id):
            return

        has_protected_touch = any(
            is_migration_path(fp) or is_protected_ci_path(fp)
            for fp in event.touched_paths
        )
        if has_protected_touch:
            logger.warning(
                "Protected path touched (migration or CI/CD config): %s. Flagging step %s.",
                event.touched_paths,
                ctx.current_step_record_id,
            )
            asyncio.run_coroutine_threadsafe(
                flag_requires_human_review(ctx.current_step_record_id),
                ctx.main_loop,
            )