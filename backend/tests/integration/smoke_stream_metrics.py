"""Live P4-05 metrics/reconstruction smoke with Atlas persistence and exact cleanup."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.main import app
from app.chat.pipeline import ProviderStreamChunk
from app.api.streaming.sse_schema import SSETranscript


def _events(body: str) -> list[dict]:
    events: list[dict] = []
    for frame in body.strip().split("\n\n"):
        lines = frame.splitlines()
        if lines:
            events.append(
                {
                    "event": lines[0].removeprefix("event: "),
                    "data": json.loads(lines[1].removeprefix("data: ")),
                }
            )
    return events


def _assert_metric(metric, *, outcome: str, has_content: bool) -> None:
    if metric.outcome != outcome or metric.first_event_ms is None:
        raise RuntimeError("stream metric outcome/first-event mismatch")
    if metric.total_latency_ms < metric.first_event_ms:
        raise RuntimeError("stream metric total latency ordering mismatch")
    if has_content:
        if metric.first_content_ms is None:
            raise RuntimeError("first-content metric is missing")
        if not metric.first_event_ms <= metric.first_content_ms <= metric.total_latency_ms:
            raise RuntimeError("first-content metric ordering mismatch")
    elif metric.first_content_ms is not None:
        raise RuntimeError("empty stream must not have first-content metric")


def main() -> int:
    session_id: str | None = None
    with TestClient(app) as client:
        database = app.state.cloud_connections.mongodb.database
        if database is None:
            print("BLOCKED: MongoDB Atlas is unavailable; secrets are not printed.")
            return 2
        try:
            created = client.post("/sessions", json={"title": "P4-05 isolated smoke"})
            if created.status_code != 201:
                raise RuntimeError(f"create session failed with HTTP {created.status_code}")
            session_id = created.json()["session_id"]
            prepared = SimpleNamespace(sources=[])

            async def success_provider(_prepared):
                await asyncio.sleep(0.01)
                yield ProviderStreamChunk(content="measured ", usage=None)
                await asyncio.sleep(0.01)
                yield ProviderStreamChunk(
                    content="answer",
                    usage={"input_tokens": 2, "output_tokens": 2, "total_tokens": 4},
                )

            success_metrics = []
            with patch("app.api.routes.chat.prepare_rag_stream", return_value=prepared), patch(
                "app.api.routes.chat.astream_rag_answer", success_provider
            ), patch(
                "app.api.routes.chat.record_stream_metric", side_effect=success_metrics.append
            ):
                response = client.post(
                    "/chat/stream",
                    json={"question": "metrics success", "session_id": session_id},
                )
            transcript = SSETranscript(events=_events(response.text))
            if transcript.reconstructed_answer != "measured answer":
                raise RuntimeError("client reconstruction mismatch")
            if len(success_metrics) != 1 or success_metrics[0].delta_count != 2:
                raise RuntimeError("success metric count mismatch")
            _assert_metric(success_metrics[0], outcome="COMPLETED", has_content=True)

            async def empty_provider(_prepared):
                yield ProviderStreamChunk(content=None, usage=None)

            empty_metrics = []
            with patch("app.api.routes.chat.prepare_rag_stream", return_value=prepared), patch(
                "app.api.routes.chat.astream_rag_answer", empty_provider
            ), patch("app.api.routes.chat.record_stream_metric", side_effect=empty_metrics.append):
                empty = client.post(
                    "/chat/stream",
                    json={"question": "metrics empty", "session_id": session_id},
                )
            empty_transcript = SSETranscript(events=_events(empty.text))
            if empty_transcript.events[-1].event != "error":
                raise RuntimeError("empty stream terminal mismatch")
            _assert_metric(empty_metrics[0], outcome="RAG_STREAM_EMPTY", has_content=False)

            async def partial_provider(_prepared):
                yield ProviderStreamChunk(content="partial", usage=None)
                raise RuntimeError("private provider detail")

            partial_metrics = []
            with patch("app.api.routes.chat.prepare_rag_stream", return_value=prepared), patch(
                "app.api.routes.chat.astream_rag_answer", partial_provider
            ), patch(
                "app.api.routes.chat.record_stream_metric", side_effect=partial_metrics.append
            ):
                partial = client.post(
                    "/chat/stream",
                    json={"question": "metrics partial", "session_id": session_id},
                )
            partial_transcript = SSETranscript(events=_events(partial.text))
            if partial_transcript.reconstructed_answer != "partial":
                raise RuntimeError("partial client reconstruction mismatch")
            _assert_metric(partial_metrics[0], outcome="RAG_STREAM_ERROR", has_content=True)

            history = client.get(f"/sessions/{session_id}/messages")
            if history.status_code != 200:
                raise RuntimeError("history read failed")
            items = history.json()["items"]
            if [item["status"] for item in items] != [
                "COMPLETED",
                "COMPLETED",
                "COMPLETED",
                "FAILED",
                "COMPLETED",
                "PARTIAL",
            ]:
                raise RuntimeError("persisted success/empty/partial states mismatch")
            if items[1]["content"] != transcript.reconstructed_answer:
                raise RuntimeError("persisted content differs from client reconstruction")
            session = database["sessions"].find_one({"_id": session_id})
            if session is None or session.get("active_generation_id") is not None:
                raise RuntimeError("generation guard remained after metrics smoke")
            print(
                "PASS: P4-05 first-event/first-content/total latency, empty/partial, "
                "client reconstruction, Atlas persistence and guard release."
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
