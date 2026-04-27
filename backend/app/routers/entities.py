import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.neo4j import get_driver
from app.db.postgres import get_session
from app.graph import queries as gq
from app.models import Community
from app.schemas.entity import CommunityOut, EntityOut, TimelineOut
from app.security.permissions import require_kb_role
from app.workers.queue import enqueue_leiden

router = APIRouter(prefix="/api/v1/kbs/{kb_id}", tags=["entities"])


@router.get("/entities", response_model=list[EntityOut])
async def list_entities(
    kb_id: uuid.UUID = Path(...),
    type: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(50, le=200),
    _: tuple = Depends(require_kb_role("reader")),
) -> list[EntityOut]:
    driver = get_driver()
    async with driver.session() as ne:
        cypher = "MATCH (e:Entity {kb_id: $kb_id})"
        params: dict = {"kb_id": str(kb_id), "limit": limit}
        clauses: list[str] = []
        if type:
            clauses.append("e.type = $type")
            params["type"] = type
        if q:
            clauses.append("toLower(e.canonical_name) CONTAINS toLower($q)")
            params["q"] = q
        if clauses:
            cypher += " WHERE " + " AND ".join(clauses)
        cypher += (
            " RETURN e.id AS id, e.type AS type, e.canonical_name AS canonical_name, "
            "        coalesce(e.aliases, []) AS aliases "
            " ORDER BY e.canonical_name LIMIT $limit"
        )
        res = await ne.run(cypher, **params)
        return [EntityOut(**dict(r)) async for r in res]


@router.get("/entities/{entity_id}", response_model=EntityOut)
async def get_entity(
    kb_id: uuid.UUID = Path(...),
    entity_id: str = Path(...),
    _: tuple = Depends(require_kb_role("reader")),
) -> EntityOut:
    driver = get_driver()
    async with driver.session() as ne:
        res = await ne.run(
            "MATCH (e:Entity {id: $id, kb_id: $kb_id}) "
            "RETURN e.id AS id, e.type AS type, e.canonical_name AS canonical_name, "
            "       coalesce(e.aliases, []) AS aliases",
            id=entity_id,
            kb_id=str(kb_id),
        )
        rec = await res.single()
        if rec is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "entity not found")
        return EntityOut(**dict(rec))


@router.get("/entities/{entity_id}/timeline", response_model=TimelineOut)
async def get_timeline(
    kb_id: uuid.UUID = Path(...),
    entity_id: str = Path(...),
    start: date | None = Query(None),
    end: date | None = Query(None),
    include_superseded: bool = Query(False),
    _: tuple = Depends(require_kb_role("reader")),
) -> TimelineOut:
    driver = get_driver()
    async with driver.session() as ne:
        res = await ne.run(
            "MATCH (e:Entity {id: $id, kb_id: $kb_id}) "
            "RETURN e.id AS id, e.type AS type, e.canonical_name AS canonical_name, "
            "       coalesce(e.aliases, []) AS aliases",
            id=entity_id,
            kb_id=str(kb_id),
        )
        rec = await res.single()
        if rec is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "entity not found")
        entity = EntityOut(**dict(rec))
    events = await gq.entity_timeline(
        entity_id=entity_id,
        start=start,
        end=end,
        include_superseded=include_superseded,
    )
    return TimelineOut(entity=entity, events=events)


@router.get("/communities", response_model=list[CommunityOut])
async def list_communities(
    kb_id: uuid.UUID = Path(...),
    _: tuple = Depends(require_kb_role("reader")),
    session: AsyncSession = Depends(get_session),
) -> list[CommunityOut]:
    rows = (
        await session.execute(select(Community).where(Community.kb_id == kb_id))
    ).scalars().all()
    return [
        CommunityOut(
            id=str(c.id),
            label=c.label,
            summary=c.summary,
            member_entity_ids=c.member_entity_ids,
            level=c.level,
            generated_at=c.generated_at,
        )
        for c in rows
    ]


@router.get("/communities/{community_id}", response_model=CommunityOut)
async def get_community(
    kb_id: uuid.UUID = Path(...),
    community_id: uuid.UUID = Path(...),
    _: tuple = Depends(require_kb_role("reader")),
    session: AsyncSession = Depends(get_session),
) -> CommunityOut:
    c = await session.get(Community, community_id)
    if c is None or c.kb_id != kb_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "community not found")
    return CommunityOut(
        id=str(c.id),
        label=c.label,
        summary=c.summary,
        member_entity_ids=c.member_entity_ids,
        level=c.level,
        generated_at=c.generated_at,
    )


@router.post("/communities/rebuild", status_code=202)
async def rebuild_communities(
    kb_id: uuid.UUID = Path(...),
    _: tuple = Depends(require_kb_role("admin")),
) -> dict:
    await enqueue_leiden(kb_id)
    return {"status": "queued", "kb_id": str(kb_id)}


@router.get("/graph")
async def get_graph_subset(
    kb_id: uuid.UUID = Path(...),
    limit: int = Query(200, le=1000),
    _: tuple = Depends(require_kb_role("reader")),
) -> dict:
    """Lightweight nodes+edges payload for visualisation (Cytoscape-style)."""
    driver = get_driver()
    async with driver.session() as ne:
        nodes_res = await ne.run(
            "MATCH (e:Entity {kb_id: $kb_id}) "
            "RETURN e.id AS id, e.canonical_name AS label, e.type AS type LIMIT $limit",
            kb_id=str(kb_id),
            limit=limit,
        )
        nodes = [dict(r) async for r in nodes_res]
        edges_res = await ne.run(
            "MATCH (a:Entity {kb_id: $kb_id})-[r:RELATED_TO]->(b:Entity {kb_id: $kb_id}) "
            "RETURN a.id AS source, b.id AS target, r.type AS type, "
            "       toString(r.valid_from) AS valid_from, toString(r.valid_to) AS valid_to "
            "LIMIT $limit",
            kb_id=str(kb_id),
            limit=limit,
        )
        edges = [dict(r) async for r in edges_res]
    return {"nodes": nodes, "edges": edges}
