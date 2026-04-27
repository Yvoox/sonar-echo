import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class GemIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    system_prompt: str = Field(min_length=1)
    kb_id: uuid.UUID | None = None
    visibility: str = "private"
    config: dict = Field(default_factory=dict)


class GemOut(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    kb_id: uuid.UUID | None
    name: str
    description: str | None
    system_prompt: str
    config: dict
    visibility: str
    created_at: datetime

    class Config:
        from_attributes = True


class GemRunIn(BaseModel):
    inputs: dict = Field(default_factory=dict)
    user_prompt: str
