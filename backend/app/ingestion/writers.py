"""Saga writes across Qdrant + Neo4j + Postgres.

Order:
  Step A — Qdrant upserts (chunks)
  Step B — Neo4j: document, entities, MENTIONED_IN, RELATED_TO
  Step C — Postgres: ingestion_jobs.saga_step + commit
  Step D — Postgres: documents.state = ingested

Idempotency:
  - Qdrant points keyed by chunk_id (deterministic from doc_id + chunk_id)
  - Neo4j MERGEs on stable IDs
  - On compensation (delete_for_doc), all stores receive a doc_id-scoped delete.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Iterable

from qdrant_client.http import models as qmodels
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import qdrant
from app.graph import queries as gq
from app.ingestion.chunker import Chunk
from app.ingestion.extractor import ExtractedRelation
from app.ingestion.resolver import ResolvedEntity
from app.models import IngestionJob


def _qdrant_point_id(doc_id: uuid.UUID, chunk_id: str) -> str:
    return f"{doc_id}:{chunk_id}"


async def write_chunks_to_qdrant(
    *,
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    chunks: list[Chunk],
    embeddings: list[list[float]],
    chunk_entity_ids: dict[str, list[str]],
    valid_from: date | None,
    valid_to: date | None,
) -> None:
    await qdrant.ensure_collection()
    client = qdrant.get_client()
    points: list[qmodels.PointStruct] = []
    for chunk, vec in zip(chunks, embeddings):
        points.append(
            qmodels.PointStruct(
                id=_uuid5(_qdrant_point_id(doc_id, chunk.chunk_id)),
                vector=vec,
                payload={
                    "kb_id": str(kb_id),
                    "doc_id": str(doc_id),
                    "chunk_id": chunk.chunk_id,
                    "page": chunk.page,
                    "text": chunk.text,
                    "entity_ids": chunk_entity_ids.get(chunk.chunk_id, []),
                    "valid_from": valid_from.isoformat() if valid_from else None,
                    "valid_to": valid_to.isoformat() if valid_to else None,
                },
            )
        )
    if points:
        await client.upsert(
            collection_name=settings.qdrant_collection,
            points=points,
            wait=True,
        )


async def delete_chunks_for_doc(doc_id: uuid.UUID) -> None:
    client = qdrant.get_client()
    await client.delete(
        collection_name=settings.qdrant_collection,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="doc_id",
                        match=qmodels.MatchValue(value=str(doc_id)),
                    )
                ]
            )
        ),
        wait=True,
    )


async def write_graph(
    *,
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    title: str,
    source_date: date | None,
    supersedes: uuid.UUID | None,
    resolved_entities: dict[str, ResolvedEntity],
    relations: list[ExtractedRelation],
    mentions_per_chunk: list[tuple[str, list[str]]],   # (chunk_id, [canonical_id])
    observation_date: date | None,
) -> None:
    await gq.upsert_document(
        kb_id=kb_id, doc_id=doc_id, title=title, source_date=source_date
    )
    if supersedes:
        await gq.link_supersedes(new_id=doc_id, old_id=supersedes)

    # entities
    seen: dict[str, dict] = {}
    for r in resolved_entities.values():
        seen[r.canonical_id] = {
            "id": r.canonical_id,
            "type": r.type,
            "canonical_name": r.canonical_name,
            "aliases": list({*r.aliases, r.canonical_name}),
        }
    if seen:
        await gq.upsert_entities(kb_id=kb_id, entities=list(seen.values()))

    # MENTIONED_IN
    mentions_payload = []
    for chunk_id, ent_ids in mentions_per_chunk:
        for eid in ent_ids:
            mentions_payload.append({
                "entity_id": eid,
                "chunk_id": chunk_id,
                "observation_date": observation_date.isoformat() if observation_date else None,
                "confidence": 0.9,
            })
    if mentions_payload:
        await gq.link_mentioned_in(doc_id=doc_id, links=mentions_payload)

    # RELATED_TO
    rels_payload = []
    for r in relations:
        src = resolved_entities.get(r.src_local_id)
        dst = resolved_entities.get(r.dst_local_id)
        if not src or not dst:
            continue
        rels_payload.append({
            "src_id": src.canonical_id,
            "dst_id": dst.canonical_id,
            "type": r.type,
            "valid_from": r.valid_from,
            "valid_to": r.valid_to,
            "confidence": r.confidence,
        })
    if rels_payload:
        await gq.upsert_relations(doc_id=doc_id, relations=rels_payload)


async def update_saga_step(session: AsyncSession, job: IngestionJob, step: str) -> None:
    job.saga_step = step
    await session.commit()


def _uuid5(s: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, s))
