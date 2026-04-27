"""Minimal MCP HTTP transport mounted on `/mcp`.

Implements the JSON-RPC subset required by MCP clients:
  - initialize
  - tools/list
  - tools/call

Authentication: HTTP Authorization: Bearer <jwt> (same JWT as REST API).
The JWT subject identifies the user; tool execution scopes by user's
KB memberships.
"""
from __future__ import annotations

import json
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_session
from app.models import Automation, Community, KBMembership, KnowledgeBase, User
from app.retrieval import hybrid
from app.security.jwt_auth import get_current_user
from app.workers.queue import enqueue_automation_run

router = APIRouter(prefix="/mcp", tags=["mcp"])


# ─── Tool descriptors ────────────────────────────────────────────────
def _tool_descriptors() -> list[dict]:
    return [
        {
            "name": "list_kbs",
            "description": "List knowledge bases the current user can access.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "search_kb",
            "description": "Search a KB; returns chunks + entities + timeline + communities.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kb_id": {"type": "string"},
                    "query": {"type": "string"},
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                    "k": {"type": "integer", "default": 10},
                    "include_superseded": {"type": "boolean", "default": False},
                },
                "required": ["kb_id", "query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_entity_timeline",
            "description": "Return temporal events for an entity (sorted desc).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kb_id": {"type": "string"},
                    "entity_id": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "include_superseded": {"type": "boolean", "default": False},
                },
                "required": ["kb_id", "entity_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "list_communities",
            "description": "List Leiden communities for a KB.",
            "inputSchema": {
                "type": "object",
                "properties": {"kb_id": {"type": "string"}},
                "required": ["kb_id"],
            },
        },
        {
            "name": "get_community",
            "description": "Get a specific community by id.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kb_id": {"type": "string"},
                    "community_id": {"type": "string"},
                },
                "required": ["kb_id", "community_id"],
            },
        },
        {
            "name": "list_automations",
            "description": "List automations owned by the current user.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "trigger_automation",
            "description": "Trigger an automation immediately (still respects active flag).",
            "inputSchema": {
                "type": "object",
                "properties": {"automation_id": {"type": "string"}},
                "required": ["automation_id"],
            },
        },
    ]


# ─── Tool dispatch ───────────────────────────────────────────────────
async def _call_tool(
    name: str,
    args: dict,
    *,
    user: User,
    session: AsyncSession,
) -> dict:
    if name == "list_kbs":
        return await _list_kbs(user, session)
    if name == "search_kb":
        return await _search_kb(user, session, args)
    if name == "get_entity_timeline":
        return await _entity_timeline(user, session, args)
    if name == "list_communities":
        return await _list_communities(user, session, args)
    if name == "get_community":
        return await _get_community(user, session, args)
    if name == "list_automations":
        return await _list_automations(user, session)
    if name == "trigger_automation":
        return await _trigger_automation(user, session, args)
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown tool: {name}")


async def _accessible_kb_ids(user: User, session: AsyncSession) -> set[uuid.UUID]:
    if user.is_global_admin:
        rows = (
            await session.execute(
                select(KnowledgeBase.id).where(KnowledgeBase.org_id == user.org_id)
            )
        ).scalars().all()
        return set(rows)
    rows = (
        await session.execute(
            select(KBMembership.kb_id).where(KBMembership.user_id == user.id)
        )
    ).scalars().all()
    return set(rows)


async def _check_kb_access(user: User, session: AsyncSession, kb_id: uuid.UUID) -> None:
    accessible = await _accessible_kb_ids(user, session)
    if kb_id not in accessible:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "no access to this KB")


async def _list_kbs(user: User, session: AsyncSession) -> dict:
    accessible = await _accessible_kb_ids(user, session)
    if not accessible:
        return {"kbs": []}
    rows = (
        await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id.in_(accessible))
        )
    ).scalars().all()
    return {"kbs": [{"id": str(k.id), "name": k.name, "description": k.description} for k in rows]}


