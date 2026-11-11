"""Live Atlas smoke for P5-01 using an isolated session and exact cleanup."""

import sys
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.infrastructure.mongo import MongoDBConnection
from app.conversations.models import (
    MessageRecord,
    MessageRole,
    MessageStatus,
    SessionRecord,
    SessionScope,
    SessionScopeMode,
)
from app.conversations.repository import MongoConversationRepository
from app.conversations.history import ConversationHistoryLoader


def _pair(
    session_id: str, sequence: int, status: MessageStatus
) -> list[MessageRecord]:
    request_id = str(uuid4())
    return [
        MessageRecord(
            session_id=session_id,
            sequence=sequence,
            role=MessageRole.USER,
            content=f"smoke question {sequence}",
            status=MessageStatus.COMPLETED,
            request_id=request_id,
        ),
        MessageRecord(
            session_id=session_id,
            sequence=sequence + 1,
            role=MessageRole.ASSISTANT,
            content="" if status is MessageStatus.FAILED else f"smoke answer {sequence}",
            status=status,
            request_id=request_id,
            error_code=(
                "SMOKE_FAILURE"
                if status in {MessageStatus.PARTIAL, MessageStatus.FAILED}
                else None
            ),
        ),
    ]


def main() -> int:
    connection = MongoDBConnection()
    document_id = str(uuid4())
    session = SessionRecord(
        title="P5-01 isolated smoke",
        scope=SessionScope(
            mode=SessionScopeMode.SELECTED_DOCUMENTS,
            document_ids=[document_id],
        ),
    )
    message_ids: list[str] = []
    try:
        status = connection.connect()
        if not status.ok:
            print(f"mongodb: ok=False; code={status.code}; message={status.message}")
            return 1
        database = connection.database
        database["sessions"].insert_one(session.to_mongo())
        messages = (
            _pair(session.session_id, 1, MessageStatus.COMPLETED)
            + _pair(session.session_id, 3, MessageStatus.PARTIAL)
            + _pair(session.session_id, 5, MessageStatus.FAILED)
        )
        message_ids.extend(message.message_id for message in messages)
        database["messages"].insert_many(
            [message.to_mongo() for message in reversed(messages)]
        )

        loader = ConversationHistoryLoader(
            MongoConversationRepository(database), page_size=2
        )
        loaded = loader.load(session.session_id)
        if loaded.session.session_id != session.session_id:
            raise RuntimeError("session identity mismatch")
        if loaded.scope.document_ids != [document_id]:
            raise RuntimeError("session scope mismatch")
        if [message.sequence for message in loaded.messages] != [1, 2]:
            raise RuntimeError("default whole-turn filtering mismatch")

        diagnostic = loader.load(
            session.session_id, include_unsuccessful_assistant=True
        )
        if [message.sequence for message in diagnostic.messages] != [1, 2, 3, 4, 5, 6]:
            raise RuntimeError("diagnostic terminal history mismatch")

        print("PASS: P5-01 session scope, stable order, paging and whole-turn filtering.")
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
