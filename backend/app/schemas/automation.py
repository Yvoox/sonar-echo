import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AutomationIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kb_id: uuid.UUID
    gem_id: uuid.UUID
    user_prompt: str
    cron_expr: str
    channel_type: str = "email"  # email|webhook|slack
    channel_config: dict = Field(default_factory=dict)
    active: bool = True


class AutomationOut(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    kb_id: uuid.UUID
    gem_id: uuid.UUID
    name: str
    user_prompt: str
    cron_expr: str
    channel_type: str
    channel_config: dict
    active: bool
    last_run_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True
