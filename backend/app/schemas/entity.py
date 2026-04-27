from datetime import date, datetime

from pydantic import BaseModel, Field


class EntityOut(BaseModel):
    id: str
    type: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)


class CommunityOut(BaseModel):
    id: str
    label: str
    summary: str
    member_entity_ids: list[str]
    level: int
    generated_at: datetime


class TimelineOut(BaseModel):
    entity: EntityOut
    events: list[dict]
