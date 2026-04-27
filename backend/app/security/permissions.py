import uuid

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_session
from app.models import KBMembership, User
from app.security.jwt_auth import get_current_user

ROLE_RANK = {"reader": 0, "proposer": 1, "editor": 2, "admin": 3}


def require_kb_role(min_role: str):
    async def dep(
        kb_id: uuid.UUID = Path(...),
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> tuple[User, KBMembership]:
        if user.is_global_admin:
            # synthétique: global admin a un rôle admin virtuel sur toutes les KBs
            membership = KBMembership(user_id=user.id, kb_id=kb_id, role="admin")
            return user, membership
        m = (
            await session.execute(
                select(KBMembership).where(
                    KBMembership.user_id == user.id, KBMembership.kb_id == kb_id
                )
            )
        ).scalar_one_or_none()
        if m is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "no access to this KB")
        if ROLE_RANK[m.role] < ROLE_RANK[min_role]:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"role '{min_role}' required, have '{m.role}'"
            )
        return user, m

    return dep
