"""Persisted repo working directory + change detection since the last ingestion.

persist the clone across runs, `git fetch` + `git pull` on
re-run instead of a fresh clone every time. Change detection via
`git diff --name-status <last_ingested_sha> HEAD`.
"""

import asyncio
import os
from dataclasses import dataclass

REPO_CLONE_ROOT = os.environ.get("REPO_CLONE_ROOT", "/data/repos")


@dataclass
class RepoDiff:
    added: list[str]
    modified: list[str]
    deleted: list[str]
    head_sha: str


class GitCommandError(RuntimeError):
    pass


async def _run_git(*args: str, cwd: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise GitCommandError(
            f"git {' '.join(args)} failed in {cwd}: {stderr.decode().strip()}"
        )
    return stdout.decode()


def local_repo_path(project_id: str) -> str:
    return os.path.join(REPO_CLONE_ROOT, project_id)


async def sync_repo(project_id: str, clone_url: str) -> str:
    """Clones the repo on first run; fetch + pull on every re-run (per the
    locked ingestion-logic decision), rather than a fresh clone each time."""
    path = local_repo_path(project_id)
    if os.path.isdir(os.path.join(path, ".git")):
        await _run_git("remote", "set-url", "origin", clone_url, cwd=path)
        await _run_git("fetch", "origin", cwd=path)
        await _run_git("pull", cwd=path)
    else:
        os.makedirs(path, exist_ok=True)
        # Full clone, not shallow. git diff against last_ingested_sha on every
        # subsequent run needs that old commit to still be reachable locally —
        # a --depth 1 clone only retains the tip, and a plain `git fetch`
        # afterward doesn't deepen a shallow repo's history backward. Once a
        # second push landed, the diff would fail with "unknown revision."
        await _run_git("clone", clone_url, path, cwd=REPO_CLONE_ROOT)
    return path


async def get_head_sha(repo_path: str) -> str:
    output = await _run_git("rev-parse", "HEAD", cwd=repo_path)
    return output.strip()


async def diff_since(repo_path: str, last_ingested_sha: str | None) -> RepoDiff:
    """Returns added/modified/deleted files since last_ingested_sha.

    On first run (last_ingested_sha is None), there's nothing to diff against —
    every tracked file in the repo is treated as added.
    """
    head_sha = await get_head_sha(repo_path)

    if last_ingested_sha is None:
        output = await _run_git("ls-tree", "-r", "--name-only", "HEAD", cwd=repo_path)
        files = [line for line in output.splitlines() if line]
        return RepoDiff(added=files, modified=[], deleted=[], head_sha=head_sha)

    output = await _run_git(
        "diff", "--name-status", last_ingested_sha, "HEAD", cwd=repo_path
    )
    added, modified, deleted = [], [], []
    for line in output.splitlines():
        if not line.strip():
            continue
        status, path = line.split("\t", 1)
        if status == "A":
            added.append(path)
        elif status == "D":
            deleted.append(path)
        elif status in ("M", "R", "C") or status.startswith(("M", "R", "C")):
            # Renames/copies (R100, C100, ...) — treat the new path as modified;
            # re-chunking it covers content correctly either way.
            modified.append(path.split("\t")[-1])
        # Deliberately no catch-all "else": an unrecognized status is a sign
        # something about the diff format changed, not a file to silently skip.

    return RepoDiff(added=added, modified=modified, deleted=deleted, head_sha=head_sha)