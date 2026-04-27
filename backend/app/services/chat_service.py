"""Chat generation: takes a SearchOut + history, calls LLM with citations enforced."""
from __future__ import annotations

import json
import uuid
from typing import AsyncIterator

from app.config import settings
from app.schemas.retrieval import ChatResponseOut, SearchOut
from app.services.llm import chat_complete, cost_usd

SYSTEM_PROMPT = """\
Tu es l'assistant Sonar-Echo. Tu réponds en t'appuyant UNIQUEMENT sur le contexte fourni
(chunks, communautés, timeline). Chaque affirmation factuelle doit être suivie d'un
marqueur de citation au format [n] où n est l'index 1-based du chunk dans le contexte.
Si le contexte ne suffit pas, dis-le clairement. Réponds en français, en restant concis
et structuré (titres, puces si pertinent). Mentionne toujours les dates (sources_date) quand tu cites.
"""


def build_context(search: SearchOut, system_prompt_extra: str | None = None) -> str:
    sys = SYSTEM_PROMPT
    if system_prompt_extra:
        sys = sys + "\n\nInstructions Gem :\n" + system_prompt_extra.strip()
    return sys


def render_context_block(search: SearchOut) -> str:
    parts: list[str] = []
    parts.append("=== CHUNKS ===")
    for i, c in enumerate(search.chunks, start=1):
        sd = c.citation.source_date.isoformat() if c.citation.source_date else "?"
        parts.append(
            f"[{i}] (doc: {c.citation.doc_title} — {sd} — page {c.citation.page or '?'})\n{c.text}"
        )
    if search.communities:
        parts.append("\n=== COMMUNAUTÉS ===")
        for c in search.communities:
            parts.append(f"- {c.label}: {c.summary}")
    if search.timeline:
        parts.append("\n=== TIMELINE ===")
        for t in search.timeline[:20]:
            parts.append(
                f"- {t.entity_id} -[{t.type}]- {t.related_entity_id or '?'} "
                f"({t.valid_from or '?'} → {t.valid_to or '?'}, src={t.source_doc_title or '?'})"
            )
    if search.entities:
        parts.append("\n=== ENTITES ===")
        for e in search.entities[:10]:
            parts.append(f"- {e.id}: {e.canonical_name} ({e.type})")
    return "\n".join(parts)


async def generate(
    *,
    user_query: str,
    search: SearchOut,
    history: list[dict] | None = None,
    system_prompt_extra: str | None = None,
) -> dict:
    sys = build_context(search, system_prompt_extra)
    ctx = render_context_block(search)
    messages: list[dict] = []
    if history:
        messages.extend(history[-10:])
    messages.append({
        "role": "user",
        "content": f"CONTEXTE :\n{ctx}\n\n---\n\nQUESTION : {user_query}",
    })
    res = await chat_complete(
        system=sys,
        messages=messages,
        model=settings.openai_model_generation,
        temperature=0.2,
    )
    return {
        "text": res["text"],
        "tokens_in": res["tokens_in"],
        "tokens_out": res["tokens_out"],
        "cost_usd": cost_usd(res["model"], res["tokens_in"], res["tokens_out"]),
    }
