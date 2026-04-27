import uuid

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_session
from app.models import Automation, KBMembership, User
from app.notifications import channel as channels
import app.notifications.email_smtp  # noqa: F401  registers SMTP channel
from app.schemas.automation import AutomationIn, AutomationOut
from app.security.jwt_auth import get_current_user
from app.workers.queue import enqueue_automation_run

router = APIRouter(prefix="/api/v1/automations", tags=["automations"])


@router.get("", response_model=list[AutomationOut])
async def list_automations(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[AutomationOut]:
    rows = (
        await session.execute(
            select(Automation).where(Automation.owner_id == user.id)
        )
    ).scalars().all()
    return [AutomationOut.model_validate(a) for a in rows]


@router.post("", response_model=AutomationOut, status_code=201)
async def create_automation(
    body: AutomationIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AutomationOut:
    if not croniter.is_valid(body.cron_expr):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cron expression")
    if body.channel_type not in channels.types():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"channel '{body.channel_type}' not registered. Available: {channels.types()}",
        )
    # check user has access to the KB
    has_access = (
        await session.execute(
            select(KBMembership).where(
                KBMembership.user_id == user.id, KBMembership.kb_id == body.kb_id
            )
        )
    ).scalar_one_or_none()
    if has_access is None and not user.is_global_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "no access to this KB")

    auto = Automation(
        owner_id=user.id,
        kb_id=body.kb_id,
        gem_id=body.gem_id,
        name=body.name,
        user_prompt=body.user_prompt,
        cron_expr=body.cron_expr,
        channel_type=body.channel_type,
        channel_config=body.channel_config,
        active=body.active,
    )
    session.add(auto)
    await session.commit()
    await session.refresh(auto)
    return AutomationOut.model_validate(auto)


@router.patch("/{automation_id}", response_model=AutomationOut)
async def update_automation(
    automation_id: uuid.UUID,
    body: AutomationIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AutomationOut:
    auto = await session.get(Automation, automation_id)
    if auto is None or (auto.owner_id != user.id and not user.is_global_admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "automation not found")
    if not croniter.is_valid(body.cron_expr):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cron expression")
    auto.name = body.name
    auto.user_prompt = body.user_prompt
    auto.cron_expr = body.cron_expr
    auto.channel_type = body.channel_type
    auto.channel_config = body.channel_config
    auto.active = body.active
    auto.kb_id = body.kb_id
    auto.gem_id = body.gem_id
    await session.commit()
    await session.refresh(auto)
    return AutomationOut.model_validate(auto)


@router.delete("/{automation_id}", status_code=204)
async def delete_automation(
    automation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    auto = await session.get(Automation, automation_id)
    if auto is None:
        return
    if auto.owner_id != user.id and not user.is_global_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your automation")
    await session.delete(auto)
    await session.commit()


@router.post("/{automation_id}/trigger", status_code=202)
async def trigger_automation(
    automation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    auto = await session.get(Automation, automation_id)
    if auto is None or (auto.owner_id != user.id and not user.is_global_admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "automation not found")
    await enqueue_automation_run(automation_id)
    return {"status": "queued", "automation_id": str(automation_id)}
