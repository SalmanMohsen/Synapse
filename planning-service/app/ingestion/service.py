"""Top-level ingestion orchestration.

A callable async function, not a standalone script — only what calls it changes.
"""

import logging
import os

from sqlalchemy import select, update

from app.db import get_connection, git_integrations
from app.git_providers import GitIntegrationRef, get_git_provider
from app.ingestion import chunking, embeddings, qdrant_store, repo_sync

logger = logging.getLogger(__name__)


async def _get_git_integration(project_id: str) -> dict:
    async with get_connection() as conn:
        result = await conn.execute(
            select(git_integrations).where(
                git_integrations.c.project_id == project_id
            )
        )
        row = result.mappings().first()
        if row is None:
            raise ValueError(f"No GitIntegration configured for project {project_id}")
        return dict(row)


async def _update_last_ingested_sha(project_id: str, sha: str) -> None:
    async with get_connection() as conn:
        await conn.execute(
            update(git_integrations)
            .where(git_integrations.c.project_id == project_id)
            .values(last_ingested_sha=sha)
        )


async def ingest_repository(project_id: str) -> None:
    """Incrementally (re)ingests a project's repo into Qdrant.

    Re-running with no new commits since last_ingested_sha is a cheap no-op
    (empty diff, nothing to embed) — safe to call from a webhook handler,
    a manual backfill, or a retry after a prior failed attempt alike.
    """
    integration_row = await _get_git_integration(project_id)

    # git_integrations doesn't have a `provider` column yet -- every row is
    # implicitly GitHub today, hardcoded here until that (backend-owned)
    # migration lands. Everything from this line down only talks to
    # `git_provider`, never to GitHub by name.
    integration = GitIntegrationRef(
        provider=integration_row["provider"],
        external_ref=integration_row["github_app_installation_id"],
        repo_full_name=integration_row["repo_full_name"],
    )
    git_provider = get_git_provider(integration.provider)

    token = await git_provider.get_access_token(integration)
    clone_url = git_provider.build_authenticated_clone_url(integration, token)

    repo_path = await repo_sync.sync_repo(project_id, clone_url)
    diff = await repo_sync.diff_since(repo_path, integration_row["last_ingested_sha"])

    await qdrant_store.ensure_collection()

    for file_path in diff.added + diff.modified:
        if chunking.is_excluded(file_path):
            continue

        full_path = os.path.join(repo_path, file_path)
        if not os.path.isfile(full_path):
            # e.g. the "new path" side of a rename that was itself later
            # deleted within the same diff range — nothing to read.
            continue

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            logger.warning("Skipping non-text file during ingestion: %s", file_path)
            continue

        chunks = chunking.dispatch_chunk(file_path, content)
        if not chunks:
            continue

        vectors = embeddings.embed_documents([chunk.content for chunk in chunks])
        await qdrant_store.upsert_chunks(project_id, file_path, chunks, vectors)

    for file_path in diff.deleted:
        await qdrant_store.delete_file(project_id, file_path)

    await _update_last_ingested_sha(project_id, diff.head_sha)