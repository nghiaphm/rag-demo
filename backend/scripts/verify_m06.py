"""M-06 live cross-phase regression on isolated session data.

MongoDB Atlas, Qdrant Cloud, embeddings, FastAPI routes and persistence are real.
Rewrite and generation are deterministic so this gate does not depend on LLM quota.
The script creates one selected-scope session, then deletes only that session and
its messages. It never mutates documents, raw files or Qdrant points.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.conversations.models import (
    MessageRecord,
    MessageRole,
    MessageStatus,
    SessionRecord,
    SessionScope,
    SessionScopeMode,
)
from app.main import app
from app.chat.query_rewriting import (
    QueryRewriteResult,
    RewriteMetrics,
    RewriteStatus,
)
from app.rag.retriever import get_retriever


RETRIEVAL_QUERY = "Retrieval-Augmented Generation kết hợp những thành phần nào?"
JSON_QUESTION = "Còn nó kết hợp những thành phần nào?"
STREAM_QUESTION = "Vậy nó dựa trên nguồn nào?"


class RecordingRewriter:
    """Deterministic dependent-query rewrite while recording selected history."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def rewrite(self, query: str, history_turns: tuple) -> QueryRewriteResult:
        self.calls.append((query, len(history_turns)))
        return QueryRewriteResult(
            original_query=query,
            retrieval_query=RETRIEVAL_QUERY,
            rewritten=True,
            status=RewriteStatus.REWRITTEN,
            dependency_reason="context_reference",
            metrics=RewriteMetrics(1, 1.0, 8, 4, 12, "estimated"),
        )


