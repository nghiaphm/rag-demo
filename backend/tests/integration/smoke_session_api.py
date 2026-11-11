"""Live P2-02 API smoke test với isolated IDs và exact MongoDB cleanup."""

import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.conversations.models import (
    MessageRecord,
    MessageRole,
    MessageStatus,
)
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
            _expect(client.get(f"/sessions/{uuid4()}"), 404, "missing get")
            created = _expect(
                client.post("/sessions", json={"title": "P2-02 isolated smoke"}),
                201,
                "create",
            )
            session_id = created["session_id"]
            request_id = str(uuid4())
            messages = [
                MessageRecord(
                    session_id=session_id,
                    sequence=1,
                    role=MessageRole.USER,
                    content="First question",
                    status=MessageStatus.COMPLETED,
                    request_id=request_id,
                ),
                MessageRecord(
                    session_id=session_id,
                    sequence=2,
                    role=MessageRole.ASSISTANT,
                    content="First answer",
                    status=MessageStatus.COMPLETED,
                    request_id=request_id,
                ),
                MessageRecord(
                    session_id=session_id,
                    sequence=3,
                    role=MessageRole.USER,
                    content="Second question",
                    status=MessageStatus.COMPLETED,
                ),
            ]
            database["messages"].insert_many([item.to_mongo() for item in messages])

            listed = _expect(client.get("/sessions?limit=200"), 200, "list")
            if not any(item["session_id"] == session_id for item in listed["items"]):
                raise RuntimeError("created session missing from list")
            _expect(client.get(f"/sessions/{session_id}"), 200, "get")
            updated = _expect(
                client.patch(
                    f"/sessions/{session_id}", json={"title": "P2-02 renamed"}
                ),
                200,
                "update",
            )
            if updated["title"] != "P2-02 renamed":
                raise RuntimeError("updated title mismatch")

            history = _expect(
                client.get(f"/sessions/{session_id}/messages?offset=1&limit=2"),
                200,
                "history",
            )
            if history["total"] != 3 or [item["sequence"] for item in history["items"]] != [2, 3]:
                raise RuntimeError("history pagination/order mismatch")

            deleted = _expect(client.delete(f"/sessions/{session_id}"), 200, "delete")
            if deleted["deleted_messages"] != 3 or deleted["message_policy"] != "hard_deleted":
                raise RuntimeError("delete policy/result mismatch")
            if database["messages"].count_documents({"session_id": session_id}) != 0:
                raise RuntimeError("related messages were not deleted")
            tombstone = database["sessions"].find_one({"_id": session_id})
            if tombstone is None or tombstone.get("deleted_at") is None:
                raise RuntimeError("session tombstone missing")
            _expect(client.get(f"/sessions/{session_id}"), 410, "deleted get")
            _expect(
                client.get(f"/sessions/{session_id}/messages"),
                410,
                "deleted history",
            )
            repeated = _expect(client.delete(f"/sessions/{session_id}"), 200, "repeat delete")
            if not repeated["already_deleted"] or repeated["deleted_messages"] != 0:
                raise RuntimeError("repeat delete is not idempotent")
            listed_after_delete = _expect(client.get("/sessions?limit=200"), 200, "list after delete")
            if any(item["session_id"] == session_id for item in listed_after_delete["items"]):
                raise RuntimeError("deleted session remained visible in default list")

            print(
                "PASS: create/list/get/update/history pagination/delete, 404/410 policy, "
                "message cleanup and idempotent repeat delete."
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
