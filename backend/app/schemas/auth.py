import uuid

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    org_id: uuid.UUID | None = None  # if None, a new org is created
    org_name: str | None = None
    is_global_admin: bool = False


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID
    org_id: uuid.UUID
    is_global_admin: bool


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    org_id: uuid.UUID
    is_global_admin: bool

    class Config:
        from_attributes = True
