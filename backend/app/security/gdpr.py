"""GDPR helpers (erasure cascade is implemented in workers/tasks.py:erase_user)."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatMessage, ChatConversation, IngestionJob, Document


async def usage_summary(session: AsyncSession, user_id: uuid.UUID) -> dict:
    """Return cumulative token / cost stats for a user (LLM spend visibility)."""
    chat_row = (
        await session.execute(
            select(
                func.coalesce(func.sum(ChatMessage.tokens_in), 0),
                func.coalesce(func.sum(ChatMessage.tokens_out), 0),
                func.coalesce(func.sum(ChatMessage.cost_usd), 0.0),
            )
            .join(ChatConversation, ChatConversation.id == ChatMessage.conversation_id)
            .where(ChatConversation.user_id == user_id)
        )
    ).one()
    ing_row = (
        await session.execute(
            select(
                func.coalesce(func.sum(IngestionJob.token_usage_in), 0),
                func.coalesce(func.sum(IngestionJob.token_usage_out), 0),
                func.coalesce(func.sum(IngestionJob.cost_usd), 0.0),
            )
            .join(Document, Document.id == IngestionJob.document_id)
            .where(Document.created_by == user_id)
        )
    ).one()
    return {
        "user_id": str(user_id),
        "chat": {
            "tokens_in": int(chat_row[0]),
            "tokens_out": int(chat_row[1]),
            "cost_usd": float(chat_row[2]),
        },
        "ingestion": {
            "tokens_in": int(ing_row[0]),
            "tokens_out": int(ing_row[1]),
            "cost_usd": float(ing_row[2]),
        },
        "total_cost_usd": float(chat_row[2]) + float(ing_row[2]),
    }
