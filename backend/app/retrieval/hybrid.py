"""Unified 4-dimension retrieval: chunks + entities + timeline + communities."""
from __future__ import annotations

import asyncio
import uuid
from datetime import date

from qdrant_client.http import models as qmodels
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import qdrant
from app.db.postgres import SessionLocal
from app.graph import queries as gq
from app.models import Community, Document
from app.retrieval.reranker import get_reranker
from app.retrieval.temporal_intent import TemporalIntent, detect
from app.schemas.retrieval import (
    ChunkResult,
    Citation,
    CommunityResult,
    EntityResult,
    SearchOut,
    TimelineEvent,
)
from app.services.llm import embed


async def search(
    *,
    kb_id: uuid.UUID,
    query: str,
    date_range: tuple[date, date] | None = None,
    k: int = 10,
    include_superseded: bool = False,
) -> SearchOut:
    intent = await detect(query)
    if date_range:
        intent.date_range = date_range

    # parallel: embed query + entity full-text
    (q_vecs, _), entity_hits = await asyncio.gather(
        embed([query]),
        gq.entity_fulltext_search(kb_id=kb_id, q=query, k=20),
    )
    q_vec = q_vecs[0]

    # (a) chunks
    chunk_hits = await _qdrant_search(kb_id, q_vec, intent, k_total=40, include_superseded=include_superseded)

    # promote entities mentioned in the chunk hits
    chunk_ids = [c["chunk_id"] for c in chunk_hits]
    chunk_to_ents = await gq.entities_for_chunks(chunk_ids=chunk_ids) if chunk_ids else {}
    promoted: dict[str, dict] = {h["id"]: {**h, "mention_count": 0} for h in entity_hits}
    for chunk_id, ents in chunk_to_ents.items():
        for eid in ents:
            promoted.setdefault(eid, {"id": eid, "type": "Unknown", "canonical_name": eid,
                                       "score": 0.0, "mention_count": 0})
            promoted[eid]["mention_count"] += 1
    entities_top = sorted(
        promoted.values(),
        key=lambda x: (x["mention_count"], x.get("score", 0.0)),
        reverse=True,
    )[:20]

    # (c) timeline events for top entities
    timeline: list[dict] = []
    for e in entities_top[:8]:
        events = await gq.entity_timeline(
            entity_id=e["id"],
            start=intent.date_range[0] if intent.date_range else None,
            end=intent.date_range[1] if intent.date_range else None,
            include_superseded=include_superseded,
        )
        timeline.extend(events[:10])

    # (d) communities (pgvector cosine on summary_embedding)
    communities = await _community_search(kb_id, q_vec, k=3)

    # graph expansion: pull chunks of neighbours to enrich
    if entities_top:
        neigh = await gq.expand_neighbours(
            entity_ids=[e["id"] for e in entities_top[:5]],
            start=intent.date_range[0] if intent.date_range else None,
            end=intent.date_range[1] if intent.date_range else None,
        )
        # we don't pull additional Qdrant hits here to keep latency in check;
        # in v2 we'd intersect neighbour entity_ids with payload-filtered Qdrant search

    # rerank
    reranker = get_reranker()
    chunk_hits = await reranker.rerank(query, chunk_hits)
    chunk_hits = chunk_hits[:k]

    # build response
    chunks_out: list[ChunkResult] = []
    async with SessionLocal() as session:
        doc_titles = await _doc_titles(session, [uuid.UUID(c["doc_id"]) for c in chunk_hits])
        for h in chunk_hits:
            doc_uuid = uuid.UUID(h["doc_id"])
            citation = Citation(
                doc_id=doc_uuid,
                doc_title=doc_titles.get(doc_uuid, h["doc_id"]),
                page=h.get("page"),
                source_date=_safe_date(h.get("valid_from")),
                chunk_id=h["chunk_id"],
                entity_ids=h.get("entity_ids", []),
            )
            chunks_out.append(
                ChunkResult(
                    chunk_id=h["chunk_id"],
                    text=h["text"],
                    score=h["score"],
                    citation=citation,
                    entity_ids=h.get("entity_ids", []),
                )
            )

    entities_out = [
        EntityResult(
            id=e["id"],
            canonical_name=e.get("canonical_name", e["id"]),
            type=e.get("type", "Unknown"),
            score=float(e.get("score", 0.0)),
            mention_count=int(e.get("mention_count", 0)),
        )
        for e in entities_top[:10]
    ]
    timeline_out = [
        TimelineEvent(
            entity_id=t["entity_id"],
            related_entity_id=t.get("related_entity_id"),
            type=t.get("type", "RELATED_TO"),
            valid_from=_safe_date(t.get("valid_from")),
            valid_to=_safe_date(t.get("valid_to")),
            source_doc_id=uuid.UUID(t["source_doc_id"]) if t.get("source_doc_id") else None,
            source_doc_title=t.get("source_doc_title"),
            confidence=t.get("confidence"),
        )
        for t in timeline[:30]
    ]
    return SearchOut(
        chunks=chunks_out,
        entities=entities_out,
        timeline=timeline_out,
        communities=communities,
    )


async def _qdrant_search(
    kb_id: uuid.UUID,
    q_vec: list[float],
    intent: TemporalIntent,
    k_total: int,
    include_superseded: bool,
) -> list[dict]:
    client = qdrant.get_client()
    must = [qmodels.FieldCondition(key="kb_id", match=qmodels.MatchValue(value=str(kb_id)))]
    qfilter = qmodels.Filter(must=must)
    res = await client.search(
        collection_name=settings.qdrant_collection,
        query_vector=q_vec,
        limit=k_total,
        query_filter=qfilter,
        with_payload=True,
    )
    out: list[dict] = []
    for r in res:
        p = r.payload or {}
        out.append({
            "chunk_id": p.get("chunk_id"),
            "doc_id": p.get("doc_id"),
            "page": p.get("page"),
            "text": p.get("text", ""),
            "score": float(r.score),
            "entity_ids": p.get("entity_ids") or [],
            "valid_from": p.get("valid_from"),
            "valid_to": p.get("valid_to"),
        })
    # post-filter on date range (Qdrant doesn't do date arithmetic on strings nicely)
    if intent.date_range:
        a, b = intent.date_range
        def overlap(c: dict) -> bool:
            vf = _safe_date(c.get("valid_from"))
            vt = _safe_date(c.get("valid_to"))
            if vf is None and vt is None:
                return True
            return (vt is None or vt >= a) and (vf is None or vf <= b)
        out = [c for c in out if overlap(c)]
    return out


async def _doc_titles(session: AsyncSession, doc_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not doc_ids:
        return {}
    rows = (
        await session.execute(
            select(Document.id, Document.title).where(Document.id.in_(doc_ids))
        )
    ).all()
    return {r[0]: r[1] for r in rows}


async def _community_search(
    kb_id: uuid.UUID, q_vec: list[float], k: int
) -> list[CommunityResult]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(Community)
                .where(Community.kb_id == kb_id)
                .order_by(Community.summary_embedding.cosine_distance(q_vec))
                .limit(k)
            )
        ).scalars().all()
        out = []
        for c in rows:
            out.append(CommunityResult(
                id=c.id,
                label=c.label,
                summary=c.summary,
                member_entity_ids=c.member_entity_ids,
                score=0.0,  # not exposed by SQLA cosine_distance
            ))
        return out


def _safe_date(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (ValueError, TypeError):
        return None
