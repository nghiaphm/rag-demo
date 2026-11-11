"""Live P2-03 success/failure persistence smoke test với exact cleanup."""

import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

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
                client.post("/sessions", json={"title": "P2-03 isolated smoke"}),
                201,
                "create session",
            )
            session_id = session["session_id"]
            success = _expect(
                client.post(
                    "/chat",
                    json={
                        "question": "Retrieval-Augmented Generation kết hợp những thành phần nào?",
                        "session_id": session_id,
                    },
                ),
                200,
                "persistent success",
            )
            history = _expect(
                client.get(f"/sessions/{session_id}/messages"), 200, "success history"
            )
            items = history["items"]
            if len(items) != 2 or [item["sequence"] for item in items] != [1, 2]:
                raise RuntimeError("success pair order mismatch")
            if [item["role"] for item in items] != ["USER", "ASSISTANT"]:
                raise RuntimeError("success pair roles mismatch")
            if items[1]["status"] != "COMPLETED" or items[1]["content"] != success["answer"]:
                raise RuntimeError("assistant success was not persisted")
            if items[0]["request_id"] != items[1]["request_id"]:
                raise RuntimeError("success request linkage mismatch")
            session_after_success = database["sessions"].find_one({"_id": session_id})
            if session_after_success.get("active_generation_id") is not None:
                raise RuntimeError("generation guard remained after success")
            response_chunks = {source.get("chunk_id") for source in success["sources"]}
            persisted_chunks = {item["chunk_id"] for item in items[1]["citations"]}
            if not persisted_chunks or not persisted_chunks.issubset(response_chunks):
                raise RuntimeError("persisted citation mapping mismatch")

            with patch(
                "app.api.routes.chat.answer_question",
                side_effect=RuntimeError("private provider detail"),
            ):
                failed_response = client.post(
                    "/chat",
                    json={"question": "Forced failure", "session_id": session_id},
                )
            _expect(failed_response, 502, "persistent failure")
            failed_history = _expect(
                client.get(f"/sessions/{session_id}/messages"), 200, "failure history"
            )["items"]
            if len(failed_history) != 4 or [item["sequence"] for item in failed_history] != [1, 2, 3, 4]:
                raise RuntimeError("failure pair order mismatch")
            failed_assistant = failed_history[3]
            if (
                failed_assistant["status"] != "FAILED"
                or failed_assistant["error_code"] != "RAG_PIPELINE_ERROR"
                or failed_assistant["content"] != ""
            ):
                raise RuntimeError("assistant failure lifecycle mismatch")
            if "private provider detail" in str(failed_assistant):
                raise RuntimeError("raw provider error leaked into persistence")
            session_after_failure = database["sessions"].find_one({"_id": session_id})
            if session_after_failure.get("active_generation_id") is not None:
                raise RuntimeError("generation guard remained after failure")

            deleted = _expect(client.delete(f"/sessions/{session_id}"), 200, "delete")
            if deleted["deleted_messages"] != 4:
                raise RuntimeError("message cleanup count mismatch")
            print(
                "PASS: durable user/PENDING-before-generation, assistant COMPLETED/FAILED, "
                "stable order, request linkage, citations and safe error persistence."
            )
            return 0
        finally:
            if database is not None and session_id is not None:
                database["messages"].delete_many({"session_id": session_id})
                database["sessions"].delete_one({"_id": session_id})
                remaining = database["sessions"].count_documents({"_id": session_id})
                print(f"Cleanup: {'PASS' if remaining == 0 else 'FAIL'}")


if __name__ == "__main__":
    raise SystemExit(main())
