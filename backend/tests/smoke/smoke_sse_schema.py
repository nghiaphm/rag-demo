"""Offline P3-03 typed SSE transcript and wire-format smoke test."""

import json
import sys
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.api.schemas.chat_documents import ChatResponseMode, Citation
from app.api.streaming.sse_schema import (
    SSECitationData,
    SSECitationEvent,
    SSEDeltaData,
    SSEDeltaEvent,
    SSEDoneData,
    SSEDoneEvent,
    SSEMetadataData,
    SSEMetadataEvent,
    SSEStartData,
    SSEStartEvent,
    SSETranscript,
    encode_sse_event,
)


def main() -> int:
    citation = Citation(
        chunk_id=uuid4(), document_id=uuid4(), version_id=uuid4(), page=1
    )
    source = {
        "chunk_id": str(citation.chunk_id),
        "document_id": str(citation.document_id),
        "version_id": str(citation.version_id),
        "page": 1,
    }
    transcript = SSETranscript(
        events=[
            SSEStartEvent(
                data=SSEStartData(
                    sequence=1,
                    request_id=uuid4(),
                    session_id=uuid4(),
                    user_message_id=uuid4(),
                    assistant_message_id=uuid4(),
                    mode=ChatResponseMode.PERSISTENT,
                )
            ),
            SSEMetadataEvent(
                data=SSEMetadataData(
                    sequence=2, model="provider/model", sources=[source]
                )
            ),
            SSECitationEvent(
                data=SSECitationData(sequence=3, citation=citation)
            ),
            SSEDeltaEvent(data=SSEDeltaData(sequence=4, content="Xin ")),
            SSEDeltaEvent(data=SSEDeltaData(sequence=5, content="chào")),
            SSEDoneEvent(data=SSEDoneData(sequence=6, usage=None)),
        ]
    )
    frames = [encode_sse_event(event) for event in transcript.events]
    for frame, event in zip(frames, transcript.events):
        lines = frame.splitlines()
        if lines[0] != f"event: {event.event}":
            raise RuntimeError("SSE event line mismatch")
        json.loads(lines[1].removeprefix("data: "))
    if transcript.reconstructed_answer != "Xin chào":
        raise RuntimeError("delta reconstruction mismatch")
    print(
        "PASS: start/metadata/citation/delta/done order, stable IDs, JSON data "
        "frames, single terminal and client reconstruction verified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
