"""Read-only P3-02 citation mapping smoke on real active Qdrant candidates."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.chat.citation_mapping import map_verified_citations
from app.infrastructure.connections import CloudConnections
from app.chat.pipeline import _to_source
from app.rag.retriever import get_retriever


def main() -> int:
    connections = CloudConnections()
    try:
        statuses = connections.connect_all()
        if not all(status.ok for status in statuses.values()):
            failed = [name for name, status in statuses.items() if not status.ok]
            print(f"Cloud readiness: FAIL ({','.join(failed)})")
            return 1

        database = connections.mongodb.database
        qdrant_client = connections.qdrant.client
        documents = get_retriever(
            database=database,
            qdrant_client=qdrant_client,
            top_k=3,
        ).invoke("Retrieval-Augmented Generation kết hợp những thành phần nào?")
        if not documents:
            raise RuntimeError("no active Qdrant candidates returned")
        sources = [_to_source(document) for document in documents]

        # The model may select only [1]. Any UUID-like text is ignored by the mapper.
        answer = f"Câu trả lời dùng candidate đầu tiên [1]; ignored={uuid4()}"
        citations = map_verified_citations(answer, sources)
        if len(citations) != 1:
            raise RuntimeError("verified citation count mismatch")
        citation = citations[0]
        first = sources[0]
        for field in ("chunk_id", "document_id", "version_id", "page"):
            if citation[field] != first[field]:
                raise RuntimeError(f"citation {field} does not match retrieved payload")

        active = database["documents"].find_one(
            {
                "_id": citation["document_id"],
                "active_version_id": citation["version_id"],
                "deleted_at": None,
            },
            {"_id": 1},
        )
        if active is None:
            raise RuntimeError("citation does not point to an active MongoDB version")

        print(
            "PASS: real active Qdrant candidates retrieved; one server ordinal mapped "
            "to verified chunk/document/version/page and MongoDB active version."
        )
        print(f"Counts: candidates={len(sources)}; citations={len(citations)}")
        return 0
    finally:
        connections.close()


if __name__ == "__main__":
    raise SystemExit(main())
