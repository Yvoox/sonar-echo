import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.models.base import Base, created_at_col, uuid_pk


class Community(Base):
    __tablename__ = "communities"

    id: Mapped[uuid.UUID] = uuid_pk()
    kb_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    summary_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.openai_embedding_dim), nullable=True
    )
    member_entity_ids: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, nullable=False
    )
    leiden_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    generated_at: Mapped[datetime] = created_at_col()
