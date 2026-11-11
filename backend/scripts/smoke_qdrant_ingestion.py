"""Live smoke riêng cho embedding -> Qdrant adapter upsert/verify/cleanup."""

import sys
from pathlib import Path
from uuid import uuid4

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.infrastructure.qdrant import QdrantConnection
from app.shared.config import settings
from app.infrastructure.qdrant_vector_index import QdrantVectorIndex
from app.rag.embeddings import get_embeddings
from app.rag.vector_index import VectorFilter, VectorRecord, chunk_point_id


def main() -> int:
    connection = QdrantConnection()
    status = connection.connect()
    if not status.ok:
        print(f"BLOCKED: qdrant={status.code}; credentials không được in.")
        return 2

    version_id = str(uuid4())
    document_id = str(uuid4())
    index = QdrantVectorIndex(connection.client, settings.qdrant_collection)
    stage = "embedding"
    try:
        chunk_text = "Non-sensitive Qdrant adapter smoke content."
        vectors = get_embeddings().embed_documents([chunk_text])
        stage = "upsert"
        index.upsert([
            VectorRecord(
                point_id=chunk_point_id(version_id, 0),
                document_id=document_id,
                version_id=version_id,
                chunk_index=0,
                file_name="qdrant-adapter-smoke.md",
                chunk_text=chunk_text,
                vector=tuple(vectors[0]),
            )
        ])
        stage = "verify"
        if index.count(VectorFilter(version_id=version_id)) != 1:
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
                index.delete(VectorFilter(version_id=version_id))
                # Dọn cả point test từ lần smoke trước nếu verify từng lỗi sau upsert.
                smoke_filter = VectorFilter(file_name="qdrant-adapter-smoke.md")
                index.delete(smoke_filter)
                smoke_count = index.count(smoke_filter)
                print(
                    "Cleanup: PASS"
                    if index.count(VectorFilter(version_id=version_id)) == 0
                    and smoke_count == 0
                    else "Cleanup: FAILED"
                )
            else:
                print("Cleanup: PASS (collection chưa được tạo)")
        except Exception:
            print("Cleanup: FAILED")
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
