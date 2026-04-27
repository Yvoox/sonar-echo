import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class Citation(BaseModel):
    doc_id: uuid.UUID
    doc_title: str
    page: int | None = None
    source_date: date | None = None
    chunk_id: str
    entity_ids: list[str] = Field(default_factory=list)


class ChunkResult(BaseModel):
    chunk_id: str
    text: str
    score: float
    citation: Citation
    entity_ids: list[str] = Field(default_factory=list)


class EntityResult(BaseModel):
    id: str
    canonical_name: str
    type: str
    score: float
    mention_count: int


class TimelineEvent(BaseModel):
    entity_id: str
    related_entity_id: str | None = None
    type: str
    valid_from: date | datetime | None = None
    valid_to: date | datetime | None = None
    source_doc_id: uuid.UUID | None = None
    source_doc_title: str | None = None
    confidence: float | None = None


class CommunityResult(BaseModel):
    id: uuid.UUID
    label: str
    summary: str
    member_entity_ids: list[str] = Field(default_factory=list)
    score: float


class SearchIn(BaseModel):
    query: str
    date_range: tuple[date, date] | None = None
    k: int = 10
    include_superseded: bool = False


class SearchOut(BaseModel):
    chunks: list[ChunkResult]
    entities: list[EntityResult]
    timeline: list[TimelineEvent]
    communities: list[CommunityResult]


class ChatMessageIn(BaseModel):
    content: str
    include_superseded: bool = False


class ChatResponseOut(BaseModel):
    message_id: uuid.UUID
    text: str
    citations: list[Citation]
    entities: list[EntityResult]
    timeline: list[TimelineEvent]
    communities: list[CommunityResult]
