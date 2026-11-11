"""Live P4-02 SSE provider-stream transport smoke with read-only cloud readiness."""

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


def _frames(text: str) -> list[tuple[str, dict]]:
    return [
        (
            frame.splitlines()[0].removeprefix("event: "),
            json.loads(frame.splitlines()[1].removeprefix("data: ")),
        )
        for frame in text.strip().split("\n\n")
    ]


def main() -> int:
    source = {
        "chunk_id": str(uuid4()),
        "document_id": str(uuid4()),
        "version_id": str(uuid4()),
        "file_name": "p4-01-smoke.md",
        "page": 0,
    }
    prepared = SimpleNamespace(sources=[source])

    async def provider_stream(_prepared):
        yield ProviderStreamChunk(content="P4-02 ", usage=None)
        yield ProviderStreamChunk(content=None, usage=None)
        yield ProviderStreamChunk(
            content="deterministic answer [1]",
            usage={"input_tokens": 4, "output_tokens": 3, "total_tokens": 7},
        )

    with TestClient(app) as client:
        health = client.get("/health/dependencies")
        if health.status_code != 200 or health.json().get("status") != "ok":
            print("BLOCKED: cloud dependencies chưa sẵn sàng; credentials không được in.")
            return 2
        with patch("app.api.routes.chat.prepare_rag_stream", return_value=prepared), patch(
            "app.api.routes.chat.astream_rag_answer", provider_stream
        ):
            response = client.post("/chat/stream", json={"question": "stream smoke"})
        if response.status_code != 200:
            raise RuntimeError(f"stream endpoint failed with HTTP {response.status_code}")
        if not response.headers.get("content-type", "").startswith("text/event-stream"):
            raise RuntimeError("SSE content type mismatch")
        events = _frames(response.text)
        if [event for event, _ in events] != [
            "start",
            "metadata",
            "delta",
            "delta",
            "done",
        ]:
            raise RuntimeError("SSE event order mismatch")
        if [data["sequence"] for _, data in events] != [1, 2, 3, 4, 5]:
            raise RuntimeError("SSE sequence mismatch")
        if events[2][1]["content"] != "P4-02 ":
            raise RuntimeError("SSE delta mismatch")
        if events[4][1]["status"] != "COMPLETED":
            raise RuntimeError("SSE terminal mismatch")
        if events[4][1]["usage"]["total_tokens"] != 7:
            raise RuntimeError("SSE usage mismatch")
    print("PASS: P4-02 normalized provider deltas, usage and cloud readiness.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
