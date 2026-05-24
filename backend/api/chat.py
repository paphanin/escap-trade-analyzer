from fastapi import APIRouter

from models.schemas import ChatRequest, ChatResponse
from services.rag import answer_query

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    result = await answer_query(request.message, request.session_id)
    return ChatResponse(
        message=result["message"],
        citations=result["citations"],
        expert_used=result.get("expert_used"),
    )


@router.get("/stats")
async def chat_stats():
    from services.vector_store import collection_count
    import asyncio
    count = await asyncio.to_thread(collection_count)
    return {"indexed_provisions": count}
