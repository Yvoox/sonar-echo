"""Reranker — naive score-based fallback.

In v1 we don't ship a heavy cross-encoder by default (the bge-reranker model
weights add ~600MB to the image). The protocol below lets you swap in a real
cross-encoder later without changing the call sites.
"""
from __future__ import annotations

from typing import Protocol


class Reranker(Protocol):
    async def rerank(self, query: str, candidates: list[dict]) -> list[dict]: ...


class IdentityReranker:
    """Sort by existing 'score' field; deterministic, no extra cost."""

    async def rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        return sorted(candidates, key=lambda c: c.get("score", 0.0), reverse=True)


def get_reranker() -> Reranker:
    return IdentityReranker()
