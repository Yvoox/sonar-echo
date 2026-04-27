"""Entity resolution / canonicalization.

Strategy v1 (naive but sound):
  - Stable ID = sha1(kb_id|type|normalized_canonical_name)[0:16]
  - When the embedding-cosine of two same-type entities is > HIGH_THRESHOLD,
    auto-merge (canonical kept = oldest).
  - Between LOW and HIGH thresholds, a row is added to
    entity_resolution_candidates so a human can later decide.
"""
from __future__ import annotations

import hashlib
import unicodedata
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.neo4j import get_driver
from app.ingestion.extractor import ExtractedEntity
from app.models import EntityResolutionCandidate
from app.services.llm import embed

LOW = 0.78
HIGH = 0.92


def _normalize(name: str) -> str:
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return " ".join(n.split())


def stable_entity_id(kb_id: uuid.UUID, type_: str, canonical_name: str) -> str:
    h = hashlib.sha1(f"{kb_id}|{type_}|{_normalize(canonical_name)}".encode()).hexdigest()
    return f"e_{h[:16]}"


@dataclass
class ResolvedEntity:
    canonical_id: str
    type: str
    canonical_name: str
    aliases: list[str]
    is_new: bool


async def resolve_entities(
    session: AsyncSession,
    kb_id: uuid.UUID,
    extracted: list[ExtractedEntity],
) -> dict[str, ResolvedEntity]:
    """Returns a map {local_id -> ResolvedEntity}."""
    if not extracted:
        return {}

    out: dict[str, ResolvedEntity] = {}
    driver = get_driver()
    async with driver.session(database="neo4j") as ne:
        # 1) compute candidate stable_ids
        candidates: list[tuple[ExtractedEntity, str]] = [
            (e, stable_entity_id(kb_id, e.type, e.canonical_name)) for e in extracted
        ]
        # 2) batch lookup existing entities in Neo4j
        ids = list({sid for _, sid in candidates})
        result = await ne.run(
            "MATCH (e:Entity {kb_id: $kb_id}) WHERE e.id IN $ids "
            "RETURN e.id as id, e.canonical_name as canonical_name, "
            "       e.aliases as aliases, e.type as type",
            kb_id=str(kb_id),
            ids=ids,
        )
        existing: dict[str, dict] = {}
        async for rec in result:
            existing[rec["id"]] = dict(rec)

        for ext, sid in candidates:
            if sid in existing:
                ex = existing[sid]
                aliases = list(set((ex.get("aliases") or []) + ext.aliases))
                out[ext.local_id] = ResolvedEntity(
                    canonical_id=sid,
                    type=ex["type"],
                    canonical_name=ex["canonical_name"],
                    aliases=aliases,
                    is_new=False,
                )
            else:
                out[ext.local_id] = ResolvedEntity(
                    canonical_id=sid,
                    type=ext.type,
                    canonical_name=ext.canonical_name,
                    aliases=ext.aliases,
                    is_new=True,
                )

    # 3) fuzzy candidates queue (low confidence merges)
    new_names = [r.canonical_name for r in out.values() if r.is_new]
    if new_names:
        new_vecs, _ = await embed(new_names)
        # naive: compare each new entity to its already-existing same-type peers
        # (no full DB scan to keep cost low)
        # If you want global dedupe, plug Qdrant or pgvector here.
        for r, vec in zip([x for x in out.values() if x.is_new], new_vecs):
            existing_same_type = [
                e for e in existing.values() if e["type"] == r.type
            ]
            if not existing_same_type:
                continue
            existing_names = [e["canonical_name"] for e in existing_same_type]
            existing_vecs, _ = await embed(existing_names)
            for ev, ename, sid_e in zip(
                existing_vecs, existing_names, [e["id"] for e in existing_same_type]
            ):
                sim = _cos(vec, ev)
                if sim >= HIGH:
                    r.canonical_id = sid_e
                    r.is_new = False
                elif sim >= LOW:
                    session.add(
                        EntityResolutionCandidate(
                            kb_id=kb_id,
                            entity_id=r.canonical_id,
                            suggested_canonical_id=sid_e,
                            confidence=float(sim),
                            metadata_json={"new_name": r.canonical_name, "existing_name": ename},
                        )
                    )
    return out


def _cos(a: list[float], b: list[float]) -> float:
    s = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return s / (na * nb)
