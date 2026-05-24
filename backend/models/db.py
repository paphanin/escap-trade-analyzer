from sqlalchemy import Column, String, Float, Integer, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from database import Base


def _uuid():
    return str(uuid.uuid4())


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=_uuid)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    status = Column(String, default="processing")  # processing | extracting | parsed | error
    total_pages = Column(Integer, default=0)
    doc_metadata = Column(JSON, default=dict)
    parsed_content = Column(Text)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    extractions = relationship("Extraction", back_populates="document", cascade="all, delete-orphan")


class Extraction(Base):
    __tablename__ = "extractions"

    id = Column(String, primary_key=True, default=_uuid)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    article_ref = Column(String)
    text = Column(Text, nullable=False)
    original_text = Column(Text, nullable=False)
    citation = Column(String, nullable=False)
    page_number = Column(Integer)
    category = Column(String)
    lang = Column(String)  # ISO 639-1 code detected from source text
    confidence = Column(Float, default=0.7)
    status = Column(String, default="pending")  # pending | accepted | edited | source_edited | declined
    edited_text = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="extractions")
