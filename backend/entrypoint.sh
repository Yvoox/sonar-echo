#!/bin/sh
# Single entrypoint for the backend container.
# Branches on APP_ENV (dev|prod) — same image, same compose file.

set -e

# Wait briefly for Postgres (compose healthcheck already does this, but
# `alembic upgrade head` is sensitive to it on first boot).
echo "[entrypoint] APP_ENV=${APP_ENV:-dev}"
echo "[entrypoint] running alembic upgrade head…"
alembic upgrade head

case "${APP_ENV:-dev}" in
  prod)
    echo "[entrypoint] starting uvicorn (prod, ${UVICORN_WORKERS:-4} workers)…"
    exec uvicorn app.main:app \
      --host 0.0.0.0 --port 8000 \
      --workers "${UVICORN_WORKERS:-4}" \
      --proxy-headers --forwarded-allow-ips='*'
    ;;
  *)
    echo "[entrypoint] starting uvicorn (dev, --reload)…"
    exec uvicorn app.main:app \
      --host 0.0.0.0 --port 8000 \
      --reload
    ;;
esac
