from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from app.config import settings

_client: AsyncQdrantClient | None = None


def get_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        )
    return _client


async def ensure_collection() -> None:
    client = get_client()
    collections = await client.get_collections()
    names = {c.name for c in collections.collections}
    if settings.qdrant_collection not in names:
        await client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=qmodels.VectorParams(
                size=settings.openai_embedding_dim,
                distance=qmodels.Distance.COSINE,
            ),
        )
        for field in ("kb_id", "doc_id", "chunk_id"):
            await client.create_payload_index(
                collection_name=settings.qdrant_collection,
                field_name=field,
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
