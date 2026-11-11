"""Tạo/xác minh MongoDB indexes trên Atlas; không ghi application data."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.infrastructure.mongo import MongoDBConnection
from app.conversations.indexes import (
    CONVERSATION_INDEX_DEFINITIONS,
    initialize_conversation_indexes,
)
from app.documents.indexes import INDEX_DEFINITIONS, initialize_document_indexes


def main() -> int:
    connection = MongoDBConnection()
    try:
        status = connection.connect()
        if not status.ok:
            print(f"mongodb: ok=False; code={status.code}; message={status.message}")
            return 1

        definitions = {**INDEX_DEFINITIONS, **CONVERSATION_INDEX_DEFINITIONS}
        first = {
            **initialize_document_indexes(connection.database),
            **initialize_conversation_indexes(connection.database),
        }
        second = {
            **initialize_document_indexes(connection.database),
            **initialize_conversation_indexes(connection.database),
        }
        verified = True
        for collection_name, expected_indexes in definitions.items():
            actual_names = set(connection.database[collection_name].index_information())
            expected_names = {index.document["name"] for index in expected_indexes}
            collection_ok = expected_names.issubset(actual_names)
            verified = verified and collection_ok
            print(
                f"{collection_name}: expected={len(expected_names)}; "
                f"verified={collection_ok}; idempotent={first[collection_name] == second[collection_name]}"
            )
        return 0 if verified else 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
