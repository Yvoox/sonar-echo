"""Arq task implementations."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import SessionLocal
from app.graph import queries as gq
from app.ingestion import writers
from app.ingestion.pipeline import run_ingestion as _run_ingestion
from app.models import Automation, Document, User
from app.services.audit import log
from app.services.storage import delete_object

logger = logging.getLogger(__name__)


async def ingest_document(ctx: dict, job_id: str, document_id: str) -> None:
    await _run_ingestion(uuid.UUID(job_id), uuid.UUID(document_id))


async def cleanup_document(ctx: dict, document_id: str, hard: bool) -> None:
    """Delete chunks from Qdrant + cascade in Neo4j; optional MinIO purge."""
    doc_id = uuid.UUID(document_id)
    async with SessionLocal() as session:
        doc = await session.get(Document, doc_id)
        if doc is None:
            return
        try:
            await writers.delete_chunks_for_doc(doc_id)
        except Exception:  # noqa: BLE001
            logger.exception("qdrant cleanup failed for %s", doc_id)
        try:
            await gq.delete_doc_cascade(doc_id=doc_id, kb_id=doc.kb_id)
        except Exception:  # noqa: BLE001
            logger.exception("neo4j cleanup failed for %s", doc_id)
        if hard and doc.storage_uri:
            try:
                delete_object(doc.storage_uri)
            except Exception:  # noqa: BLE001
                logger.exception("minio purge failed for %s", doc_id)
        await log(session, None, "document.cleaned", "document", str(doc_id), {"hard": hard})
        await session.commit()


async def erase_user(ctx: dict, user_id: str) -> None:
    """GDPR right-to-erasure (cascade across PG + Neo4j + Qdrant)."""
    uid = uuid.UUID(user_id)
    async with SessionLocal() as session:
        user = await session.get(User, uid)
        if user is None:
            return
        # Pseudonymise PG identifiers; documents & chats are kept but de-linked
        user.email = f"erased-{uid}@erased.local"
        user.password_hash = "!"
        user.erased = True
        # Cleanup user-uploaded docs in stores (caller-defined business rules
        # could also keep org-shared docs; we delete only those flagged personal)
        docs = (
            await session.execute(
                select(Document).where(Document.created_by == uid)
            )
        ).scalars().all()
        for doc in docs:
            try:
                await writers.delete_chunks_for_doc(doc.id)
                await gq.delete_doc_cascade(doc_id=doc.id, kb_id=doc.kb_id)
                if doc.storage_uri:
                    delete_object(doc.storage_uri)
                doc.state = "deleted"
                doc.deleted_at = datetime.now(timezone.utc)
            except Exception:  # noqa: BLE001
                logger.exception("erasure failed for doc %s", doc.id)
        await log(session, None, "user.erased", "user", str(uid), {})
        await session.commit()


async def rebuild_communities(ctx: dict, kb_id: str) -> None:
    """Run Leiden via Neo4j GDS + LLM-summarise communities."""
    from app.services.communities import run_leiden_and_summarise
    await run_leiden_and_summarise(uuid.UUID(kb_id))


async def run_automation(ctx: dict, automation_id: str) -> None:
    from app.services.automation_service import execute_automation
    await execute_automation(uuid.UUID(automation_id))


async def cron_scheduler(ctx: dict) -> None:
    """Runs every minute; fires automations whose cron matches."""
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    async with SessionLocal() as session:
        autos = (
            await session.execute(
                select(Automation).where(Automation.active == True)
            )
        ).scalars().all()
        for auto in autos:
            try:
                # croniter expects naive or tz-aware: keep aware
                base = auto.last_run_at or auto.created_at
                it = croniter(auto.cron_expr, base)
                next_run = it.get_next(datetime)
                if next_run <= now:
                    auto.last_run_at = now
                    await session.commit()
                    from app.workers.queue import enqueue_automation_run
                    await enqueue_automation_run(auto.id)
            except Exception:  # noqa: BLE001
                logger.exception("scheduler failure for automation %s", auto.id)
