"""Live P3 compatibility contract smoke with isolated MongoDB Atlas cleanup."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.main import app


REQUIRED_FIELDS = {
    "request_id",
    "session_id",
    "user_message_id",
    "assistant_message_id",
    "answer",
    "sources",
    "citations",
    "metadata",
    "usage",
    "status",
    "error",
}


def _expect(response, status: int, stage: str) -> dict:
    if response.status_code != status:
        raise RuntimeError(f"{stage} failed with HTTP {response.status_code}")
    return response.json()


def _assert_common(body: dict, *, mode: str) -> None:
    if set(body) != REQUIRED_FIELDS:
        raise RuntimeError("response fields mismatch")
    UUID(body["request_id"])
    if body["status"] != "COMPLETED" or body["error"] is not None:
        raise RuntimeError("terminal success contract mismatch")
    if body["usage"] is not None:
        raise RuntimeError("usage must be null when provider does not supply it")
    if body["metadata"]["mode"] != mode or not body["metadata"].get("model"):
        raise RuntimeError("response metadata mismatch")
    if not isinstance(body["sources"], list) or not isinstance(body["citations"], list):
        raise RuntimeError("sources/citations must be arrays")


def _assert_failed(body: dict, *, mode: str) -> None:
    if set(body) != REQUIRED_FIELDS:
        raise RuntimeError("failed response fields mismatch")
    UUID(body["request_id"])
    if body["status"] != "FAILED" or body["answer"] is not None:
        raise RuntimeError("terminal failure contract mismatch")
    if body["sources"] or body["citations"] or body["usage"] is not None:
        raise RuntimeError("failed response nullable/empty fields mismatch")
    if body["metadata"]["mode"] != mode:
        raise RuntimeError("failed response mode mismatch")
    if body["error"]["code"] != "RAG_PIPELINE_ERROR":
        raise RuntimeError("failed response safe error mismatch")


def main() -> int:
    session_id: str | None = None
    sources = [
        {
            "chunk_id": str(uuid4()),
            "document_id": str(uuid4()),
            "version_id": str(uuid4()),
            "file_name": "p3-02-candidate.md",
            "chunk_index": 0,
            "page": 0,
        },
        {
            "chunk_id": str(uuid4()),
            "document_id": str(uuid4()),
            "version_id": str(uuid4()),
            "file_name": "p3-02-cited.md",
            "chunk_index": 1,
            "page": 4,
        },
    ]
    generated = {"answer": "P3-02 deterministic answer [2]", "sources": sources}

    with TestClient(app) as client:
        database = None
        try:
            health = _expect(client.get("/health/dependencies"), 200, "dependencies")
            if health.get("status") != "ok":
                raise RuntimeError("cloud dependencies are not healthy")
            # Readiness reconnects clients, so capture the current database afterwards.
            database = app.state.cloud_connections.mongodb.database

            with patch("app.api.routes.chat.answer_question", return_value=generated):
                stateless = _expect(
                    client.post("/chat", json={"question": "stateless"}),
                    200,
                    "stateless chat",
                )
            _assert_common(stateless, mode="STATELESS")
            if any(
                stateless[field] is not None
                for field in ("session_id", "user_message_id", "assistant_message_id")
            ):
                raise RuntimeError("stateless IDs must be null")
            if len(stateless["sources"]) != 2 or len(stateless["citations"]) != 1:
                raise RuntimeError("stateless candidate/citation distinction mismatch")
            if stateless["citations"][0]["chunk_id"] != sources[1]["chunk_id"]:
                raise RuntimeError("stateless citation was not mapped from retrieved source")
            legacy_projection = {key: stateless[key] for key in ("answer", "sources")}
            if legacy_projection["answer"] != generated["answer"] or [
                item["file_name"] for item in legacy_projection["sources"]
            ] != [item["file_name"] for item in generated["sources"]]:
                raise RuntimeError("legacy /chat projection mismatch")

            fallback_result = {
                "answer": "Không tìm thấy thông tin trong tài liệu",
                "sources": [],
            }
            with patch("app.api.routes.chat.answer_question", return_value=fallback_result):
                fallback = _expect(
                    client.post("/chat", json={"question": "outside corpus"}),
                    200,
                    "fallback chat",
                )
            _assert_common(fallback, mode="STATELESS")
            if fallback["sources"] or fallback["citations"]:
                raise RuntimeError("fallback must not claim sources or citations")

            session = _expect(
                client.post("/sessions", json={"title": "P3-01 isolated smoke"}),
                201,
                "create session",
            )
            session_id = session["session_id"]
            with patch("app.api.routes.chat.answer_question", return_value=generated):
                persistent = _expect(
                    client.post(
                        "/chat",
                        json={"question": "persistent", "session_id": session_id},
                    ),
                    200,
                    "persistent chat",
                )
            _assert_common(persistent, mode="PERSISTENT")
            for field in (
                "session_id",
                "user_message_id",
                "assistant_message_id",
            ):
                UUID(persistent[field])
            if persistent["session_id"] != session_id:
                raise RuntimeError("persistent session ID mismatch")
            if len(persistent["citations"]) != 1:
                raise RuntimeError("persistent citation contract mismatch")
            if persistent["citations"][0]["chunk_id"] != sources[1]["chunk_id"]:
                raise RuntimeError("persistent citation selected the wrong candidate")

            history = _expect(
                client.get(f"/sessions/{session_id}/messages"),
                200,
                "history",
            )["items"]
            if len(history) != 2:
                raise RuntimeError("persistent message pair mismatch")
            if persistent["user_message_id"] != history[0]["message_id"]:
                raise RuntimeError("user message ID is not durable")
            if persistent["assistant_message_id"] != history[1]["message_id"]:
                raise RuntimeError("assistant message ID is not durable")
            if persistent["request_id"] != history[0]["request_id"]:
                raise RuntimeError("request ID is not linked to persisted messages")
            if history[1]["citations"] != persistent["citations"]:
                raise RuntimeError("response citations do not match durable history")

            with patch(
                "app.api.routes.chat.answer_question",
                side_effect=RuntimeError("private provider detail"),
            ):
                failed_response = client.post(
                    "/chat",
                    json={"question": "forced failure", "session_id": session_id},
                )
            failed = _expect(failed_response, 502, "failed persistent chat")
            _assert_failed(failed, mode="PERSISTENT")
            if "private provider detail" in failed_response.text:
                raise RuntimeError("raw provider error leaked")
            failure_history = _expect(
                client.get(f"/sessions/{session_id}/messages"),
                200,
                "failed history",
            )["items"]
            if len(failure_history) != 4:
                raise RuntimeError("failed turn message pair mismatch")
            if failure_history[-1]["status"] != "FAILED":
                raise RuntimeError("failed assistant state was not persisted")
            if failed["assistant_message_id"] != failure_history[-1]["message_id"]:
                raise RuntimeError("failed response assistant ID is not durable")

            deleted = _expect(client.delete(f"/sessions/{session_id}"), 200, "delete")
            if deleted["deleted_messages"] != 4:
                raise RuntimeError("message cleanup mismatch")
            print(
                "PASS: legacy projection, fallback, multi-document citation, usage=null, "
                "safe failure envelope and durable failed IDs verified."
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
