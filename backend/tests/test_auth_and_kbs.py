"""Smoke tests against the FastAPI ASGI app (no external services needed).

These tests skip gracefully if Postgres is unreachable; they verify routing
and Pydantic schemas only, not full E2E.
"""
import pytest


@pytest.mark.asyncio
async def test_healthz(client) -> None:
    r = await client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["env"] in ("dev", "prod")


@pytest.mark.asyncio
async def test_login_unauthenticated(client) -> None:
    r = await client.post("/api/v1/auth/login",
                          json={"email": "nobody@example.com", "password": "x" * 8})
    assert r.status_code in (401, 500, 503)  # 5xx if DB not reachable in test env


@pytest.mark.asyncio
async def test_protected_route_requires_jwt(client) -> None:
    r = await client.get("/api/v1/kbs")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_mcp_requires_jwt(client) -> None:
    r = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert r.status_code == 401
