import asyncio
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import AsyncSessionLocal, get_db
from models.db import Document, Extraction
from models.schemas import DocumentResponse
from services import parser as parser_svc

router = APIRouter(prefix="/api/documents", tags=["documents"])


async def _process_document(doc_id: str, file_path: Path, filename: str) -> None:
    async with AsyncSessionLocal() as db:
        doc = await db.get(Document, doc_id)
        try:
            parsed, page_count = await parser_svc.parse_document(file_path, filename)

            doc.parsed_content = parsed
            doc.total_pages = page_count
            doc.status = "extracting"
            await db.commit()

            provisions = await parser_svc.extract_provisions(parsed, filename)

            for p in provisions:
                text = p.get("text", "").strip()
                if not text:
                    continue
                db.add(Extraction(
                    id=str(uuid.uuid4()),
                    document_id=doc_id,
                    article_ref=p.get("article_ref"),
                    text=text,
                    original_text=text,
                    citation=p.get("citation", ""),
                    page_number=p.get("page_number"),
                    category=p.get("category"),
                    lang=p.get("lang"),
                    confidence=float(p.get("confidence", 0.7)),
                    status="pending",
                ))

            doc.status = "parsed"
            await db.commit()

        except Exception as exc:
            doc.status = "error"
            doc.error_message = str(exc)[:500]
            await db.commit()
            raise


@router.post("", response_model=DocumentResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    country: str = Form(default=""),
    treaty_name: str = Form(default=""),
    year: str = Form(default=""),
    category: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    doc_id = str(uuid.uuid4())
    file_path = settings.upload_dir / f"{doc_id}.pdf"

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    doc = Document(
        id=doc_id,
        filename=file.filename,
        file_path=str(file_path),
        status="processing",
        doc_metadata={
            "country": country,
            "treaty_name": treaty_name,
            "year": year,
            "category": category,
        },
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    background_tasks.add_task(_process_document, doc_id, file_path, file.filename)

    return DocumentResponse(
        id=doc.id,
        filename=doc.filename,
        status=doc.status,
        total_pages=doc.total_pages,
        doc_metadata=doc.doc_metadata or {},
        created_at=doc.created_at,
    )


@router.get("", response_model=list[DocumentResponse])
async def list_documents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).order_by(Document.created_at.desc()))
    docs = result.scalars().all()

    responses = []
    for doc in docs:
        total = (await db.execute(
            select(func.count(Extraction.id)).where(Extraction.document_id == doc.id)
        )).scalar() or 0
        pending = (await db.execute(
            select(func.count(Extraction.id)).where(
                Extraction.document_id == doc.id, Extraction.status == "pending"
            )
        )).scalar() or 0
        accepted = (await db.execute(
            select(func.count(Extraction.id)).where(
                Extraction.document_id == doc.id, Extraction.status.in_(["accepted", "edited", "source_edited"])
            )
        )).scalar() or 0

        responses.append(DocumentResponse(
            id=doc.id,
            filename=doc.filename,
            status=doc.status,
            total_pages=doc.total_pages,
            doc_metadata=doc.doc_metadata or {},
            error_message=doc.error_message,
            created_at=doc.created_at,
            extraction_count=total,
            pending_count=pending,
            accepted_count=accepted,
        ))
    return responses


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")

    total = (await db.execute(
        select(func.count(Extraction.id)).where(Extraction.document_id == doc_id)
    )).scalar() or 0
    pending = (await db.execute(
        select(func.count(Extraction.id)).where(
            Extraction.document_id == doc_id, Extraction.status == "pending"
        )
    )).scalar() or 0
    accepted = (await db.execute(
        select(func.count(Extraction.id)).where(
            Extraction.document_id == doc_id, Extraction.status.in_(["accepted", "edited", "source_edited"])
        )
    )).scalar() or 0

    return DocumentResponse(
        id=doc.id,
        filename=doc.filename,
        status=doc.status,
        total_pages=doc.total_pages,
        doc_metadata=doc.doc_metadata or {},
        error_message=doc.error_message,
        created_at=doc.created_at,
        extraction_count=total,
        pending_count=pending,
        accepted_count=accepted,
    )


@router.get("/{doc_id}/page/{page_number}")
async def get_page_image(doc_id: str, page_number: int, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    img = await parser_svc.get_page_image(Path(doc.file_path), page_number)
    return Response(content=img, media_type="image/png")


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")

    result = await db.execute(select(Extraction).where(Extraction.document_id == doc_id))
    extractions = result.scalars().all()

    from services import vector_store
    for ext in extractions:
        await asyncio.to_thread(vector_store.remove_extraction, ext.id)

    Path(doc.file_path).unlink(missing_ok=True)
    await db.delete(doc)
    await db.commit()
    return {"status": "deleted"}
