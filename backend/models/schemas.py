from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class DocumentResponse(BaseModel):
    id: str
    filename: str
    status: str
    total_pages: int
    doc_metadata: dict
    error_message: Optional[str] = None
    created_at: datetime
    extraction_count: int = 0
    pending_count: int = 0
    accepted_count: int = 0

    class Config:
        from_attributes = True


class ExtractionResponse(BaseModel):
    id: str
    document_id: str
    article_ref: Optional[str] = None
    text: str
    original_text: str
    citation: str
    page_number: Optional[int] = None
    category: Optional[str] = None
    lang: Optional[str] = None
    confidence: float
    status: str
    edited_text: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ExtractionUpdate(BaseModel):
    action: str  # accept | edit | source_edit | decline
    edited_text: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class CitationItem(BaseModel):
    id: str
    citation: str
    text: str
    score: float
    article_ref: str
    category: str


class ChatResponse(BaseModel):
    message: str
    citations: list[CitationItem]
    expert_used: Optional[str] = None
