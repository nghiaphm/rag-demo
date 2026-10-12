"""Endpoint chat: gọi RAG pipeline và trả answer + sources."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from app.config import settings
from app.conversation_repository import (
    ConversationRepositoryError,
    SessionConflictError,
    SessionDeletedError,
    SessionNotFoundError,
)
from app.conversation_service import create_conversation_service
from app.rag.pipeline import answer_question
from app.schemas import ChatRequest, ChatResponse, Source

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    """Trả lời câu hỏi bằng RAG pipeline (retrieve top-k -> prompt -> LLM)."""
    try:
        cloud = request.app.state.cloud_connections
        if cloud.mongodb.database is None or cloud.qdrant.client is None:
            raise HTTPException(status_code=503, detail="Cloud dependencies chưa sẵn sàng.")
        if payload.session_id is None:
            result = await run_in_threadpool(
                answer_question,
                payload.question,
                database=cloud.mongodb.database,
                qdrant_client=cloud.qdrant.client,
            )
        else:
            service = await run_in_threadpool(
                create_conversation_service, cloud.mongodb.database
            )

            def generate() -> dict:
                return answer_question(
                    payload.question,
                    database=cloud.mongodb.database,
                    qdrant_client=cloud.qdrant.client,
                )

            result = await run_in_threadpool(
                service.answer_with_persistence,
                session_id=str(payload.session_id),
                question=payload.question,
                generate=generate,
                model=settings.llm_model,
            )
    except HTTPException:
        raise
    except SessionDeletedError as exc:
        raise HTTPException(status_code=410, detail="Session đã bị xóa.") from exc
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session không tồn tại.") from exc
    except SessionConflictError as exc:
        raise HTTPException(status_code=409, detail="Session đang có xung đột trạng thái.") from exc
    except ConversationRepositoryError as exc:
        raise HTTPException(status_code=503, detail="Message persistence tạm thời không khả dụng.") from exc
    except Exception as exc:  # noqa: BLE001 - chuyển lỗi integration thành lỗi API rõ ràng
        raise HTTPException(
            status_code=502,
            detail=f"Lỗi RAG pipeline: {type(exc).__name__}",
        ) from exc

    return ChatResponse(
        answer=result["answer"],
        sources=[Source(**source) for source in result["sources"]],
    )
