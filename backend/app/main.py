"""FastAPI app entry."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db.minio import ensure_bucket
from app.db.neo4j import close_driver
from app.db.qdrant import close_client, ensure_collection
from app.graph.queries import ensure_constraints
from app.routers import auth, automations, chat, documents, entities, gems, kbs, search, users
from app.security.rate_limiter import global_limiter

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # init external dependencies (best-effort, don't crash if a service is briefly unavailable)
    try:
        ensure_bucket()
    except Exception:  # noqa: BLE001
        logger.warning("MinIO bucket init failed (will retry on first upload)", exc_info=True)
    try:
        await ensure_collection()
    except Exception:  # noqa: BLE001
        logger.warning("Qdrant collection init failed", exc_info=True)
    try:
        await ensure_constraints()
    except Exception:  # noqa: BLE001
        logger.warning("Neo4j constraints init failed", exc_info=True)
    yield
    await close_driver()
    await close_client()


app = FastAPI(
    title="Sonar-Echo",
    version="0.1.0",
    description="RAG Graph multi-tenant avec dimension temporelle native.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin] if settings.frontend_origin else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_rate_limit(request: Request, call_next):
    """Apply per-user rate limit on authenticated requests."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        try:
            from app.security.jwt_auth import decode_token
            payload = decode_token(auth_header.split(" ", 1)[1])
            global_limiter.check(f"user:{payload['sub']}")
        except Exception:  # noqa: BLE001
            pass  # let the route handler return the proper 401
    return await call_next(request)


@app.exception_handler(Exception)
async def fallback_handler(request: Request, exc: Exception):
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True, "env": settings.app_env, "version": "0.1.0"}


# Routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(kbs.router)
app.include_router(documents.router)
app.include_router(search.router)
app.include_router(entities.router)
app.include_router(chat.router)
app.include_router(gems.router)
app.include_router(automations.router)

# MCP
from app.mcp.server import router as mcp_router  # noqa: E402

app.include_router(mcp_router)
