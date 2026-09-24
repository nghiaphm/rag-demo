"""Endpoint chat: gọi RAG pipeline và trả answer + sources."""

from fastapi import APIRouter, HTTPException

from app.rag.pipeline import answer_question
from app.schemas import ChatRequest, ChatResponse, Source

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Trả lời câu hỏi bằng RAG pipeline (retrieve top-k -> prompt -> LLM)."""
    try:
        result = answer_question(request.question)
    except Exception as exc:  # noqa: BLE001 - chuyển lỗi integration thành lỗi API rõ ràng
        raise HTTPException(
            status_code=502,
            detail=f"Lỗi RAG pipeline: {type(exc).__name__}",
        ) from exc

    return ChatResponse(
        answer=result["answer"],
        sources=[Source(**source) for source in result["sources"]],
    )
