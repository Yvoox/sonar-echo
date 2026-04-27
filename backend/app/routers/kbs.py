import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_session
from app.models import KnowledgeBase, KBMembership, User
from app.schemas.kb import KBCreate, KBMemberIn, KBMemberOut, KBOut
from app.security.jwt_auth import get_current_user
from app.security.permissions import require_kb_role
from app.services.audit import log

router = APIRouter(prefix="/api/v1/kbs", tags=["kbs"])


@router.get("", response_model=list[KBOut])
async def list_kbs(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[KBOut]:
    if user.is_global_admin:
        kbs = (
            await session.execute(
                select(KnowledgeBase).where(KnowledgeBase.org_id == user.org_id)
            )
        ).scalars().all()
    else:
        kbs = (
            await session.execute(
                select(KnowledgeBase)
                .join(KBMembership, KBMembership.kb_id == KnowledgeBase.id)
                .where(KBMembership.user_id == user.id)
            )
        ).scalars().all()
    return [KBOut.model_validate(k) for k in kbs]


@router.post("", response_model=KBOut, status_code=201)
async def create_kb(
    body: KBCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> KBOut:
    kb = KnowledgeBase(org_id=user.org_id, name=body.name, description=body.description)
    session.add(kb)
    await session.flush()
    session.add(KBMembership(user_id=user.id, kb_id=kb.id, role="admin"))
    await log(session, user.id, "kb.created", "kb", str(kb.id), {"name": body.name})
    await session.commit()
    await session.refresh(kb)
    return KBOut.model_validate(kb)


@router.get("/{kb_id}", response_model=KBOut)
async def get_kb(
    kb_id: uuid.UUID,
    _: tuple = Depends(require_kb_role("reader")),
    session: AsyncSession = Depends(get_session),
) -> KBOut:
    kb = await session.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "kb not found")
    return KBOut.model_validate(kb)


@router.post("/{kb_id}/members", response_model=KBMemberOut, status_code=201)
async def add_member(
    kb_id: uuid.UUID,
    body: KBMemberIn,
    ctx: tuple[User, KBMembership] = Depends(require_kb_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> KBMemberOut:
    actor, _ = ctx
    if body.role not in ("admin", "editor", "reader", "proposer"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid role")
    target = (
        await session.execute(
            select(User).where(User.org_id == actor.org_id, User.email == body.email)
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found in org (must be registered first)")
    existing = (
        await session.execute(
            select(KBMembership).where(
                KBMembership.user_id == target.id, KBMembership.kb_id == kb_id
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.role = body.role
        m = existing
    else:
        m = KBMembership(user_id=target.id, kb_id=kb_id, role=body.role)
        session.add(m)
    await log(session, actor.id, "kb.member.added", "kb", str(kb_id),
              {"user_id": str(target.id), "role": body.role})
    await session.commit()
    return KBMemberOut(user_id=target.id, kb_id=kb_id, role=body.role, email=target.email)


@router.get("/{kb_id}/members", response_model=list[KBMemberOut])
async def list_members(
    kb_id: uuid.UUID,
    _: tuple = Depends(require_kb_role("reader")),
    session: AsyncSession = Depends(get_session),
) -> list[KBMemberOut]:
    rows = (
        await session.execute(
            select(KBMembership, User.email)
            .join(User, User.id == KBMembership.user_id)
            .where(KBMembership.kb_id == kb_id)
        )
    ).all()
    return [
        KBMemberOut(user_id=m.user_id, kb_id=m.kb_id, role=m.role, email=email)
        for (m, email) in rows
    ]
