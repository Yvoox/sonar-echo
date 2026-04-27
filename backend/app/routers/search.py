import uuid

from fastapi import APIRouter, Depends, Path

from app.retrieval import hybrid
from app.schemas.retrieval import SearchIn, SearchOut
from app.security.permissions import require_kb_role

router = APIRouter(prefix="/api/v1/kbs/{kb_id}", tags=["search"])


@router.post("/search", response_model=SearchOut)
async def search_kb(
    body: SearchIn,
    kb_id: uuid.UUID = Path(...),
    _: tuple = Depends(require_kb_role("reader")),
) -> SearchOut:
    return await hybrid.search(
        kb_id=kb_id,
        query=body.query,
        date_range=body.date_range,
        k=body.k,
        include_superseded=body.include_superseded,
    )
