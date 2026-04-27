"""Helpers exposés à l'API pour enqueuer des tâches Arq."""
import uuid
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings

from app.config import settings

_pool = None


async def _get_pool():
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool


async def enqueue_ingestion(job_id: uuid.UUID, document_id: uuid.UUID) -> None:
    pool = await _get_pool()
    await pool.enqueue_job(
        "ingest_document",
        str(job_id),
        str(document_id),
        _job_id=f"ingest:{job_id}",
    )


async def enqueue_doc_cleanup(document_id: uuid.UUID, hard: bool = False) -> None:
    pool = await _get_pool()
    await pool.enqueue_job(
        "cleanup_document",
        str(document_id),
        hard,
        _job_id=f"cleanup:{document_id}",
    )


async def enqueue_user_erasure(user_id: uuid.UUID) -> None:
    pool = await _get_pool()
    await pool.enqueue_job("erase_user", str(user_id), _job_id=f"erase:{user_id}")


async def enqueue_automation_run(automation_id: uuid.UUID) -> None:
    pool = await _get_pool()
    await pool.enqueue_job("run_automation", str(automation_id))


async def enqueue_leiden(kb_id: uuid.UUID) -> None:
    pool = await _get_pool()
    await pool.enqueue_job("rebuild_communities", str(kb_id), _job_id=f"leiden:{kb_id}")


async def enqueue_kwargs(name: str, *args: Any, **kwargs: Any) -> None:
    pool = await _get_pool()
    await pool.enqueue_job(name, *args, **kwargs)
