"""Qdrant storage.

One shared collection platform-wide (not one per project) — project_id is a
mandatory keyword payload field, indexed with is_tenant=true, and every
retrieval query filters on it.
"""

import hashlib
import os
import uuid

from qdrant_client import AsyncQdrantClient, models

from app.ingestion.chunking import Chunk
from app.ingestion.embeddings import EMBED_DIM

COLLECTION_NAME = os.environ.get("QDRANT_COLLECTION", "codebase_chunks")

_client: AsyncQdrantClient | None = None


def get_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(
            url=os.environ.get("QDRANT_URL", "http://qdrant:6333")
        )
    return _client


async def ensure_collection() -> None:
    """Idempotent — safe to call at the start of every ingestion run."""
    client = get_client()
    if not await client.collection_exists(COLLECTION_NAME):
        await client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=EMBED_DIM, distance=models.Distance.COSINE
            ),
        )
        await client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="project_id",
            field_schema=models.KeywordIndexParams(type="keyword", is_tenant=True),
        )


def _point_id(project_id: str, file_path: str, chunk_index: int) -> str:
    raw = f"{project_id}:{file_path}:{chunk_index}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, raw))


async def upsert_chunks(
    project_id: str,
    file_path: str,
    chunks: list[Chunk],
    embeddings: list[list[float]],
) -> None:
    """Replaces this file's existing points, then upserts the new chunk set."""
    await delete_file(project_id, file_path)
    points = [
        models.PointStruct(
            id=_point_id(project_id, file_path, i),
            vector=embedding,
            payload={
                "project_id": project_id,
                "file_path": file_path,
                "content": chunk.content,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
            },
        )
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]
    if points:
        await get_client().upsert(collection_name=COLLECTION_NAME, points=points)


async def delete_file(project_id: str, file_path: str) -> None:
    """Removes all points for a file."""
    await get_client().delete(
        collection_name=COLLECTION_NAME,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="project_id", match=models.MatchValue(value=project_id)
                    ),
                    models.FieldCondition(
                        key="file_path", match=models.MatchValue(value=file_path)
                    ),
                ]
            )
        ),
    )


# --- Step 11 File-Grounding Retrieval & Validation Helpers ---

async def file_exists_in_chunks(project_id: str, file_path: str) -> bool:
    """Check if any chunks exist for a given file_path and project_id in Qdrant.
    
    This is executed offline during mechanical grounding validation.
    """
    client = get_client()
    try:
        results, _ = await client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="project_id",
                        match=models.MatchValue(value=project_id),
                    ),
                    models.FieldCondition(
                        key="file_path",
                        match=models.MatchValue(value=file_path),
                    ),
                ]
            ),
            limit=1,
            with_payload=False,
            with_vectors=False,
        )
        return len(results) > 0
    except Exception as e:
        raise RuntimeError(f"Qdrant file presence lookup failed for {file_path}: {e}") from e


async def retrieve_chunks(
    project_id: str,
    query_vector: list[float],
    limit: int = 8,
) -> list[tuple[str, str]]:
    """Retrieve top-k relevant codebase chunks from Qdrant filtered by project_id."""
    client = get_client()
    try:
        results = await client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="project_id",
                        match=models.MatchValue(value=project_id)
                    )
                ]
            ),
            limit=limit,
        )
        return [
            (point.payload["file_path"], point.payload["content"])
            for point in results
            if point.payload and "file_path" in point.payload and "content" in point.payload
        ]
    except Exception as e:
        raise RuntimeError(f"Qdrant retrieval query failed: {e}") from e