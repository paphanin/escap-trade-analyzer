"""Synchronous ChromaDB operations — always call via asyncio.to_thread from async context."""
from typing import Optional

import chromadb
from chromadb.utils import embedding_functions

from config import settings

_client: Optional[chromadb.PersistentClient] = None
_collection = None


def get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=settings.chroma_path)
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=settings.embedding_model
        )
        _collection = _client.get_or_create_collection(
            name="regulations",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def index_extraction(extraction_id: str, text: str, metadata: dict) -> None:
    col = get_collection()
    col.upsert(ids=[extraction_id], documents=[text], metadatas=[metadata])


def remove_extraction(extraction_id: str) -> None:
    try:
        get_collection().delete(ids=[extraction_id])
    except Exception:
        pass


def search(query: str, n_results: int = 8, where: Optional[dict] = None) -> list[dict]:
    col = get_collection()
    count = col.count()
    if count == 0:
        return []

    kwargs: dict = {
        "query_texts": [query],
        "n_results": min(n_results, count),
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    results = col.query(**kwargs)
    items = []
    if results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            items.append({
                "id": doc_id,
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "score": 1.0 - results["distances"][0][i],
            })
    return items


def collection_count() -> int:
    try:
        return get_collection().count()
    except Exception:
        return 0
