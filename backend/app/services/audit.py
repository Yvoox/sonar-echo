import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def log(
    session: AsyncSession,
    actor_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=payload or {},
        )
    )
