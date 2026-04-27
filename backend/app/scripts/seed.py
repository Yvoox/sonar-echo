"""Seed an initial org + global-admin user. Idempotent.

Usage (inside the backend container):
    python -m app.scripts.seed --email admin@example.com --password change_me_too
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.db.postgres import SessionLocal
from app.models import Organization, User
from app.security.jwt_auth import hash_password


async def seed(email: str, password: str, org_name: str) -> None:
    async with SessionLocal() as session:
        org = (
            await session.execute(select(Organization).where(Organization.name == org_name))
        ).scalar_one_or_none()
        if org is None:
            org = Organization(name=org_name)
            session.add(org)
            await session.flush()

        user = (
            await session.execute(
                select(User).where(User.org_id == org.id, User.email == email)
            )
        ).scalar_one_or_none()
        if user is None:
            user = User(
                org_id=org.id,
                email=email,
                password_hash=hash_password(password),
                is_global_admin=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            print(f"Created admin user {email} in org '{org.name}' (id={user.id})")
        else:
            print(f"User {email} already exists (id={user.id})")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--org", default="Sonar-Echo Default")
    args = p.parse_args()
    asyncio.run(seed(args.email, args.password, args.org))


if __name__ == "__main__":
    main()
