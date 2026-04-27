import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class KBCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class KBOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class KBMemberIn(BaseModel):
    email: EmailStr
    role: str  # admin|editor|reader|proposer


class KBMemberOut(BaseModel):
    user_id: uuid.UUID
    kb_id: uuid.UUID
    role: str
    email: EmailStr
