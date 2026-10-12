"""Live P2-05 verification for durable sessions/messages on MongoDB Atlas.

The RAG generation function is deterministic and patched only for this smoke test.
This keeps the persistence verification independent from external LLM quotas while
the real FastAPI lifespan, MongoDB connection, indexes and HTTP routes are used.
All records use one generated session ID and are removed exactly in ``finally``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.cloud_connections import MongoDBConnection
from app.main import app


def _expect(response, status: int, stage: str) -> dict:
    if response.status_code != status:
        raise RuntimeError(f"{stage} failed with HTTP {response.status_code}")
    return response.json()


def _generation(turn: int) -> dict:
    return {
        "answer": f"P2-05 deterministic answer {turn} [1]",
        "sources": [
            {
                "chunk_id": str(uuid4()),
                "document_id": str(uuid4()),
                "version_id": str(uuid4()),
                "file_name": "p2-05-verification.md",
                "page": turn,
            }
        ],
    }


def main() -> int:
    session_id: str | None = None
    cleanup_connection = MongoDBConnection()
    cleanup_status = cleanup_connection.connect()
    if not cleanup_status.ok or cleanup_connection.database is None:
        print(f"MongoDB cleanup connection: FAIL ({cleanup_status.code})")
        return 1
    cleanup_database = cleanup_connection.database

    try:
        # Lifespan 1: create durable state and verify success/failure persistence.
        with TestClient(app) as client:
            health = _expect(client.get("/health/dependencies"), 200, "dependencies")
            dependencies = health.get("dependencies", {})
            if health.get("status") != "ok" or not all(
                dependencies.get(name, {}).get("ok") for name in ("mongodb", "qdrant")
            ):
                raise RuntimeError("cloud dependencies are not healthy")

            created = _expect(
                client.post("/sessions", json={"title": "P2-05 isolated verification"}),
                201,
                "create session",
            )
            session_id = created["session_id"]
            updated = _expect(
                client.patch(
                    f"/sessions/{session_id}",
                    json={"title": "P2-05 survives restart"},
                ),
                200,
                "update title",
            )
            if updated["title"] != "P2-05 survives restart":
                raise RuntimeError("updated title mismatch")

            for turn in range(1, 4):
                with patch(
                    "app.api.chat.answer_question",
                    return_value=_generation(turn),
                ):
                    result = _expect(
                        client.post(
                            "/chat",
                            json={
                                "question": f"P2-05 question {turn}",
                                "session_id": session_id,
                            },
                        ),
                        200,
                        f"successful chat {turn}",
                    )
                if result["answer"] != f"P2-05 deterministic answer {turn} [1]":
                    raise RuntimeError("chat response mismatch")

            with patch(
                "app.api.chat.answer_question",
                side_effect=RuntimeError("forced verification failure"),
            ):
                failed = client.post(
                    "/chat",
                    json={"question": "P2-05 failed turn", "session_id": session_id},
                )
            failure_body = _expect(failed, 502, "failed generation")
            if "forced verification failure" in failure_body.get("detail", ""):
                raise RuntimeError("raw provider error leaked through API")

            persisted = cleanup_database["sessions"].find_one({"_id": session_id})
            if persisted is None:
                raise RuntimeError("session was not persisted")
            if persisted.get("next_message_sequence") != 9:
                raise RuntimeError("next message sequence mismatch")
            if (
                persisted.get("active_generation_id") is not None
                or persisted.get("active_generation_started_at") is not None
            ):
                raise RuntimeError("generation guard remained after failed turn")

        # Lifespan 2: a fresh backend lifecycle must reload all durable state.
        with TestClient(app) as client:
            restored = _expect(client.get(f"/sessions/{session_id}"), 200, "restart get")
            if restored["title"] != "P2-05 survives restart":
                raise RuntimeError("session title did not survive restart")

            first_page = _expect(
                client.get(f"/sessions/{session_id}/messages?offset=0&limit=3"),
                200,
                "history page 1",
            )
            second_page = _expect(
                client.get(f"/sessions/{session_id}/messages?offset=3&limit=5"),
                200,
                "history page 2",
            )
            if first_page["total"] != 8 or second_page["total"] != 8:
                raise RuntimeError("history total mismatch")
            items = first_page["items"] + second_page["items"]
            if [item["sequence"] for item in items] != list(range(1, 9)):
                raise RuntimeError("history ordering/pagination mismatch")
            for index in range(0, 8, 2):
                pair = items[index : index + 2]
                if [message["role"] for message in pair] != ["USER", "ASSISTANT"]:
                    raise RuntimeError("message role pairing mismatch")
                if pair[0]["request_id"] != pair[1]["request_id"]:
                    raise RuntimeError("request linkage mismatch")
            if any(item["status"] != "COMPLETED" for item in items[:6]):
                raise RuntimeError("successful history status mismatch")
            if any(len(items[index]["citations"]) != 1 for index in (1, 3, 5)):
                raise RuntimeError("persisted citation mismatch")
            if (
                items[7]["status"] != "FAILED"
                or items[7]["error_code"] != "RAG_PIPELINE_ERROR"
            ):
                raise RuntimeError("failed assistant terminal state mismatch")

            _expect(client.get("/sessions/not-a-uuid"), 422, "invalid session id")
            _expect(client.get(f"/sessions/{uuid4()}"), 404, "missing session")

            deleted = _expect(client.delete(f"/sessions/{session_id}"), 200, "delete")
            if deleted["deleted_messages"] != 8 or deleted["already_deleted"]:
                raise RuntimeError("session/message delete result mismatch")
            listing = _expect(client.get("/sessions?offset=0&limit=200"), 200, "list")
            if any(item["session_id"] == session_id for item in listing["items"]):
                raise RuntimeError("deleted session remained in default list")

        # Lifespan 3: tombstone behavior itself must survive another restart.
        with TestClient(app) as client:
            _expect(client.get(f"/sessions/{session_id}"), 410, "deleted get")
            _expect(
                client.get(f"/sessions/{session_id}/messages"),
                410,
                "deleted history",
            )
            repeated = _expect(
                client.delete(f"/sessions/{session_id}"), 200, "repeated delete"
            )
            if not repeated["already_deleted"] or repeated["deleted_messages"] != 0:
                raise RuntimeError("idempotent delete mismatch")

        print(
            "PASS: two backend restarts preserved session/history and tombstone; "
            "ordering, pagination, invalid/missing/deleted session, failed generation, "
            "citations, guard release, list exclusion and idempotent delete verified."
        )
        return 0
    finally:
        if session_id is not None:
            cleanup_database["messages"].delete_many({"session_id": session_id})
            cleanup_database["sessions"].delete_one({"_id": session_id})
            messages_left = cleanup_database["messages"].count_documents(
                {"session_id": session_id}
            )
            session_left = cleanup_database["sessions"].count_documents(
                {"_id": session_id}
            )
            print(
                "Cleanup: "
                f"{'PASS' if messages_left == 0 and session_left == 0 else 'FAIL'}"
            )
        cleanup_connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
