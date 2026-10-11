"""Live smoke riêng cho embedding -> Qdrant upsert/verify/cleanup của P1-05."""

import sys
from pathlib import Path
from uuid import uuid4

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from langchain_core.documents import Document

from app.cloud_connections import QdrantConnection
from app.config import settings
from qdrant_client.http.models import FieldCondition, Filter, MatchValue

from app.qdrant_ingestion import QdrantIngestionIndex
from app.rag.embeddings import get_embeddings


def main() -> int:
    connection = QdrantConnection()
    status = connection.connect()
    if not status.ok:
        print(f"BLOCKED: qdrant={status.code}; credentials không được in.")
        return 2

    version_id = str(uuid4())
    index = QdrantIngestionIndex(connection.client, settings.qdrant_collection)
    stage = "embedding"
    try:
        chunks = [Document(page_content="Non-sensitive P1-05 Qdrant smoke content.")]
        vectors = get_embeddings().embed_documents([chunks[0].page_content])
        stage = "upsert"
        index.upsert_version(
            document_id=str(uuid4()),
            version_id=version_id,
            file_name="p1-05-qdrant-smoke.md",
            chunks=chunks,
            vectors=vectors,
        )
        stage = "verify"
        if index.count_version(version_id) != 1:
            print("FAILED: Qdrant count verification mismatch.")
            return 1
        print(f"PASS: embedding + Qdrant upsert/verify ({len(vectors[0])} dimensions).")
        return 0
    except Exception as exc:
        print(f"FAILED: stage={stage}; type={type(exc).__name__}; raw exception không được in.")
        return 1
    finally:
        try:
            if connection.client.collection_exists(settings.qdrant_collection):
                index.delete_version(version_id)
                # Dọn cả point test từ lần smoke trước nếu verify từng lỗi sau upsert.
                connection.client.delete(
                    collection_name=settings.qdrant_collection,
                    points_selector=Filter(
                        must=[
                            FieldCondition(
                                key="file_name",
                                match=MatchValue(value="p1-05-qdrant-smoke.md"),
                            )
                        ]
                    ),
                    wait=True,
                )
                smoke_filter = Filter(
                    must=[
                        FieldCondition(
                            key="file_name",
                            match=MatchValue(value="p1-05-qdrant-smoke.md"),
                        )
                    ]
                )
                smoke_count = connection.client.count(
                    collection_name=settings.qdrant_collection,
                    count_filter=smoke_filter,
                    exact=True,
                ).count
                print(
                    "Cleanup: PASS"
                    if index.count_version(version_id) == 0 and smoke_count == 0
                    else "Cleanup: FAILED"
                )
            else:
                print("Cleanup: PASS (collection chưa được tạo)")
        except Exception:
            print("Cleanup: FAILED")
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
