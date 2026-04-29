"""Explicit state machine for documents.

Transitions are validated and traced in document_state_transitions.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentStateTransition

# allowed transitions: from -> {to}
ALLOWED: dict[str | None, set[str]] = {
    "proposed": {"proposed", "approved", "rejected", "deleted"},
    "approved": {"ingesting", "rejected", "deleted"},
    "ingesting": {"ingested", "ingestion_failed"},
    "ingested": {"superseded", "deleted"},
    "ingestion_failed": {"ingesting", "rejected", "deleted"},
    "superseded": {"deleted"},
    "rejected": {"deleted"},
    "deleted": set(),
}


class IllegalStateTransition(Exception):
    pass


async def transition(
    session: AsyncSession,
    document: Document,
    to_state: str,
    actor_id: uuid.UUID | None,
    reason: str | None = None,
) -> None:
    current = document.state
    if to_state not in ALLOWED.get(current, set()):
        raise IllegalStateTransition(
            f"cannot transition document {document.id} from {current!r} to {to_state!r}"
        )
    session.add(
        DocumentStateTransition(
            document_id=document.id,
            from_state=current,
            to_state=to_state,
            actor_id=actor_id,
            reason=reason,
        )
    )
    document.state = to_state
