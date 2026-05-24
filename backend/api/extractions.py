import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.db import Document, Extraction
from models.schemas import ExtractionResponse, ExtractionUpdate
from services import vector_store

router = APIRouter(prefix="/api/extractions", tags=["extractions"])

_INDEXED_STATUSES = {"accepted", "edited", "source_edited"}


@router.get("/document/{doc_id}", response_model=list[ExtractionResponse])
async def get_extractions(
    doc_id: str,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(Extraction).where(Extraction.document_id == doc_id)
    if status:
        q = q.where(Extraction.status == status)
    q = q.order_by(Extraction.page_number, Extraction.article_ref)
    result = await db.execute(q)
    return result.scalars().all()


@router.patch("/{extraction_id}", response_model=ExtractionResponse)
async def update_extraction(
    extraction_id: str,
    body: ExtractionUpdate,
    db: AsyncSession = Depends(get_db),
):
    ext = await db.get(Extraction, extraction_id)
    if not ext:
        raise HTTPException(404, "Extraction not found")

    doc = await db.get(Document, ext.document_id)

    action = body.action
    if action not in ("accept", "edit", "source_edit", "decline"):
        raise HTTPException(400, f"Unknown action: {action}")

    if action in ("edit", "source_edit") and not body.edited_text:
        raise HTTPException(400, "edited_text required for edit/source_edit actions")

    # Snapshot values before commit (avoids detached-instance issues)
    ext_id = ext.id
    citation = ext.citation
    article_ref = ext.article_ref or ""
    category = ext.category or "general_trade"
    page_number = str(ext.page_number or 0)
    doc_filename = doc.filename
    doc_country = (doc.doc_metadata or {}).get("country", "")

    if action == "accept":
        text = ext.text
        ext.status = "accepted"
    elif action == "edit":
        text = body.edited_text
        ext.edited_text = body.edited_text
        ext.status = "edited"
    elif action == "source_edit":
        text = body.edited_text
        ext.edited_text = body.edited_text
        ext.status = "source_edited"
    else:  # decline
        text = None
        ext.status = "declined"

    await db.commit()
    await db.refresh(ext)

    if action in _INDEXED_STATUSES and text:
        metadata = {
            "document_id": ext.document_id,
            "filename": doc_filename,
            "article_ref": article_ref,
            "citation": citation,
            "page_number": page_number,
            "category": category,
            "country": doc_country,
        }
        await asyncio.to_thread(vector_store.index_extraction, ext_id, text, metadata)
    elif action == "decline":
        await asyncio.to_thread(vector_store.remove_extraction, ext_id)

    return ext


@router.post("/document/{doc_id}/accept-all", response_model=dict)
async def accept_all_pending(doc_id: str, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")

    result = await db.execute(
        select(Extraction).where(
            Extraction.document_id == doc_id, Extraction.status == "pending"
        )
    )
    extractions = result.scalars().all()

    count = 0
    index_jobs = []
    for ext in extractions:
        ext.status = "accepted"
        index_jobs.append((
            ext.id,
            ext.text,
            {
                "document_id": ext.document_id,
                "filename": doc.filename,
                "article_ref": ext.article_ref or "",
                "citation": ext.citation,
                "page_number": str(ext.page_number or 0),
                "category": ext.category or "general_trade",
                "country": (doc.doc_metadata or {}).get("country", ""),
            },
        ))
        count += 1

    await db.commit()

    for ext_id, text, metadata in index_jobs:
        await asyncio.to_thread(vector_store.index_extraction, ext_id, text, metadata)

    return {"accepted": count}
