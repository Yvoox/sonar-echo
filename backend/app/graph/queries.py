"""High-level Cypher helpers using neo4j async driver."""
from __future__ import annotations

import uuid
from datetime import date

from app.db.neo4j import get_driver
from app.graph import temporal_model as tm


async def ensure_constraints() -> None:
    driver = get_driver()
    async with driver.session() as s:
        for q in tm.ENSURE_CONSTRAINTS:
            try:
                await s.run(q)
            except Exception:  # noqa: BLE001
                # Older Neo4j versions / index already exists in different form
                pass


async def upsert_document(
    *, kb_id: uuid.UUID, doc_id: uuid.UUID, title: str, source_date: date | None
) -> None:
    driver = get_driver()
    async with driver.session() as s:
        await s.run(
            tm.MERGE_DOCUMENT,
            kb_id=str(kb_id),
            doc_id=str(doc_id),
            title=title,
            source_date=source_date.isoformat() if source_date else None,
        )


async def link_supersedes(*, new_id: uuid.UUID, old_id: uuid.UUID) -> None:
    driver = get_driver()
    async with driver.session() as s:
        await s.run(tm.MERGE_SUPERSEDES, new_id=str(new_id), old_id=str(old_id))
        await s.run(tm.CLOSE_TX_FOR_DOC_FACTS, old_doc_id=str(old_id))


async def upsert_entities(*, kb_id: uuid.UUID, entities: list[dict]) -> None:
    """entities: [{id, type, canonical_name, aliases}]"""
    driver = get_driver()
    async with driver.session() as s:
        for e in entities:
            await s.run(
                tm.MERGE_ENTITY_NOAPOC,
                id=e["id"],
                kb_id=str(kb_id),
                type=e["type"],
                canonical_name=e["canonical_name"],
                aliases=list(set(e.get("aliases", []))),
            )


async def link_mentioned_in(*, doc_id: uuid.UUID, links: list[dict]) -> None:
    """links: [{entity_id, chunk_id, observation_date|None, confidence}]"""
    driver = get_driver()
    async with driver.session() as s:
        for l in links:
            await s.run(
                tm.MERGE_MENTIONED_IN,
                entity_id=l["entity_id"],
                doc_id=str(doc_id),
                chunk_id=l["chunk_id"],
                observation_date=l.get("observation_date"),
                confidence=float(l.get("confidence", 0.7)),
            )


async def upsert_relations(*, doc_id: uuid.UUID, relations: list[dict]) -> None:
    """relations: [{src_id, dst_id, type, valid_from, valid_to, confidence}]"""
    driver = get_driver()
    async with driver.session() as s:
        for r in relations:
            await s.run(
                tm.MERGE_RELATED_TO,
                src_id=r["src_id"],
                dst_id=r["dst_id"],
                type=r["type"],
                source_doc_id=str(doc_id),
                valid_from=r.get("valid_from"),
                valid_to=r.get("valid_to"),
                confidence=float(r.get("confidence", 0.7)),
            )


async def delete_doc_cascade(*, doc_id: uuid.UUID, kb_id: uuid.UUID) -> None:
    driver = get_driver()
    async with driver.session() as s:
        await s.run(tm.DELETE_DOC_CASCADE, doc_id=str(doc_id))
        await s.run(tm.CLEANUP_ORPHAN_ENTITIES, kb_id=str(kb_id))


async def entity_fulltext_search(
    *, kb_id: uuid.UUID, q: str, k: int = 10
) -> list[dict]:
    driver = get_driver()
    async with driver.session() as s:
        # neo4j fulltext query language → escape user input minimally
        safe = q.replace('"', " ")
        try:
            res = await s.run(
                tm.ENTITY_FULLTEXT_SEARCH, q=safe, kb_id=str(kb_id), k=k
            )
            return [dict(r) async for r in res]
        except Exception:
            return []


async def entity_timeline(
    *,
    entity_id: str,
    start: date | None = None,
    end: date | None = None,
    include_superseded: bool = False,
) -> list[dict]:
    driver = get_driver()
    async with driver.session() as s:
        res = await s.run(
            tm.ENTITY_TIMELINE,
            entity_id=entity_id,
            start=start.isoformat() if start else None,
            end=end.isoformat() if end else None,
            include_superseded=include_superseded,
        )
        out = []
        async for rec in res:
            out.append(dict(rec))
        return out


async def expand_neighbours(
    *,
    entity_ids: list[str],
    start: date | None = None,
    end: date | None = None,
) -> list[dict]:
    driver = get_driver()
    async with driver.session() as s:
        res = await s.run(
            tm.EXPAND_NEIGHBOURS,
            entity_ids=entity_ids,
            start=start.isoformat() if start else None,
            end=end.isoformat() if end else None,
        )
        return [dict(r) async for r in res]


async def entities_for_chunks(*, chunk_ids: list[str]) -> dict[str, list[str]]:
    driver = get_driver()
    async with driver.session() as s:
        res = await s.run(tm.ENTITIES_FOR_CHUNKS, chunk_ids=chunk_ids)
        out: dict[str, list[str]] = {}
        async for rec in res:
            out[rec["chunk_id"]] = rec["entity_ids"]
        return out
