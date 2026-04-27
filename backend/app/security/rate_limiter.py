import time
from collections import defaultdict
from threading import Lock

from fastapi import Depends, HTTPException, Request, status

from app.config import settings
from app.models import User
from app.security.jwt_auth import get_current_user


class _Bucket:
    def __init__(self) -> None:
        self.count = 0
        self.window_start = time.monotonic()


class InMemoryRateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self.buckets: dict[str, _Bucket] = defaultdict(_Bucket)
        self.lock = Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self.lock:
            b = self.buckets[key]
            if now - b.window_start >= 60:
                b.count = 0
                b.window_start = now
            b.count += 1
            if b.count > self.per_minute:
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"rate limit exceeded ({self.per_minute}/min)",
                )


global_limiter = InMemoryRateLimiter(settings.rate_limit_per_minute)
ingestion_limiter = InMemoryRateLimiter(settings.ingestion_rate_limit_per_minute)


async def enforce_global_rate_limit(
    request: Request, user: User = Depends(get_current_user)
) -> User:
    global_limiter.check(f"user:{user.id}")
    return user


async def enforce_ingestion_rate_limit(user: User = Depends(get_current_user)) -> User:
    ingestion_limiter.check(f"user:{user.id}:ingest")
    return user
