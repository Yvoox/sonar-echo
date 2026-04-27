import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_session
from app.models import Organization, User
from app.schemas.auth import LoginIn, RegisterIn, TokenOut, UserOut
from app.security.jwt_auth import (
    create_access_token,
    get_current_user,
    hash_password,
    require_global_admin,
    verify_password,
)
from app.services.audit import log

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(
    body: RegisterIn,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_global_admin),
) -> UserOut:
    if body.org_id is None:
        if not body.org_name:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "org_id or org_name required")
        org = Organization(name=body.org_name)
        session.add(org)
        await session.flush()
        org_id = org.id
    else:
        org = await session.get(Organization, body.org_id)
        if org is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "organization not found")
        org_id = org.id

    existing = (
        await session.execute(
            select(User).where(User.org_id == org_id, User.email == body.email)
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already used in this org")

    user = User(
        org_id=org_id,
        email=body.email,
        password_hash=hash_password(body.password),
        is_global_admin=body.is_global_admin,
    )
    session.add(user)
    await session.flush()
    await log(session, _admin.id, "user.created", "user", str(user.id),
              {"email": body.email, "org_id": str(org_id)})
    await session.commit()
    await session.refresh(user)
    return UserOut.model_validate(user)


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, session: AsyncSession = Depends(get_session)) -> TokenOut:
    user = (
        await session.execute(
            select(User).where(User.email == body.email, User.erased == False)
        )
    ).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    token = create_access_token(user.id, user.org_id, user.is_global_admin)
    return TokenOut(
        access_token=token,
        user_id=user.id,
        org_id=user.org_id,
        is_global_admin=user.is_global_admin,
    )


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
