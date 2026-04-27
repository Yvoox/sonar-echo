import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_session
from app.models import Gem, KBMembership, User
from app.schemas.gem import GemIn, GemOut
from app.security.jwt_auth import get_current_user

router = APIRouter(prefix="/api/v1/gems", tags=["gems"])


@router.get("", response_model=list[GemOut])
async def list_gems(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[GemOut]:
    # Visible gems: owned + kb-shared (where user is member) + org-shared
    member_kb_ids = (
        await session.execute(
            select(KBMembership.kb_id).where(KBMembership.user_id == user.id)
        )
    ).scalars().all()
    stmt = select(Gem).where(
        or_(
            Gem.owner_id == user.id,
            (Gem.visibility == "kb") & (Gem.kb_id.in_(member_kb_ids)),
            (Gem.visibility == "org"),
        )
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [GemOut.model_validate(g) for g in rows]


@router.post("", response_model=GemOut, status_code=201)
async def create_gem(
    body: GemIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> GemOut:
    if body.visibility not in ("private", "kb", "org"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid visibility")
    gem = Gem(
        owner_id=user.id,
        kb_id=body.kb_id,
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        config=body.config,
        visibility=body.visibility,
    )
    session.add(gem)
    await session.commit()
    await session.refresh(gem)
    return GemOut.model_validate(gem)


@router.get("/{gem_id}", response_model=GemOut)
async def get_gem(
    gem_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> GemOut:
    gem = await session.get(Gem, gem_id)
    if gem is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "gem not found")
    return GemOut.model_validate(gem)


@router.patch("/{gem_id}", response_model=GemOut)
async def update_gem(
    gem_id: uuid.UUID,
    body: GemIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> GemOut:
    gem = await session.get(Gem, gem_id)
    if gem is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "gem not found")
    if gem.owner_id != user.id and not user.is_global_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your gem")
    gem.name = body.name
    gem.description = body.description
    gem.system_prompt = body.system_prompt
    gem.config = body.config
    gem.visibility = body.visibility
    gem.kb_id = body.kb_id
    await session.commit()
    await session.refresh(gem)
    return GemOut.model_validate(gem)


@router.delete("/{gem_id}", status_code=204)
async def delete_gem(
    gem_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    gem = await session.get(Gem, gem_id)
    if gem is None:
        return
    if gem.owner_id != user.id and not user.is_global_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your gem")
    await session.delete(gem)
    await session.commit()
