"""M-04: migrate the explicit repository demo corpus to MongoDB/Qdrant."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.infrastructure.connections import CloudConnections
from app.shared.config import settings
from app.documents.migrations.demo_corpus import DemoCorpusMigration, MigrationSource
from app.documents.indexes import initialize_document_indexes
from app.documents.repository import MongoDocumentRepository
from app.documents.ingestion import IngestionService
from app.infrastructure.qdrant_vector_index import QdrantVectorIndex
from app.rag.embeddings import get_embeddings
from app.infrastructure.storage import create_file_storage

MANIFEST_PATH = BACKEND_DIR / "migration" / "demo_corpus.json"
DEMO_SOURCE_ROOT = (PROJECT_ROOT / "data" / "documents").resolve()
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")


def load_manifest(path: Path = MANIFEST_PATH) -> list[MigrationSource]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        namespace = payload["namespace"]
        documents = payload["documents"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("Manifest migration không hợp lệ") from exc
    if not isinstance(namespace, str) or not _IDENTIFIER.fullmatch(namespace):
        raise ValueError("Manifest namespace không hợp lệ")
    if not isinstance(documents, list) or not documents:
        raise ValueError("Manifest không có documents")

    sources: list[MigrationSource] = []
    for item in documents:
        try:
            source_id = item["source_id"]
            relative_path = Path(item["path"])
        except (KeyError, TypeError) as exc:
            raise ValueError("Manifest document không hợp lệ") from exc
        if not isinstance(source_id, str) or not _IDENTIFIER.fullmatch(source_id):
            raise ValueError("Manifest source_id không hợp lệ")
        source_path = (PROJECT_ROOT / relative_path).resolve()
        if not source_path.is_relative_to(DEMO_SOURCE_ROOT) or not source_path.is_file():
            raise ValueError("Manifest source path không hợp lệ")
        sources.append(MigrationSource(f"{namespace}:{source_id}", source_path))
    if len({source.source_key for source in sources}) != len(sources):
        raise ValueError("Manifest có source_id trùng")
    return sources


def main() -> int:
    try:
        sources = load_manifest()
    except ValueError as exc:
        print(f"FAILED: {exc}")
        return 2

    connections = CloudConnections()
    try:
        statuses = connections.connect_all()
        for name, status in statuses.items():
            print(f"{name}: ok={status.ok}; code={status.code}")
        if not all(status.ok for status in statuses.values()):
            print("BLOCKED: cloud dependencies chưa sẵn sàng; credentials không được in.")
            return 2
        database = connections.mongodb.database
        qdrant_client = connections.qdrant.client
        if database is None or qdrant_client is None:
            print("BLOCKED: cloud clients chưa sẵn sàng.")
            return 2

        initialize_document_indexes(database)
        repository = MongoDocumentRepository(database)
        storage = create_file_storage(settings)
        vector_index = QdrantVectorIndex(qdrant_client, settings.qdrant_collection)
        embeddings = get_embeddings()
        ingestion = IngestionService(
            repository=repository,
            storage=storage,
            vector_index=vector_index,
            embeddings=embeddings,
            embedding_model=settings.embedding_model,
        )
        migration = DemoCorpusMigration(
            repository=repository,
            storage=storage,
            vector_index=vector_index,
            ingestion=ingestion,
            embeddings=embeddings,
        )
        summary = migration.migrate(sources)
        for item in summary.items:
            suffix = f"; error={item.error_code}" if item.error_code else ""
            print(
                f"{item.file_name}: {item.outcome}; chunks={item.chunk_count}{suffix}"
            )
        print(
            "summary: "
            f"created={summary.created}; updated={summary.updated}; "
            f"verified={summary.verified}; failed={summary.failed}"
        )
        return 0 if summary.failed == 0 and len(summary.items) == len(sources) else 1
    except Exception:
        print("FAILED: migration gặp lỗi nội bộ; không in raw exception hoặc credentials.")
        return 1
    finally:
        connections.close()


if __name__ == "__main__":
    raise SystemExit(main())
