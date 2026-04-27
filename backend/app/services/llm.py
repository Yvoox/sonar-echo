"""Thin wrapper around the OpenAI SDK with optional dev-time fallback."""
from __future__ import annotations

import hashlib
from typing import Any

from openai import AsyncOpenAI

from app.config import settings

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI | None:
    global _client
    if not settings.openai_api_key:
        return None
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def chat_complete(
    *,
    system: str,
    messages: list[dict[str, Any]],
    model: str | None = None,
    response_format: dict | None = None,
    temperature: float = 0.2,
    tools: list[dict] | None = None,
    tool_choice: str | dict | None = None,
) -> dict:
    """Returns {"text": str, "tool_calls": list, "tokens_in": int, "tokens_out": int}."""
    client = _get_client()
    model = model or settings.openai_model_generation
    if client is None:
        return _fallback_chat(system, messages)
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": system}, *messages],
        "temperature": temperature,
    }
    if response_format:
        payload["response_format"] = response_format
    if tools:
        payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
    resp = await client.chat.completions.create(**payload)
    msg = resp.choices[0].message
    return {
        "text": msg.content or "",
        "tool_calls": [
            {"name": tc.function.name, "arguments": tc.function.arguments}
            for tc in (msg.tool_calls or [])
        ],
        "tokens_in": resp.usage.prompt_tokens if resp.usage else 0,
        "tokens_out": resp.usage.completion_tokens if resp.usage else 0,
        "model": resp.model,
    }


async def embed(texts: list[str]) -> tuple[list[list[float]], int]:
    """Returns (embeddings, tokens_in)."""
    if not texts:
        return [], 0
    client = _get_client()
    if client is None:
        return [_deterministic_embedding(t) for t in texts], 0
    resp = await client.embeddings.create(
        model=settings.openai_embedding_model, input=texts
    )
    vecs = [d.embedding for d in resp.data]
    return vecs, resp.usage.prompt_tokens if resp.usage else 0


def _deterministic_embedding(text: str) -> list[float]:
    """Stable hash-based fallback for tests / dev-without-key."""
    dim = settings.openai_embedding_dim
    h = hashlib.sha256(text.encode("utf-8")).digest()
    # tile bytes → floats in [-1, 1)
    out: list[float] = []
    while len(out) < dim:
        for b in h:
            out.append((b - 128) / 128.0)
            if len(out) == dim:
                break
        h = hashlib.sha256(h).digest()
    # normalise (cosine-friendly)
    s = sum(x * x for x in out) ** 0.5 or 1.0
    return [x / s for x in out]


def _fallback_chat(system: str, messages: list[dict]) -> dict:
    last = messages[-1]["content"] if messages else ""
    return {
        "text": f"[fallback-no-llm] {last[:200]}",
        "tool_calls": [],
        "tokens_in": 0,
        "tokens_out": 0,
        "model": "fallback",
    }


# Cost map (USD per 1M tokens) — best-effort, kept in code for visibility
PRICES = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "text-embedding-3-small": (0.02, 0.0),
}


def cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    base = next((v for k, v in PRICES.items() if model.startswith(k)), (0.0, 0.0))
    return tokens_in / 1_000_000 * base[0] + tokens_out / 1_000_000 * base[1]
