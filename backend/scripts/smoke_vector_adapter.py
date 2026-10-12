"""Live M-03 smoke cho add/upsert/query/filter/delete trên Qdrant Cloud."""

import sys
from pathlib import Path
from uuid import uuid4

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.cloud_connections import QdrantConnection
from app.config import settings
from app.qdrant_ingestion import QdrantVectorIndex
from app.rag.embeddings import get_embeddings
from app.vector_index import (
    VectorConflictError,
    VectorFilter,
    VectorRecord,
    chunk_point_id,
)


def main() -> int:
    connection = QdrantConnection()
    status = connection.connect()
    if not status.ok:
        print(f"BLOCKED: qdrant={status.code}; credentials không được in.")
        return 2

    adapter = QdrantVectorIndex(connection.client, settings.qdrant_collection)
    document_id = str(uuid4())
    first_version = str(uuid4())
    second_version = str(uuid4())
    file_name = f"m03-vector-smoke-{uuid4()}.md"
    cleanup_filter = VectorFilter(file_name=file_name)
    stage = "embedding"
    try:
        texts = [
            "M03 alpha marker for vector adapter verification.",
            "M03 beta marker for filtered vector retrieval.",
        ]
        embeddings = get_embeddings()
        vectors = embeddings.embed_documents(texts)
        records = [
            VectorRecord(
                point_id=chunk_point_id(first_version, 0),
                document_id=document_id,
                version_id=first_version,
                chunk_index=0,
                file_name=file_name,
                chunk_text=texts[0],
                vector=tuple(vectors[0]),
                page=1,
            ),
            VectorRecord(
                point_id=chunk_point_id(second_version, 0),
                document_id=document_id,
                version_id=second_version,
                chunk_index=0,
                file_name=file_name,
                chunk_text=texts[1],
                vector=tuple(vectors[1]),
                page=2,
            ),
        ]

        stage = "add"
        adapter.add(records)
        try:
            adapter.add([records[0]])
            raise RuntimeError("duplicate add unexpectedly succeeded")
        except VectorConflictError:
            pass

        stage = "query_filter"
        query_vector = embeddings.embed_query("beta marker")
        hits = adapter.query(
            query_vector,
            limit=5,
            filters=VectorFilter(
                document_id=document_id,
                version_id=second_version,
                file_name=file_name,
            ),
        )
        if (
            len(hits) != 1
            or hits[0].version_id != second_version
            or hits[0].page != 2
            or hits[0].chunk_text != texts[1]
        ):
            raise RuntimeError("filtered query mismatch")

        stage = "upsert"
        updated_text = "M03 beta marker updated through idempotent upsert."
        updated_vector = embeddings.embed_documents([updated_text])[0]
        adapter.upsert([
            VectorRecord(
                point_id=records[1].point_id,
                document_id=document_id,
                version_id=second_version,
                chunk_index=0,
                file_name=file_name,
                chunk_text=updated_text,
                vector=tuple(updated_vector),
                page=2,
            )
        ])
        updated = adapter.query(
            updated_vector,
            limit=1,
            filters=VectorFilter(version_id=second_version),
        )
        if len(updated) != 1 or updated[0].chunk_text != updated_text:
            raise RuntimeError("upsert verification mismatch")

        stage = "delete"
        adapter.delete(VectorFilter(version_id=first_version))
        if adapter.count(VectorFilter(version_id=first_version)) != 0:
            raise RuntimeError("version delete mismatch")
        if adapter.count(VectorFilter(document_id=document_id)) != 1:
            raise RuntimeError("document filter count mismatch")
        adapter.delete(VectorFilter(document_id=document_id))
        if adapter.query(query_vector, limit=5, filters=cleanup_filter):
            raise RuntimeError("document remained retrievable")

        print("PASS: M-03 add/upsert/query/filter/delete verified on Qdrant Cloud.")
        return 0
    except Exception as exc:
        print(
            f"FAILED: stage={stage}; type={type(exc).__name__}; "
            "credentials/raw exception không được in."
        )
        return 1
    finally:
        cleanup_ok = False
        try:
            adapter.delete(cleanup_filter)
            cleanup_ok = adapter.count(cleanup_filter) == 0
        except Exception:
            cleanup_ok = False
        print("Cleanup: PASS" if cleanup_ok else "Cleanup: FAILED")
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
