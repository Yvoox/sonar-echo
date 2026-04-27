"""Arq worker settings."""
from arq import cron
from arq.connections import RedisSettings

from app.config import settings
from app.workers import tasks


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [
        tasks.ingest_document,
        tasks.cleanup_document,
        tasks.erase_user,
        tasks.rebuild_communities,
        tasks.run_automation,
    ]
    cron_jobs = [
        cron(tasks.cron_scheduler, second=0),
    ]
    job_timeout = 60 * 30  # 30 min for heavy ingestion jobs
    max_jobs = 4
    keep_result = 60 * 60 * 24  # 1 day
