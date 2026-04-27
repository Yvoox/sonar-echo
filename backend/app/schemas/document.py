import uuid
from datetime import date, datetime

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: uuid.UUID
    kb_id: uuid.UUID
    title: str
    source_date: date | None
    mime_type: str
    state: str
    version: int
    supersedes_id: uuid.UUID | None
    superseded_by_id: uuid.UUID | None
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentApproveIn(BaseModel):
    reason: str | None = None


class IngestionJobOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    status: str
    saga_step: str | None
    token_usage_in: int
    token_usage_out: int
    cost_usd: float
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None

    class Config:
        from_attributes = True
