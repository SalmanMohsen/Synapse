"""Git operations for the code agent (build plan Steps 3 & 14).

These run on the controller side against the per-run working clone under
REPO_WORK_ROOT. That directory is the same one bind-mounted into the sandbox,
so edits the agent makes inside the sandbox are visible here for commit/push.

Locked rules enforced here:
- Branch: ai/ticket-{id}-{slug}. Checked out if it exists, created otherwise.
- Commit + push after every completed step (never batched to the end).
- NEVER force-push. A rejected (non-fast-forward) push escalates immediately
  with diff diagnostics attached — no auto pull-merge-retry.
"""

import asyncio
import logging
import os
import re

from app.config import (
    BRANCH_PREFIX,
    GIT_AUTHOR_EMAIL,
    GIT_AUTHOR_NAME,
    REPO_WORK_ROOT,
)

logger = logging.getLogger(__name__)


class GitCommandError(RuntimeError):
    def __init__(self, message: str, stdout: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


class PushRejectedError(GitCommandError):
    """Non-fast-forward push rejection — escalates (never auto-resolved)."""


async def _run_git(*args: str, cwd: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_b, stderr_b = await proc.communicate()
    stdout, stderr = stdout_b.decode(), stderr_b.decode()
    if proc.returncode != 0:
        raise GitCommandError(
            f"git {' '.join(args)} failed in {cwd}: {stderr.strip()}",
            stdout=stdout,
            stderr=stderr,
        )
    return stdout


def _slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].strip("-") or "ticket"


def branch_name(ticket_id: str, ticket_title: str) -> str:
    """ai/ticket-{id}-{slug}."""
    return f"{BRANCH_PREFIX}-{ticket_id}-{_slugify(ticket_title)}"


def work_repo_path(agent_run_id: str) -> str:
    """Per-run working clone path (host-side; bind-mounted into the sandbox)."""
    return os.path.join(REPO_WORK_ROOT, agent_run_id)


async def clone_and_checkout(
    agent_run_id: str,
    clone_url: str,
    ticket_id: str,
    ticket_title: str,
    default_branch: str,
) -> tuple[str, str]:
    """Fresh clone for the run, then checkout/create the ticket branch.

    A re-triggered AgentRun gets a fresh clone but checks out the SAME existing
    branch (so per-step pushes from a prior crashed attempt are picked up).
    Returns (repo_path, branch).
    """
    repo_path = work_repo_path(agent_run_id)
    branch = branch_name(ticket_id, ticket_title)

    # Always start from a clean clone for the run (checkpoint resume relies on
    # the remote branch, not a surviving local dir).
    if os.path.isdir(repo_path):
        await _run_git("clean", "-fdx", cwd=repo_path) if os.path.isdir(
            os.path.join(repo_path, ".git")
        ) else None
        import shutil

        shutil.rmtree(repo_path, ignore_errors=True)

    os.makedirs(REPO_WORK_ROOT, exist_ok=True)
    await _run_git("clone", clone_url, repo_path, cwd=REPO_WORK_ROOT)

    await configure_identity(repo_path)

    # Does the branch already exist on the remote?
    remote_refs = await _run_git("ls-remote", "--heads", "origin", branch, cwd=repo_path)
    if remote_refs.strip():
        await _run_git("fetch", "origin", branch, cwd=repo_path)
        await _run_git("checkout", branch, cwd=repo_path)
        logger.info("Checked out existing branch %s", branch)
    else:
        await _run_git("checkout", "-b", branch, default_branch, cwd=repo_path)
        logger.info("Created new branch %s from %s", branch, default_branch)

    return repo_path, branch


async def configure_identity(repo_path: str) -> None:
    await _run_git("config", "user.name", GIT_AUTHOR_NAME, cwd=repo_path)
    await _run_git("config", "user.email", GIT_AUTHOR_EMAIL, cwd=repo_path)


async def checkout_commit(repo_path: str, commit_sha: str) -> None:
    """Reset the working tree to a specific commit (checkpoint resume, Step 13)."""
    await _run_git("checkout", commit_sha, cwd=repo_path)


async def current_head(repo_path: str) -> str:
    return (await _run_git("rev-parse", "HEAD", cwd=repo_path)).strip()


async def has_changes(repo_path: str) -> bool:
    out = await _run_git("status", "--porcelain", cwd=repo_path)
    return bool(out.strip())


async def changed_files(repo_path: str) -> list[str]:
    """Files changed in the working tree (staged + unstaged), porcelain-parsed."""
    out = await _run_git("status", "--porcelain", cwd=repo_path)
    files: list[str] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        # Format: "XY path" (or "XY old -> new" for renames).
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(path.strip())
    return files


async def commit_all(repo_path: str, message: str) -> str:
    """Stage everything and commit. Returns the new commit SHA."""
    await _run_git("add", "-A", cwd=repo_path)
    await _run_git("commit", "-m", message, cwd=repo_path)
    return await current_head(repo_path)


async def push(repo_path: str, branch: str) -> None:
    """Push the branch to origin. NEVER force. Escalates on rejection.

    On non-fast-forward rejection we attach diff diagnostics
    (`git log branch..origin/branch`) and raise PushRejectedError — the caller
    routes this to the blocked escalation path. We do NOT auto pull-merge-retry:
    something unexpected touched an agent-owned branch and that needs human
    judgement, not silent reconciliation.
    """
    try:
        await _run_git("push", "origin", branch, cwd=repo_path)
    except GitCommandError as exc:
        lowered = (exc.stderr or "").lower()
        if "non-fast-forward" in lowered or "rejected" in lowered or "fetch first" in lowered:
            diagnostics = ""
            try:
                await _run_git("fetch", "origin", branch, cwd=repo_path)
                diagnostics = await _run_git(
                    "log", "--oneline", f"{branch}..origin/{branch}", cwd=repo_path
                )
            except GitCommandError:
                diagnostics = "(could not compute divergence diagnostics)"
            raise PushRejectedError(
                f"Push to {branch} rejected (non-fast-forward). Something "
                f"unexpected touched this agent-owned branch. Divergence "
                f"(origin has commits local lacks):\n{diagnostics}",
                stderr=exc.stderr,
            ) from exc
        raise
