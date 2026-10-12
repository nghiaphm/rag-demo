"""Live P4-04 Atlas smoke for post-header provider failure and timeout.

The script uses one isolated session, deterministic mocked provider streams and
exact cleanup. It never sends document content to an external LLM.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.config import settings
from app.main import app
from app.rag.pipeline import ProviderStreamChunk


def _frames(body: str) -> list[tuple[str, dict]]:
    frames: list[tuple[str, dict]] = []
    for frame in body.strip().split("\n\n"):
        lines = frame.splitlines()
        if lines:
            frames.append(
                (
                    lines[0].removeprefix("event: "),
                    json.loads(lines[1].removeprefix("data: ")),
                )
            )
    return frames


def main() -> int:
    session_id: str | None = None
    with TestClient(app) as client:
        database = app.state.cloud_connections.mongodb.database
        if database is None:
            print("BLOCKED: MongoDB Atlas is unavailable; secrets are not printed.")
            return 2
        try:
            created = client.post("/sessions", json={"title": "P4-04 isolated smoke"})
            if created.status_code != 201:
                raise RuntimeError(f"create session failed with HTTP {created.status_code}")
            session_id = created.json()["session_id"]
            prepared = SimpleNamespace(sources=[])

            async def partial_failure(_prepared):
                yield ProviderStreamChunk(content="partial", usage=None)
                raise RuntimeError("private provider detail")

            with patch("app.api.chat.prepare_rag_stream", return_value=prepared), patch(
                "app.api.chat.astream_rag_answer", partial_failure
            ):
                partial_response = client.post(
                    "/chat/stream",
                    json={"question": "partial failure", "session_id": session_id},
                )
            partial_events = _frames(partial_response.text)
            if [name for name, _ in partial_events] != ["start", "metadata", "delta", "error"]:
                raise RuntimeError("partial failure event order mismatch")
            if partial_events[-1][1]["status"] != "PARTIAL":
                raise RuntimeError("partial failure terminal status mismatch")
            if "private provider detail" in partial_response.text:
                raise RuntimeError("raw provider error leaked")

            async def slow_provider(_prepared):
                await asyncio.sleep(1)
                yield ProviderStreamChunk(content="late", usage=None)

            with patch("app.api.chat.prepare_rag_stream", return_value=prepared), patch(
                "app.api.chat.astream_rag_answer", slow_provider
            ), patch.object(settings, "stream_timeout_seconds", 0.01):
                timeout_response = client.post(
                    "/chat/stream",
                    json={"question": "timeout", "session_id": session_id},
                )
            timeout_events = _frames(timeout_response.text)
            if [name for name, _ in timeout_events] != ["start", "metadata", "error"]:
                raise RuntimeError("timeout event order mismatch")
            if timeout_events[-1][1]["error"]["code"] != "RAG_STREAM_TIMEOUT":
                raise RuntimeError("timeout error code mismatch")

            history = client.get(f"/sessions/{session_id}/messages")
            if history.status_code != 200:
                raise RuntimeError("history read failed")
            items = history.json()["items"]
            if [item["status"] for item in items] != [
                "COMPLETED",
                "PARTIAL",
                "COMPLETED",
                "FAILED",
            ]:
                raise RuntimeError("persisted terminal states mismatch")
            if items[1]["error_code"] != "RAG_STREAM_ERROR":
                raise RuntimeError("partial persistence error code mismatch")
            if items[3]["error_code"] != "RAG_STREAM_TIMEOUT":
                raise RuntimeError("timeout persistence error code mismatch")
            session = database["sessions"].find_one({"_id": session_id})
            if session is None or session.get("active_generation_id") is not None:
                raise RuntimeError("generation guard remained after error")
            print("PASS: P4-04 safe SSE errors, timeout, Atlas states and guard release.")
            return 0
        finally:
            if database is not None and session_id is not None:
                database["messages"].delete_many({"session_id": session_id})
                database["sessions"].delete_one({"_id": session_id})
                remaining = database["sessions"].count_documents({"_id": session_id})
                print(f"Cleanup: {'PASS' if remaining == 0 else 'FAIL'}")


if __name__ == "__main__":
    raise SystemExit(main())
