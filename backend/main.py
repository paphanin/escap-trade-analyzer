import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import init_db
from api import documents, extractions, chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Pre-warm the embedding model in the background — server accepts requests immediately
    from services.vector_store import get_collection
    asyncio.create_task(asyncio.to_thread(get_collection))
    yield


app = FastAPI(
    title="ESCAP Digital Trade Regulatory Analyzer",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(extractions.router)
app.include_router(chat.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Serve frontend static files — must be mounted last
app.mount("/", StaticFiles(directory="static", html=True), name="static")
