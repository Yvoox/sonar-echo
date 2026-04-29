import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_session
from app.models import Document, IngestionJob, KBMembership, User
from app.schemas.document import DocumentApproveIn, DocumentOut, IngestionJobOut
from app.security.permissions import require_kb_role
from app.security.rate_limiter import enforce_ingestion_rate_limit
from app.services import document_state
from app.services.audit import log
from app.services.storage import make_key, upload_bytes
from app.workers.queue import enqueue_ingestion

router = APIRouter(prefix="/api/v1/kbs/{kb_id}/documents", tags=["documents"])


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    kb_id: uuid.UUID = Path(...),
    state: str | None = Query(None),
    include_deleted: bool = Query(False),
    _: tuple = Depends(require_kb_role("reader")),
    session: AsyncSession = Depends(get_session),
) -> list[DocumentOut]:
    stmt = select(Document).where(Document.kb_id == kb_id)
    if state:
        stmt = stmt.where(Document.state == state)
    if not include_deleted:
        stmt = stmt.where(Document.state != "deleted")
    stmt = stmt.order_by(Document.created_at.desc())
    docs = (await session.execute(stmt)).scalars().all()
    return [DocumentOut.model_validate(d) for d in docs]


@router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(
    kb_id: uuid.UUID = Path(...),
    file: UploadFile = File(...),
    title: str | None = Form(None),
    supersedes: uuid.UUID | None = Form(None),
    ctx: tuple[User, KBMembership] = Depends(require_kb_role("proposer")),
    _rl: User = Depends(enforce_ingestion_rate_limit),
    session: AsyncSession = Depends(get_session),
) -> DocumentOut:
    user, membership = ctx
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty file")
    if len(data) > 200 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "max 200MB per upload")

    # editor/admin → bypass approval; proposer → state proposed
    direct_ingest = membership.role in ("admin", "editor")

    version = 1
    if supersedes is not None:
        old = await session.get(Document, supersedes)
        if old is None or old.kb_id != kb_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "supersedes target not found")
        version = old.version + 1

    new_id = uuid.uuid4()
    key = make_key(kb_id, new_id, file.filename or f"{new_id}.bin")
    storage_uri = upload_bytes(data, key, file.content_type or "application/octet-stream")

    doc = Document(
        id=new_id,
        kb_id=kb_id,
        title=title or file.filename or str(new_id),
        storage_uri=storage_uri,
        mime_type=file.content_type or "application/octet-stream",
        state="proposed",  # placeholder, transition below
        version=version,
        supersedes_id=supersedes,
        created_by=user.id,
    )
    session.add(doc)
    await session.flush()

    # explicit: from None -> proposed
    await document_state.transition(session, doc, "proposed", user.id, "upload")
    if direct_ingest:
        await document_state.transition(session, doc, "approved", user.id, "auto-approve")

    await log(session, user.id, "document.uploaded", "document", str(doc.id),
              {"kb_id": str(kb_id), "title": doc.title, "state": doc.state, "supersedes": str(supersedes) if supersedes else None})
    await session.commit()
    await session.refresh(doc)

    if direct_ingest:
        await _kickoff_ingestion(session, doc, user.id)

    return DocumentOut.model_validate(doc)


@router.post("/{doc_id}/approve", response_model=DocumentOut)
async def approve_document(
    kb_id: uuid.UUID = Path(...),
    doc_id: uuid.UUID = Path(...),
    body: DocumentApproveIn = DocumentApproveIn(),
    ctx: tuple[User, KBMembership] = Depends(require_kb_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> DocumentOut:
    user, _ = ctx
    doc = await session.get(Document, doc_id)
    if doc is None or doc.kb_id != kb_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    if doc.state != "proposed":
        raise HTTPException(status.HTTP_409_CONFLICT, f"cannot approve from state {doc.state}")
    await document_state.transition(session, doc, "approved", user.id, body.reason or "approved")
    await log(session, user.id, "document.approved", "document", str(doc.id), {"kb_id": str(kb_id)})
    await session.commit()
    await session.refresh(doc)
    await _kickoff_ingestion(session, doc, user.id)
    return DocumentOut.model_validate(doc)


@router.post("/{doc_id}/reject", response_model=DocumentOut)
async def reject_document(
    kb_id: uuid.UUID = Path(...),
    doc_id: uuid.UUID = Path(...),
    body: DocumentApproveIn = DocumentApproveIn(),
    ctx: tuple[User, KBMembership] = Depends(require_kb_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> DocumentOut:
    user, _ = ctx
    doc = await session.get(Document, doc_id)
    if doc is None or doc.kb_id != kb_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    await document_state.transition(session, doc, "rejected", user.id, body.reason or "rejected")
    await log(session, user.id, "document.rejected", "document", str(doc.id), {"kb_id": str(kb_id)})
    await session.commit()
    await session.refresh(doc)
    return DocumentOut.model_validate(doc)


@router.delete("/{doc_id}", response_model=DocumentOut)
async def delete_document(
    kb_id: uuid.UUID = Path(...),
    doc_id: uuid.UUID = Path(...),
    hard: bool = Query(False),
    ctx: tuple[User, KBMembership] = Depends(require_kb_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> DocumentOut:
    user, membership = ctx
    if hard and membership.role != "admin" and not user.is_global_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "hard delete requires admin")
    doc = await session.get(Document, doc_id)
    if doc is None or doc.kb_id != kb_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")

    await document_state.transition(session, doc, "deleted", user.id, "deleted")
    doc.deleted_at = datetime.now(timezone.utc)
    await log(session, user.id, "document.deleted", "document", str(doc.id),
              {"kb_id": str(kb_id), "hard": hard})
    await session.commit()
    await session.refresh(doc)

    # Schedule cascade cleanup (Neo4j + Qdrant + optional MinIO)
    from app.workers.queue import enqueue_doc_cleanup
    await enqueue_doc_cleanup(doc.id, hard=hard)
    return DocumentOut.model_validate(doc)


@router.get("/{doc_id}", response_model=DocumentOut)
async def get_document(
    kb_id: uuid.UUID = Path(...),
    doc_id: uuid.UUID = Path(...),
    _: tuple = Depends(require_kb_role("reader")),
    session: AsyncSession = Depends(get_session),
) -> DocumentOut:
    doc = await session.get(Document, doc_id)
    if doc is None or doc.kb_id != kb_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    return DocumentOut.model_validate(doc)


@router.get("/{doc_id}/job", response_model=IngestionJobOut)
async def get_ingestion_job(
    kb_id: uuid.UUID = Path(...),
    doc_id: uuid.UUID = Path(...),
    _: tuple = Depends(require_kb_role("reader")),
    session: AsyncSession = Depends(get_session),
) -> IngestionJobOut:
    job = (
        await session.execute(
            select(IngestionJob)
            .where(IngestionJob.document_id == doc_id)
            .order_by(IngestionJob.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no ingestion job for this document")
    return IngestionJobOut.model_validate(job)


async def _kickoff_ingestion(
    session: AsyncSession, doc: Document, actor_id: uuid.UUID
) -> None:
    """Create an IngestionJob row + enqueue Arq task."""
    job = IngestionJob(document_id=doc.id, status="queued")
    session.add(job)
    await document_state.transition(session, doc, "ingesting", actor_id, "ingestion queued")
    await session.commit()
    await enqueue_ingestion(job_id=job.id, document_id=doc.id)
