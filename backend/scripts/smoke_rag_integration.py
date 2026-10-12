"""Live P5-04 Mongo/Qdrant scope, budget and citation smoke with exact cleanup."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.citation_mapping import map_verified_citations
from app.cloud_connections import CloudConnections
from app.config import settings
from app.conversation_models import (
    MessageRecord,
    MessageRole,
    MessageStatus,
    SessionRecord,
    SessionScope,
    SessionScopeMode,
)
from app.rag.pipeline import prepare_rag_stream
from app.rag.retriever import get_retriever


QUERY = "Retrieval-Augmented Generation kết hợp những thành phần nào?"


def main() -> int:
    connections = CloudConnections()
    session = None
    message_ids: list[str] = []
    try:
        statuses = connections.connect_all()
        if not all(status.ok for status in statuses.values()):
            failed = [name for name, status in statuses.items() if not status.ok]
            print(f"Cloud readiness: FAIL ({','.join(failed)})")
            return 1
        database = connections.mongodb.database
        qdrant = connections.qdrant.client

        baseline = get_retriever(database=database, qdrant_client=qdrant, top_k=1).invoke(
            QUERY
        )
        if not baseline:
            raise RuntimeError("no active baseline candidate")
        selected_document_id = baseline[0].metadata["document_id"]
        selected_version_id = baseline[0].metadata["version_id"]
        session = SessionRecord(
            title="P5-04 isolated integration smoke",
            scope=SessionScope(
                mode=SessionScopeMode.SELECTED_DOCUMENTS,
                document_ids=[selected_document_id],
            ),
        )
        request_id = str(uuid4())
        history = [
            MessageRecord(
                session_id=session.session_id,
                sequence=1,
                role=MessageRole.USER,
                content="RAG là chủ đề đang được thảo luận.",
                status=MessageStatus.COMPLETED,
                request_id=request_id,
            ),
            MessageRecord(
                session_id=session.session_id,
                sequence=2,
                role=MessageRole.ASSISTANT,
                content="Tôi sẽ chỉ trả lời dựa trên tài liệu được truy xuất.",
                status=MessageStatus.COMPLETED,
                request_id=request_id,
            ),
        ]
        message_ids.extend(message.message_id for message in history)
        database["sessions"].insert_one(session.to_mongo())
        database["messages"].insert_many([message.to_mongo() for message in history])

        prepared = prepare_rag_stream(
            QUERY,
            database=database,
            qdrant_client=qdrant,
            session_id=session.session_id,
        )
        if not prepared.sources:
            raise RuntimeError("selected scope returned no candidates")
        if prepared.active_version_ids != (selected_version_id,):
            raise RuntimeError("selected scope did not resolve exact active version")
        if any(
            source["document_id"] != selected_document_id
            or source["version_id"] != selected_version_id
            for source in prepared.sources
        ):
            raise RuntimeError("retrieval escaped selected active scope")
        if prepared.original_query != QUERY or prepared.retrieval_query != QUERY:
            raise RuntimeError("independent query should keep original retrieval query")
        if len(prepared.history_turns) != 1:
            raise RuntimeError("whole-turn history was not included")
        if prepared.budget.usage.total > settings.rag_context_window_tokens:
            raise RuntimeError("context budget exceeded")
        citations = map_verified_citations("Grounded smoke answer [1]", prepared.sources)
        if len(citations) != 1:
            raise RuntimeError("citation did not map to retrieved source")

        print(
            "PASS: P5-04 selected active scope, whole-turn history, shared budgeted "
            "context and Qdrant/Mongo citation traceability."
        )
        print(
            f"Counts: active_versions={len(prepared.active_version_ids)}; "
            f"sources={len(prepared.sources)}; history_turns={len(prepared.history_turns)}"
        )
        return 0
    finally:
        if connections.mongodb.database is not None and session is not None:
            database = connections.mongodb.database
            database["messages"].delete_many(
                {"_id": {"$in": message_ids}, "session_id": session.session_id}
            )
            database["sessions"].delete_one({"_id": session.session_id})
            remaining = database["messages"].count_documents(
                {"session_id": session.session_id}
            ) + database["sessions"].count_documents({"_id": session.session_id})
            print(f"Cleanup: {'PASS' if remaining == 0 else 'FAIL'}")
        connections.close()


if __name__ == "__main__":
    raise SystemExit(main())
