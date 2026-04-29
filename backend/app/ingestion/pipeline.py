"""Ingestion saga orchestrator (called by Arq worker)."""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import SessionLocal
from app.graph import queries as gq
from app.ingestion import writers
from app.ingestion.chunker import chunk_pages
from app.ingestion.extractor import extract_chunk
from app.ingestion.ocr import ocr_document
from app.ingestion.resolver import resolve_entities
from app.models import Document, IngestionJob
from app.services import document_state
from app.services.audit import log
from app.services.llm import cost_usd, embed
from app.services.storage import download_bytes

logger = logging.getLogger(__name__)


async def run_ingestion(job_id: uuid.UUID, document_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        job = await session.get(IngestionJob, job_id)
        doc = await session.get(Document, document_id)
        if job is None or doc is None:
            logger.error("missing job or document: job=%s doc=%s", job_id, document_id)
            return

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        await session.commit()

        try:
            await _ingest(session, job, doc)
        except Exception as exc:  # noqa: BLE001
            logger.exception("ingestion failed for doc %s", document_id)
            job.status = "failed"
            job.error = str(exc)[:2000]
            job.finished_at = datetime.now(timezone.utc)
            try:
                await document_state.transition(
                    session, doc, "ingestion_failed", None, f"error: {exc!s}"
                )
            except document_state.IllegalStateTransition:
                pass
            await session.commit()
            return


async def _ingest(session: AsyncSession, job: IngestionJob, doc: Document) -> None:
    await gq.ensure_constraints()
    print("Starting document ingestion")


    # === Step 0: download + OCR ===
    print("Step 0: download + OCR ")
    raw = download_bytes(doc.storage_uri)
    ocr = await ocr_document(raw, doc.mime_type)

    # === Step 1: chunking ===
    print("Step 1: chunking")

    chunks = chunk_pages(ocr)
    if not chunks:
        raise RuntimeError("no chunks produced from OCR (empty document?)")
    job.saga_step = "chunked"
    await session.commit()

    # === Step 2: extraction (per chunk) ===
    print("Step 2: extraction (per chunk)")
    all_entities = []
    all_relations = []
    chunk_local_ents: list[list] = []
    document_dates = []
    total_in = 0
    total_out = 0
    total_cost = 0.0

    for chunk in chunks:
        ext = await extract_chunk(chunk.text, doc.title, doc.source_date)
        # prefix local_ids with chunk_id to avoid collision across chunks
        for e in ext.entities:
            e.local_id = f"{chunk.chunk_id}::{e.local_id}"
        for r in ext.relations:
            r.src_local_id = f"{chunk.chunk_id}::{r.src_local_id}"
            r.dst_local_id = f"{chunk.chunk_id}::{r.dst_local_id}"
        all_entities.extend(ext.entities)
        all_relations.extend(ext.relations)
        chunk_local_ents.append([e.local_id for e in ext.entities])
        if ext.document_date:
            document_dates.append(ext.document_date)
        total_in += ext.tokens_in
        total_out += ext.tokens_out
        total_cost += ext.cost_usd

    # consolidate document date if missing
    if not doc.source_date and document_dates:
        try:
            doc.source_date = date.fromisoformat(document_dates[0])
        except ValueError:
            pass

    job.token_usage_in = total_in
    job.token_usage_out = total_out
    job.cost_usd = total_cost
    job.saga_step = "extracted"
    await session.commit()

    # === Step 3: entity resolution ===
    print("Step 3: entity resolution")

    resolved = await resolve_entities(session, doc.kb_id, all_entities)
    job.saga_step = "resolved"
    await session.commit()

    # === Step 4: embeddings (parallel batch) ===
    print("Step 4: embeddings (parallel batch)")

    texts = [c.text for c in chunks]
    embeddings, emb_in = await embed(texts)
    job.token_usage_in += emb_in
    job.cost_usd += cost_usd("text-embedding-3-small", emb_in, 0)
    await session.commit()

    # === Step 5: build per-chunk entity_ids list ===
    print("Step 5: build per-chunk entity_ids list")

    chunk_entity_ids: dict[str, list[str]] = {}
    mentions_per_chunk: list[tuple[str, list[str]]] = []
    for chunk, locals_ in zip(chunks, chunk_local_ents):
        canonicals = list({resolved[lid].canonical_id for lid in locals_ if lid in resolved})
        chunk_entity_ids[chunk.chunk_id] = canonicals
        mentions_per_chunk.append((chunk.chunk_id, canonicals))

    # === Step A: Qdrant ===
    print("Step A: Qdrant")

    await writers.write_chunks_to_qdrant(
        kb_id=doc.kb_id,
        doc_id=doc.id,
        chunks=chunks,
        embeddings=embeddings,
        chunk_entity_ids=chunk_entity_ids,
        valid_from=doc.source_date,
        valid_to=None,
    )
    job.saga_step = "qdrant_written"
    await session.commit()

    # === Step B: Neo4j ===
    print("Step B: Neo4j")
    print(f"DEBUG RELATION {all_relations}")

    await writers.write_graph(
        kb_id=doc.kb_id,
        doc_id=doc.id,
        title=doc.title,
        source_date=doc.source_date,
        supersedes=doc.supersedes_id,
        resolved_entities=resolved,
        relations=all_relations,
        mentions_per_chunk=mentions_per_chunk,
        observation_date=doc.source_date,
    )
    job.saga_step = "neo4j_written"
    await session.commit()

    # === Step C: PG state machine commit-last (visibility gate) ===
    print("Step C: PG state machine commit-last (visibility gate)")

    await document_state.transition(
        session, doc, "ingested", None, "ingestion completed"
    )
    if doc.supersedes_id:
        # mark old document as superseded + link
        old = await session.get(Document, doc.supersedes_id)
        if old and old.state in ("ingested", "ingestion_failed", "approved"):
            try:
                await document_state.transition(
                    session, old, "superseded", None, f"superseded by {doc.id}"
                )
                old.superseded_by_id = doc.id
            except document_state.IllegalStateTransition:
                pass
    job.status = "succeeded"
    job.saga_step = "done"
    job.finished_at = datetime.now(timezone.utc)
    await log(
        session, doc.created_by, "document.ingested", "document", str(doc.id),
        {
            "tokens_in": job.token_usage_in,
            "tokens_out": job.token_usage_out,
            "cost_usd": job.cost_usd,
            "chunks": len(chunks),
            "entities": len({r.canonical_id for r in resolved.values()}),
            "relations": len(all_relations),
        },
    )
    await session.commit()
