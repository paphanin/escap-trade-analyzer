# LexanTrade — Digital Trade Regulatory Analyzer

AI pipeline for discovering, extracting, and querying digital trade regulations across Asia-Pacific jurisdictions.

## Architecture

```
Upload PDF → VLM Page Parsing → Provision Extraction (w/ citations)
    → Human Review (Accept / Edit / Decline / Edit Source)
    → Multilingual Vector Index → RAG Chatbot (MoE routing)
```

**Stack:**
- Backend: FastAPI + SQLite + ChromaDB
- AI: Claude claude-sonnet-4-6 (vision parsing + extraction + chat), Claude Haiku (query routing)
- Embeddings: `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers)
- Frontend: Static HTML + Alpine.js + Tailwind CSS (served by FastAPI — no Node required)

## Setup

### 1. Python environment

```bash
cd escap-trade-analyzer/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment variables

```bash
cp .env.example .env
# Edit .env and add your Anthropic API key:
#   ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Run

```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000
```

Open: http://localhost:8000

## Usage

1. **Upload** — drag a PDF onto the Upload page, add metadata (country, treaty, year)
2. **Wait** — the AI parses each page with Claude Vision and extracts provisions (~30–120s per doc)
3. **Review** — accept, edit, decline, or "Edit Source" each extracted provision
4. **Chat** — ask cross-jurisdictional questions; every answer cites exact source clauses

## Key design decisions

| Choice | Reason |
|---|---|
| Claude Vision per page | Preserves table structure and multi-column layouts |
| Verbatim extraction prompt | Zero paraphrase — extracted text matches source exactly |
| Human review before indexing | Only expert-approved provisions enter the knowledge base |
| Edit Source shows page image | User corrects extraction with the original visible |
| MoE routing (Haiku classifier) | Cheap routing, expensive generation only where needed |
| sentence-transformers multilingual | Cross-lingual retrieval without translation |

## Page limit

By default, documents are capped at 40 pages (`MAX_PAGES_PER_DOC` in `.env`).  
Each page makes one Claude Vision API call.

## Project structure

```
backend/
├── main.py              # FastAPI app + static file serving
├── config.py
├── database.py
├── models/
│   ├── db.py            # SQLAlchemy models
│   └── schemas.py       # Pydantic schemas
├── api/
│   ├── documents.py     # Upload, list, delete, page image
│   ├── extractions.py   # Review workflow (accept/edit/decline/source_edit)
│   └── chat.py          # RAG chatbot + stats
├── services/
│   ├── parser.py        # VLM parsing + provision extraction
│   ├── vector_store.py  # ChromaDB operations
│   └── rag.py           # MoE routing + RAG answer generation
└── static/
    ├── index.html       # Dashboard
    ├── upload.html      # Upload form
    ├── review.html      # Extraction review UI
    ├── chat.html        # RAG chatbot UI
    └── app.js           # Shared API client + UI helpers
```
