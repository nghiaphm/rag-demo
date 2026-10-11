"""Reconcile các ingestion job bị gián đoạn; không scan/xóa ngoài version metadata."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.cloud_connections import CloudConnections
from app.document_indexes import initialize_document_indexes
from app.ingestion import IngestionError, create_ingestion_service


def main() -> int:
    connections = CloudConnections()
    statuses = connections.connect_all()
    try:
        if not all(status.ok for status in statuses.values()):
            print("BLOCKED: cloud dependencies chưa sẵn sàng; không có credentials nào được in.")
            return 2
        initialize_document_indexes(connections.mongodb.database)
        service = create_ingestion_service(
            database=connections.mongodb.database,
            qdrant_client=connections.qdrant.client,
        )
        summary = service.reconcile_processing()
        print(
            "Reconciliation hoàn tất: "
            f"completed={summary['completed']}, failed={summary['failed']}, skipped={summary['skipped']}"
        )
        return 0
    except IngestionError as exc:
        print(f"FAILED: {exc.code}")
        return 1
    finally:
        connections.close()


if __name__ == "__main__":
    raise SystemExit(main())