async def _search_kb(user: User, session: AsyncSession, args: dict) -> dict:
    kb_id = uuid.UUID(args["kb_id"])
    await _check_kb_access(user, session, kb_id)
    dr = None
    if args.get("date_from") and args.get("date_to"):
        dr = (date.fromisoformat(args["date_from"]), date.fromisoformat(args["date_to"]))
    res = await hybrid.search(
        kb_id=kb_id,
        query=args["query"],
        date_range=dr,
        k=int(args.get("k", 10)),
        include_superseded=bool(args.get("include_superseded", False)),
    )
    return json.loads(res.model_dump_json())


async def _entity_timeline(user: User, session: AsyncSession, args: dict) -> dict:
    from app.graph import queries as gq
    kb_id = uuid.UUID(args["kb_id"])
    await _check_kb_access(user, session, kb_id)
    start = date.fromisoformat(args["start"]) if args.get("start") else None
    end = date.fromisoformat(args["end"]) if args.get("end") else None
    events = await gq.entity_timeline(
        entity_id=args["entity_id"],
        start=start,
        end=end,
        include_superseded=bool(args.get("include_superseded", False)),
    )
    return {"events": events}


async def _list_communities(user: User, session: AsyncSession, args: dict) -> dict:
    kb_id = uuid.UUID(args["kb_id"])
    await _check_kb_access(user, session, kb_id)
    rows = (
        await session.execute(select(Community).where(Community.kb_id == kb_id))
    ).scalars().all()
    return {"communities": [
        {"id": str(c.id), "label": c.label, "summary": c.summary,
         "member_entity_ids": c.member_entity_ids}
        for c in rows
    ]}


async def _get_community(user: User, session: AsyncSession, args: dict) -> dict:
    kb_id = uuid.UUID(args["kb_id"])
    await _check_kb_access(user, session, kb_id)
    cid = uuid.UUID(args["community_id"])
    c = await session.get(Community, cid)
    if c is None or c.kb_id != kb_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "community not found")
    return {
        "id": str(c.id), "label": c.label, "summary": c.summary,
        "member_entity_ids": c.member_entity_ids, "level": c.level,
    }


async def _list_automations(user: User, session: AsyncSession) -> dict:
    rows = (
        await session.execute(
            select(Automation).where(Automation.owner_id == user.id)
        )
    ).scalars().all()
    return {"automations": [
        {"id": str(a.id), "name": a.name, "kb_id": str(a.kb_id),
         "cron_expr": a.cron_expr, "active": a.active}
        for a in rows
    ]}


async def _trigger_automation(user: User, session: AsyncSession, args: dict) -> dict:
    aid = uuid.UUID(args["automation_id"])
    a = await session.get(Automation, aid)
    if a is None or (a.owner_id != user.id and not user.is_global_admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "automation not found")
    await enqueue_automation_run(aid)
    return {"status": "queued"}


# ─── JSON-RPC endpoint ───────────────────────────────────────────────
@router.post("")
async def jsonrpc_endpoint(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    rpc_id = body.get("id")
    method = body.get("method")

    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "sonar-echo", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            }
        elif method == "tools/list":
            result = {"tools": _tool_descriptors()}
        elif method == "tools/call":
            params = body.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})
            tool_result = await _call_tool(name, args, user=user, session=session)
            result = {
                "content": [{"type": "text", "text": json.dumps(tool_result, default=str)}],
                "isError": False,
            }
        else:
            return {"jsonrpc": "2.0", "id": rpc_id,
                    "error": {"code": -32601, "message": f"method not found: {method}"}}
    except HTTPException as e:
        return {"jsonrpc": "2.0", "id": rpc_id,
                "error": {"code": -32000, "message": e.detail, "data": {"status": e.status_code}}}
    except Exception as exc:  # noqa: BLE001
        return {"jsonrpc": "2.0", "id": rpc_id,
                "error": {"code": -32000, "message": str(exc)}}

    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}
