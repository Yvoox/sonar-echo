import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_session
from app.models import (
    ChatConversation,
    ChatMessage,
    Feedback,
    Gem,
    KnowledgeBase,
    User,
)
from app.retrieval import hybrid
from app.schemas.retrieval import ChatMessageIn, ChatResponseOut
from app.security.jwt_auth import get_current_user
from app.security.permissions import require_kb_role
from app.services import chat_service

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


class ConversationIn(BaseModel):
    kb_id: uuid.UUID
    gem_id: uuid.UUID | None = None
    title: str | None = None


class ConversationOut(BaseModel):
    id: uuid.UUID
    kb_id: uuid.UUID
    gem_id: uuid.UUID | None
    title: str

    class Config:
        from_attributes = True


class FeedbackIn(BaseModel):
    rating: int  # -1 | 0 | 1
    comment: str | None = None


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: ConversationIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ConversationOut:
    # check kb access
    kb = await session.get(KnowledgeBase, body.kb_id)
    if kb is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "kb not found")

    conv = ChatConversation(
        user_id=user.id,
        kb_id=body.kb_id,
        gem_id=body.gem_id,
        title=body.title or "Nouvelle conversation",
    )
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return ConversationOut.model_validate(conv)


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ConversationOut]:
    rows = (
        await session.execute(
            select(ChatConversation)
            .where(ChatConversation.user_id == user.id)
            .order_by(ChatConversation.created_at.desc())
        )
    ).scalars().all()
    return [ConversationOut.model_validate(c) for c in rows]


@router.get("/conversations/{conv_id}/messages")
async def list_messages(
    conv_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    conv = await session.get(ChatConversation, conv_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conversation not found")
    rows = (
        await session.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conv_id)
            .order_by(ChatMessage.created_at.asc())
        )
    ).scalars().all()
    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "citations": m.citations,
            "retrieval": m.retrieval,
            "created_at": m.created_at.isoformat(),
        }
        for m in rows
    ]


@router.post("/conversations/{conv_id}/messages")
async def post_message(
    conv_id: uuid.UUID,
    body: ChatMessageIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    conv = await session.get(ChatConversation, conv_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conversation not found")

    # Persist user message
    user_msg = ChatMessage(
        conversation_id=conv_id, role="user", content=body.content
    )
    session.add(user_msg)
    await session.flush()
    user_msg_id = user_msg.id
    await session.commit()

    return StreamingResponse(
        _generate_stream(conv, body, user.id),
        media_type="text/event-stream",
    )


async def _generate_stream(conv: ChatConversation, body: ChatMessageIn, user_id: uuid.UUID):
    """SSE stream of: status events + retrieval payload + final assistant message."""
    # Run retrieval
    yield _sse({"type": "status", "stage": "retrieval"})
    search = await hybrid.search(
        kb_id=conv.kb_id,
        query=body.content,
        k=10,
        include_superseded=body.include_superseded,
    )
    yield _sse({"type": "retrieval", "payload": json.loads(search.model_dump_json())})

    # Pull gem prompt + recent history
    from app.db.postgres import SessionLocal
    async with SessionLocal() as session:
        gem_prompt = None
        if conv.gem_id:
            gem = await session.get(Gem, conv.gem_id)
            if gem:
                gem_prompt = gem.system_prompt
        history_rows = (
            await session.execute(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conv.id)
                .order_by(ChatMessage.created_at.asc())
            )
        ).scalars().all()
    history = [{"role": m.role, "content": m.content} for m in history_rows]

    yield _sse({"type": "status", "stage": "generation"})
    res = await chat_service.generate(
        user_query=body.content,
        search=search,
        history=history,
        system_prompt_extra=gem_prompt,
    )

    # Persist assistant message
    async with SessionLocal() as session:
        citations_payload = [c.model_dump(mode="json") for c in [
            cr.citation for cr in search.chunks
        ]]
        msg = ChatMessage(
            conversation_id=conv.id,
            role="assistant",
            content=res["text"],
            citations=citations_payload,
            retrieval={
                "entities": [e.model_dump(mode="json") for e in search.entities],
                "timeline": [t.model_dump(mode="json") for t in search.timeline],
                "communities": [c.model_dump(mode="json") for c in search.communities],
            },
            tokens_in=res["tokens_in"],
            tokens_out=res["tokens_out"],
            cost_usd=res["cost_usd"],
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)

    yield _sse({
        "type": "message",
        "message_id": str(msg.id),
        "text": res["text"],
        "citations": citations_payload,
        "entities": [e.model_dump(mode="json") for e in search.entities],
        "timeline": [t.model_dump(mode="json") for t in search.timeline],
        "communities": [c.model_dump(mode="json") for c in search.communities],
    })
    yield _sse({"type": "done"})


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


@router.post("/messages/{message_id}/feedback", status_code=201)
async def post_feedback(
    message_id: uuid.UUID,
    body: FeedbackIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    msg = await session.get(ChatMessage, message_id)
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not found")
    if body.rating not in (-1, 0, 1):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "rating must be -1|0|1")
    fb = Feedback(message_id=message_id, user_id=user.id,
                   rating=body.rating, comment=body.comment)
    session.add(fb)
    await session.commit()
    return {"id": str(fb.id), "ok": True}
