"""Live P2-01 smoke test trên Atlas với test IDs riêng và cleanup chính xác."""

import sys
from pathlib import Path
from uuid import uuid4

from pymongo.errors import DuplicateKeyError

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.cloud_connections import MongoDBConnection
from app.conversation_indexes import initialize_conversation_indexes
from app.conversation_models import (
    MessageRecord,
    MessageRole,
    MessageStatus,
    SessionRecord,
)


def main() -> int:
    connection = MongoDBConnection()
    session = SessionRecord(title="P2-01 isolated smoke")
    request_id = str(uuid4())
    message_ids: list[str] = []
    try:
        status = connection.connect()
        if not status.ok:
            print(f"mongodb: ok=False; code={status.code}; message={status.message}")
            return 1

        database = connection.database
        initialize_conversation_indexes(database)
        database["sessions"].insert_one(session.to_mongo())

        user = MessageRecord(
            session_id=session.session_id,
            sequence=1,
            role=MessageRole.USER,
            content="P2-01 smoke question",
            status=MessageStatus.COMPLETED,
            request_id=request_id,
        )
        assistant = MessageRecord(
            session_id=session.session_id,
            sequence=2,
            role=MessageRole.ASSISTANT,
            content="P2-01 smoke answer",
            status=MessageStatus.COMPLETED,
            request_id=request_id,
        )
        message_ids.extend([user.message_id, assistant.message_id])
        database["messages"].insert_many([user.to_mongo(), assistant.to_mongo()])

        ordered = list(
            database["messages"].find(
                {"session_id": session.session_id},
                {"_id": 1, "sequence": 1, "request_id": 1},
            ).sort([("sequence", 1), ("_id", 1)])
        )
        if [item["sequence"] for item in ordered] != [1, 2]:
            raise RuntimeError("message order verification failed")
        if any(item["request_id"] != request_id for item in ordered):
            raise RuntimeError("request linkage verification failed")

        duplicate = MessageRecord(
            session_id=session.session_id,
            sequence=2,
            role=MessageRole.ASSISTANT,
            status=MessageStatus.PENDING,
            request_id=request_id,
        )
        message_ids.append(duplicate.message_id)
        try:
            database["messages"].insert_one(duplicate.to_mongo())
        except DuplicateKeyError:
            pass
        else:
            raise RuntimeError("unique session/sequence index was not enforced")

        print("PASS: session/message persistence, stable order, request linkage, unique sequence.")
        return 0
    finally:
        if connection.database is not None:
            connection.database["messages"].delete_many(
                {"_id": {"$in": message_ids}, "session_id": session.session_id}
            )
            connection.database["sessions"].delete_one({"_id": session.session_id})
            remaining = connection.database["messages"].count_documents(
                {"session_id": session.session_id}
            )
            print(f"Cleanup: {'PASS' if remaining == 0 else 'FAIL'}")
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
