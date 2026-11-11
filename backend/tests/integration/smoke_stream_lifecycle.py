"""Live P4-03 Atlas lifecycle smoke with a deterministic provider stream.

This test writes only one isolated session and its two messages, then removes both
by exact ID. Retrieval/provider are mocked so no document data or provider quota
is consumed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.main import app
from app.chat.pipeline import ProviderStreamChunk


def _frames(body: str) -> list[tuple[str, dict]]:
    return [
        (
            lines[0].removeprefix("event: "),
            json.loads(lines[1].removeprefix("data: ")),
        )
        for frame in body.strip().split("\n\n")
        if (lines := frame.splitlines())
    ]


def main() -> int:
    session_id: str | None = None
    with TestClient(app) as client:
        database = app.state.cloud_connections.mongodb.database
        if database is None:
            print("BLOCKED: MongoDB Atlas is unavailable; secrets are not printed.")
            return 2
        try:
            created = client.post("/sessions", json={"title": "P4-03 isolated smoke"})
            if created.status_code != 201:
                raise RuntimeError(f"create session failed with HTTP {created.status_code}")
            session_id = created.json()["session_id"]
            prepared = SimpleNamespace(sources=[])

            async def provider_stream(_prepared):
                yield ProviderStreamChunk(content="P4-03 ", usage=None)
                yield ProviderStreamChunk(
                    content="lifecycle answer",
                    usage={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
                )

            with patch("app.api.routes.chat.prepare_rag_stream", return_value=prepared), patch(
                "app.api.routes.chat.astream_rag_answer", provider_stream
            ):
                response = client.post(
                    "/chat/stream",
                    json={"question": "lifecycle smoke", "session_id": session_id},
                )
            if response.status_code != 200:
                raise RuntimeError(f"stream endpoint failed with HTTP {response.status_code}")
            events = _frames(response.text)
            if [event for event, _ in events] != ["start", "metadata", "delta", "delta", "done"]:
                raise RuntimeError("SSE lifecycle event order mismatch")
            start = events[0][1]
            if start["mode"] != "PERSISTENT" or start["session_id"] != session_id:
                raise RuntimeError("persistent SSE identifiers mismatch")
            history = client.get(f"/sessions/{session_id}/messages")
            if history.status_code != 200:
                raise RuntimeError("read persistent history failed")
            items = history.json()["items"]
            if [item["status"] for item in items] != ["COMPLETED", "COMPLETED"]:
                raise RuntimeError("terminal lifecycle state mismatch")
            if items[1]["content"] != "P4-03 lifecycle answer":
                raise RuntimeError("persisted stream content mismatch")
            if items[1]["usage"]["total_tokens"] != 5:
                raise RuntimeError("persisted stream usage mismatch")
            active = database["sessions"].find_one({"_id": session_id})
            if active is None or active.get("active_generation_id") is not None:
                raise RuntimeError("generation guard was not released")
            print("PASS: P4-03 persistent SSE lifecycle, content, usage and guard release.")
            return 0
        finally:
            if database is not None and session_id is not None:
                database["messages"].delete_many({"session_id": session_id})
                database["sessions"].delete_one({"_id": session_id})
                print("Cleanup: PASS" if database["sessions"].count_documents({"_id": session_id}) == 0 else "Cleanup: FAIL")


if __name__ == "__main__":
    raise SystemExit(main())
