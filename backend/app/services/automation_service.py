"""Automation execution: load gem + retrieval + LLM + deliver via channel."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import SessionLocal
from app.models import Automation, Gem
from app.notifications import channel as channels
import app.notifications.email_smtp  # noqa: F401  ensures registration
from app.retrieval import hybrid
from app.services import chat_service
from app.services.audit import log

logger = logging.getLogger(__name__)


async def execute_automation(automation_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        auto = await session.get(Automation, automation_id)
        if auto is None or not auto.active:
            return
        gem = await session.get(Gem, auto.gem_id)
        if gem is None:
            logger.error("gem missing for automation %s", automation_id)
            return

        try:
            search = await hybrid.search(
                kb_id=auto.kb_id, query=auto.user_prompt, k=10
            )
            res = await chat_service.generate(
                user_query=auto.user_prompt,
                search=search,
                history=None,
                system_prompt_extra=gem.system_prompt,
            )

            channel = channels.get(auto.channel_type)
            await channel.deliver(
                subject=f"[Sonar-Echo] {auto.name}",
                body=res["text"],
                config=auto.channel_config,
            )
            auto.last_run_at = datetime.now(timezone.utc)
            await log(session, auto.owner_id, "automation.run", "automation",
                      str(auto.id),
                      {"tokens_in": res["tokens_in"], "tokens_out": res["tokens_out"],
                       "cost_usd": res["cost_usd"]})
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.exception("automation %s failed", automation_id)
            await log(session, auto.owner_id, "automation.failed", "automation",
                      str(auto.id), {"error": str(exc)[:500]})
            await session.commit()
