"""Phase 0 checkpoint for planning-service. Run with: pytest -m integration"""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.mark.asyncio
async def test_schema_created(pg_conn):
    from sqlalchemy import text

    result = await pg_conn.execute(text("SELECT to_regclass('public.tickets')"))
    assert result.scalar() is not None


@pytest.mark.asyncio
async def test_qdrant_write_and_query_one_point(qdrant_client):
    from qdrant_client.models import Distance, PointStruct, VectorParams

    collection = "phase0_smoke_test"
    await qdrant_client.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=4, distance=Distance.COSINE),
    )
    await qdrant_client.upsert(
        collection_name=collection,
        points=[PointStruct(id=1, vector=[0.1, 0.2, 0.3, 0.4], payload={"project_id": "smoke"})],
    )

    result = await qdrant_client.retrieve(collection_name=collection, ids=[1])
    assert len(result) == 1
    assert result[0].payload["project_id"] == "smoke"