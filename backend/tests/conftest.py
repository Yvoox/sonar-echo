import asyncio
import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Ensure dev fallbacks (no API keys needed for unit tests)
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("MISTRAL_API_KEY", "")
os.environ.setdefault("APP_ENV", "dev")

# Use a separate test DB if available; default falls back to local docker-compose
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://sonar:change_me@localhost:5433/sonar_echo",
)


@pytest_asyncio.fixture
async def client():
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def fixture_pdf() -> Path:
    return Path(__file__).parent / "fixtures" / "cm_mairie_sample.txt"
