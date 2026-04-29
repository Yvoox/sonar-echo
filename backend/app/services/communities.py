"""Leiden-based community detection (via Neo4j GDS) + LLM summaries.

Triggered manually (admin) or via the worker scheduler.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.neo4j import get_driver
from app.db.postgres import SessionLocal
from app.models import Community
from app.services.llm import chat_complete, embed

logger = logging.getLogger(__name__)


GDS_PROJECT = """
CALL gds.graph.exists($graph_name) YIELD exists
WITH exists
CALL apoc.do.when(exists, 'CALL gds.graph.drop($name) YIELD graphName RETURN graphName',
                          'RETURN null AS graphName',
                          {name: $graph_name}) YIELD value
RETURN value.graphName AS graphName
"""


async def run_leiden_and_summarise(kb_id: uuid.UUID) -> None:
    driver = get_driver()
    run_id = f"leiden_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{kb_id}"
    graph_name = f"g_{kb_id.hex[:12]}"

    async with driver.session() as ne:
        # Drop projection if exists (best-effort, no APOC required)
        try:
            await ne.run(f"CALL gds.graph.drop('{graph_name}', false)")
        except Exception:  # noqa: BLE001
            pass

        # Project the entity-RELATED_TO subgraph (filtered by kb_id at projection)
        node_query = "MATCH (e:Entity {kb_id: $kb_id}) RETURN id(e) AS id"
        rel_query = (
            "MATCH (a:Entity {kb_id: $kb_id})-[r:RELATED_TO]-(b:Entity {kb_id: $kb_id}) "
            "RETURN id(a) AS source, id(b) AS target, coalesce(r.confidence, 0.7) AS weight"
        )
        await ne.run(
            """
            CALL gds.graph.project.cypher(
              $graph_name,
              $node_query,
              $rel_query,
              {parameters: {kb_id: $kb_id}}
            )
            """,
            graph_name=graph_name,
            node_query=node_query,
            rel_query=rel_query,
            kb_id=str(kb_id),
        )

        # Run Leiden, write community ids back to nodes
        try:
            await ne.run(
                """
                CALL gds.leiden.write($graph_name, {
                  writeProperty: 'community_id',
                  relationshipWeightProperty: 'weight',
                  randomSeed: 42
                })
                YIELD communityCount, modularity
                RETURN communityCount, modularity
                """,
                graph_name=graph_name,
            )
        except Exception as exc:  # noqa: BLE001
            # Leiden plugin missing → silently skip (dev environments without GDS)
            logger.warning("Leiden unavailable, skipping: %s", exc)
            try:
                await ne.run(f"CALL gds.graph.drop('{graph_name}', false)")
            except Exception:  # noqa: BLE001
                pass
            return

        # Pull communities & their members
        result = await ne.run(
            """
            MATCH (e:Entity {kb_id: $kb_id})
            WHERE e.community_id IS NOT NULL
            RETURN e.community_id AS cid,
                   collect({id: e.id, type: e.type, name: e.canonical_name}) AS members
            ORDER BY size(members) DESC
            LIMIT 100
            """,
            kb_id=str(kb_id),
        )
        comms = [dict(r) async for r in result]

        try:
            await ne.run(f"CALL gds.graph.drop('{graph_name}', false)")
        except Exception:  # noqa: BLE001
            pass

    # Summarise + persist
    async with SessionLocal() as session:
        # wipe previous communities for this KB (we keep only the latest run)
        await session.execute(delete(Community).where(Community.kb_id == kb_id))
        await session.flush()

        labels: list[str] = []
        summaries: list[str] = []
        rows: list[Community] = []
        for c in comms:
            members = c["members"][:30]
            label, summary = await _llm_summarise(members)
            labels.append(label)
            summaries.append(summary)
            rows.append(
                Community(
                    kb_id=kb_id,
                    level=0,
                    label=label,
                    summary=summary,
                    member_entity_ids=[m["id"] for m in c["members"]],
                    leiden_run_id=run_id,
                )
            )

        # embed summaries in one batch
        if summaries:
            vecs, _ = await embed(summaries)
            for r, v in zip(rows, vecs):
                r.summary_embedding = v

        for r in rows:
            session.add(r)
        await session.commit()


async def _llm_summarise(members: list[dict]) -> tuple[str, str]:
    """Returns (label, summary) for a community."""
    if not members:
        return ("(vide)", "")
    if not settings.openai_api_key:
        names = ", ".join(m["name"] for m in members[:10])
        return (names[:60] or "communauté", f"Communauté regroupant : {names}")

    listing = "\n".join(f"- {m['type']}: {m['name']}" for m in members[:30])
    sys = (
        "Tu es un analyste documentaire. Tu reçois une liste d'entités liées entre elles "
        "dans une base de connaissance. Tu produis :\n"
        "1) un label court (max 6 mots) qui capture la thématique commune,\n"
        "2) un résumé en 3-5 phrases décrivant le rôle de cette communauté."
    )
    res = await chat_complete(
        system=sys,
        messages=[{
            "role": "user",
            "content": f"Membres de la communauté :\n{listing}\n\nRéponds au format :\n"
                       f"LABEL: <label>\nRESUME: <résumé>",
        }],
        model=settings.openai_model_routing,
        temperature=0.3,
    )
    text = res["text"]
    label = "Communauté"
    summary = text
    for line in text.splitlines():
        if line.lower().startswith("label:"):
            label = line.split(":", 1)[1].strip()
        elif line.lower().startswith("resume") or line.lower().startswith("résumé"):
            summary = line.split(":", 1)[1].strip()
    return (label[:300] or "Communauté", summary or text)