class DeterministicLlm:
    """Provider-shaped async interface for stable JSON and SSE assertions."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def _record(self, prompt) -> None:
        messages = getattr(prompt, "to_messages", lambda: [])()
        self.prompts.append("\n".join(str(message.content) for message in messages))

    async def ainvoke(self, prompt):
        self._record(prompt)
        return SimpleNamespace(
            content="M-06 JSON grounded answer [1]",
            usage_metadata={
                "input_tokens": 8,
                "output_tokens": 4,
                "total_tokens": 12,
            },
        )

    async def astream(self, prompt):
        self._record(prompt)
        yield SimpleNamespace(content="M-06 stream ", usage_metadata=None)
        yield SimpleNamespace(
            content="grounded answer [1]",
            usage_metadata={
                "input_tokens": 6,
                "output_tokens": 3,
                "total_tokens": 9,
            },
        )


def _events(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for frame in body.strip().split("\n\n"):
        lines = frame.splitlines()
        if len(lines) != 2 or not lines[0].startswith("event: "):
            raise RuntimeError("invalid SSE frame")
        if not lines[1].startswith("data: "):
            raise RuntimeError("invalid SSE data")
        events.append(
            (
                lines[0].removeprefix("event: "),
                json.loads(lines[1].removeprefix("data: ")),
            )
        )
    return events


def _assert_scoped_sources(
    sources: list[dict], *, document_id: str, version_id: str
) -> None:
    if not sources:
        raise RuntimeError("selected scope returned no sources")
    if any(
        source.get("document_id") != document_id
        or source.get("version_id") != version_id
        for source in sources
    ):
        raise RuntimeError("retrieval escaped selected active scope")
    for source in sources:
        UUID(str(source.get("chunk_id")))


def _assert_citation(citations: list[dict], source: dict) -> None:
    if len(citations) != 1:
        raise RuntimeError("verified citation count mismatch")
    citation = citations[0]
    for field in ("chunk_id", "document_id", "version_id", "page"):
        if citation.get(field) != source.get(field):
            raise RuntimeError("verified citation provenance mismatch")


def main() -> int:
    session: SessionRecord | None = None
    database = None
    rewriter = RecordingRewriter()
    llm = DeterministicLlm()

    with TestClient(app) as client:
        try:
            readiness = client.get("/health/dependencies")
            if readiness.status_code != 200 or readiness.json().get("status") != "ok":
                print("BLOCKED: cloud dependencies are unavailable; secrets are not printed.")
                return 2
            cloud = app.state.cloud_connections
            database = cloud.mongodb.database
            qdrant = cloud.qdrant.client
            if database is None or qdrant is None:
                print("BLOCKED: cloud clients are unavailable; secrets are not printed.")
                return 2

            baseline = get_retriever(
                database=database,
                qdrant_client=qdrant,
                top_k=1,
            ).invoke(RETRIEVAL_QUERY)
            if not baseline:
                raise RuntimeError("application collection has no active baseline candidate")
            document_id = baseline[0].metadata["document_id"]
            version_id = baseline[0].metadata["version_id"]

            session = SessionRecord(
                title="M-06 isolated cross-phase verification",
                scope=SessionScope(
                    mode=SessionScopeMode.SELECTED_DOCUMENTS,
                    document_ids=[document_id],
                ),
                next_message_sequence=3,
            )
            seed_request_id = str(uuid4())
            seed_messages = [
                MessageRecord(
                    session_id=session.session_id,
                    sequence=1,
                    role=MessageRole.USER,
                    content="Chúng ta đang thảo luận về RAG.",
                    status=MessageStatus.COMPLETED,
                    request_id=seed_request_id,
                ),
                MessageRecord(
                    session_id=session.session_id,
                    sequence=2,
                    role=MessageRole.ASSISTANT,
                    content="RAG kết hợp retrieval với generation dựa trên tài liệu.",
                    status=MessageStatus.COMPLETED,
                    request_id=seed_request_id,
                ),
            ]
            database["sessions"].insert_one(session.to_mongo())
            database["messages"].insert_many(
                [message.to_mongo() for message in seed_messages]
            )

            with patch(
                "app.chat.pipeline.create_query_rewriter", return_value=rewriter
            ), patch("app.chat.pipeline.get_llm", return_value=llm):
                json_response = client.post(
                    "/chat",
                    json={"question": JSON_QUESTION, "session_id": session.session_id},
                )
                if json_response.status_code != 200:
                    raise RuntimeError(
                        f"persistent JSON failed with HTTP {json_response.status_code}"
                    )
                json_body = json_response.json()
                if (
                    json_body.get("status") != "COMPLETED"
                    or json_body.get("metadata", {}).get("mode") != "PERSISTENT"
                    or json_body.get("session_id") != session.session_id
                ):
                    raise RuntimeError("persistent JSON contract mismatch")
                _assert_scoped_sources(
                    json_body["sources"],
                    document_id=document_id,
                    version_id=version_id,
                )
                _assert_citation(json_body["citations"], json_body["sources"][0])
                if json_body.get("usage", {}).get("total_tokens") != 12:
                    raise RuntimeError("JSON usage mismatch")

                stream_response = client.post(
                    "/chat/stream",
                    json={"question": STREAM_QUESTION, "session_id": session.session_id},
                    headers={"Accept": "text/event-stream"},
                )
                if stream_response.status_code != 200:
                    raise RuntimeError(
                        f"persistent SSE failed with HTTP {stream_response.status_code}"
                    )

            events = _events(stream_response.text)
            names = [name for name, _ in events]
            if names != ["start", "metadata", "delta", "delta", "done"]:
                raise RuntimeError("SSE event order mismatch")
            if [data["sequence"] for _, data in events] != list(
                range(1, len(events) + 1)
            ):
                raise RuntimeError("SSE sequence mismatch")
            start = events[0][1]
            if (
                start.get("mode") != "PERSISTENT"
                or start.get("session_id") != session.session_id
            ):
                raise RuntimeError("SSE persistent IDs mismatch")
            metadata_sources = events[1][1]["sources"]
            _assert_scoped_sources(
                metadata_sources,
                document_id=document_id,
                version_id=version_id,
            )
            reconstructed = "".join(
                data["content"] for name, data in events if name == "delta"
            )
            if reconstructed != "M-06 stream grounded answer [1]":
                raise RuntimeError("SSE reconstruction mismatch")
            if events[-1][1].get("usage", {}).get("total_tokens") != 9:
                raise RuntimeError("SSE usage mismatch")

            history_response = client.get(
                f"/sessions/{session.session_id}/messages?offset=0&limit=20"
            )
            if history_response.status_code != 200:
                raise RuntimeError("persistent history read failed")
            items = history_response.json()["items"]
            if len(items) != 6 or [item["sequence"] for item in items] != list(
                range(1, 7)
            ):
                raise RuntimeError("cross-transport history order mismatch")
            if any(item["status"] != "COMPLETED" for item in items):
                raise RuntimeError("cross-transport terminal state mismatch")
            if items[2]["request_id"] != items[3]["request_id"] or items[4][
                "request_id"
            ] != items[5]["request_id"]:
                raise RuntimeError("request/message linkage mismatch")
            if items[3]["citations"] != json_body["citations"]:
                raise RuntimeError("JSON citation persistence mismatch")
            _assert_citation(items[5]["citations"], metadata_sources[0])
            if items[5].get("usage", {}).get("total_tokens") != 9:
                raise RuntimeError("SSE usage persistence mismatch")

            stored_session = database["sessions"].find_one(
                {"_id": session.session_id}
            )
            if stored_session is None:
                raise RuntimeError("isolated session disappeared")
            if stored_session.get("scope", {}).get("mode") != "SELECTED_DOCUMENTS":
                raise RuntimeError("session scope changed")
            if stored_session.get("active_generation_id") is not None:
                raise RuntimeError("generation guard was not released")

            if rewriter.calls != [(JSON_QUESTION, 1), (STREAM_QUESTION, 2)]:
                raise RuntimeError("history-aware rewrite calls mismatch")
            if len(llm.prompts) != 2:
                raise RuntimeError("JSON/SSE did not both reach shared generation")
            if JSON_QUESTION not in llm.prompts[0] or STREAM_QUESTION not in llm.prompts[1]:
                raise RuntimeError("final generation did not preserve original query")

            print(
                "PASS: M-06 selected session scope, whole-turn history, conditional "
                "rewrite, JSON/SSE contracts, citation provenance and persistence."
            )
            print(
                "Counts: transports=2; messages=6; rewrite_calls=2; "
                f"json_sources={len(json_body['sources'])}; "
                f"stream_sources={len(metadata_sources)}"
            )
            return 0
        finally:
            if database is not None and session is not None:
                database["messages"].delete_many(
                    {"session_id": session.session_id}
                )
                database["sessions"].delete_one({"_id": session.session_id})
                remaining = database["messages"].count_documents(
                    {"session_id": session.session_id}
                ) + database["sessions"].count_documents(
                    {"_id": session.session_id}
                )
                print(f"Cleanup: {'PASS' if remaining == 0 else 'FAIL'}")


if __name__ == "__main__":
    raise SystemExit(main())
