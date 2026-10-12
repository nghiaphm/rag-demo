"""Live P2-04 atomic same-session generation guard test trên MongoDB Atlas."""

import asyncio
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.conversation_repository import (
    MongoConversationRepository,
    SessionConflictError,
)
from app.conversation_service import ConversationService
from app.main import app


def _expect(response, status: int, stage: str) -> dict:
    if response.status_code != status:
        raise RuntimeError(f"{stage} failed with HTTP {response.status_code}")
    return response.json()


def main() -> int:
    session_id: str | None = None
    with TestClient(app) as client:
        database = app.state.cloud_connections.mongodb.database
        try:
            session = _expect(
                client.post("/sessions", json={"title": "P2-04 isolated smoke"}),
                201,
                "create",
            )
            session_id = session["session_id"]
            service = ConversationService(MongoConversationRepository(database))
            started = threading.Event()
            finish = threading.Event()

            def slow_generate(*_args, **_kwargs):
                started.set()
                if not finish.wait(timeout=15):
                    raise TimeoutError("smoke generation did not resume")
                return {"answer": "first completed", "sources": []}

            with patch("app.api.chat.answer_question", side_effect=slow_generate):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    first = executor.submit(
                        client.post,
                        "/chat",
                        json={"question": "first", "session_id": session_id},
                    )
                    if not started.wait(timeout=10):
                        raise RuntimeError("first generation did not acquire guard")

                    try:
                        service.repository.release_generation(session_id, str(uuid4()))
                    except SessionConflictError:
                        pass
                    else:
                        raise RuntimeError("non-owner request released generation guard")

                    second = executor.submit(
                        client.post,
                        "/chat",
                        json={"question": "second", "session_id": session_id},
                    )
                    second_response = second.result(timeout=10)
                    _expect(second_response, 409, "second concurrent chat")

                    _expect(client.delete(f"/sessions/{session_id}"), 409, "delete while active")
                    finish.set()
                    first_response = first.result(timeout=15)
                    first_result = _expect(first_response, 200, "first concurrent chat")
                    if first_result["answer"] != "first completed":
                        raise RuntimeError("first generation result mismatch")

            persisted = database["sessions"].find_one({"_id": session_id})
            if (
                persisted.get("active_generation_id") is not None
                or persisted.get("active_generation_started_at") is not None
            ):
                raise RuntimeError("guard remained after completion")

            try:
                service.answer_with_persistence(
                    session_id=session_id,
                    question="cancelled",
                    generate=lambda: (_ for _ in ()).throw(asyncio.CancelledError()),
                    model="p2-04/test",
                )
            except asyncio.CancelledError:
                pass
            else:
                raise RuntimeError("cancelled generation did not propagate cancellation")

            persisted = database["sessions"].find_one({"_id": session_id})
            if persisted.get("active_generation_id") is not None:
                raise RuntimeError("guard remained after cancellation")

            try:
                service.answer_with_persistence(
                    session_id=session_id,
                    question="failed",
                    generate=lambda: (_ for _ in ()).throw(RuntimeError("forced")),
                    model="p2-04/test",
                )
            except RuntimeError as exc:
                if str(exc) != "forced":
                    raise
            else:
                raise RuntimeError("failed generation did not propagate error")
            persisted = database["sessions"].find_one({"_id": session_id})
            if persisted.get("active_generation_id") is not None:
                raise RuntimeError("guard remained after generation error")

            history = _expect(
                client.get(f"/sessions/{session_id}/messages"), 200, "history"
            )["items"]
            if len(history) != 6 or [item["sequence"] for item in history] != [1, 2, 3, 4, 5, 6]:
                raise RuntimeError("concurrency history/order mismatch")
            if history[3]["status"] != "FAILED" or history[3]["error_code"] != "GENERATION_CANCELLED":
                raise RuntimeError("cancelled assistant terminal state mismatch")
            if history[5]["status"] != "FAILED" or history[5]["error_code"] != "RAG_PIPELINE_ERROR":
                raise RuntimeError("failed assistant terminal state mismatch")

            deleted = _expect(client.delete(f"/sessions/{session_id}"), 200, "delete")
            if deleted["deleted_messages"] != 6:
                raise RuntimeError("final message cleanup mismatch")
            print(
                "PASS: one active generation/session, concurrent reject, owner-only release, "
                "delete conflict, completion/error/cancellation release and terminal history."
            )
            return 0
        finally:
            if "finish" in locals():
                finish.set()
            if database is not None and session_id is not None:
                database["messages"].delete_many({"session_id": session_id})
                database["sessions"].delete_one({"_id": session_id})
                remaining = database["sessions"].count_documents({"_id": session_id})
                print(f"Cleanup: {'PASS' if remaining == 0 else 'FAIL'}")


if __name__ == "__main__":
    raise SystemExit(main())
