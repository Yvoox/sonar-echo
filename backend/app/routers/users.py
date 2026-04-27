import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_session
from app.models import User
from app.security.gdpr import usage_summary
from app.security.jwt_auth import get_current_user, require_global_admin
from app.services.audit import log
from app.workers.queue import enqueue_user_erasure

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/{user_id}/usage")
async def user_usage(
    user_id: uuid.UUID = Path(...),
    actor: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if actor.id != user_id and not actor.is_global_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not allowed")
    return await usage_summary(session, user_id)


@router.delete("/{user_id}/erase", status_code=202)
async def erase_user(
    user_id: uuid.UUID = Path(...),
    admin: User = Depends(require_global_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    await log(session, admin.id, "user.erase.requested", "user", str(user_id), {})
    await session.commit()
    await enqueue_user_erasure(user_id)
    return {"status": "queued", "user_id": str(user_id)}
