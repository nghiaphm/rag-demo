"""Named, idempotent index specifications cho sessions và messages."""

from collections.abc import Mapping, Sequence
from typing import Any

from pymongo import ASCENDING, DESCENDING, IndexModel

SESSIONS_COLLECTION = "sessions"
MESSAGES_COLLECTION = "messages"

SESSION_INDEXES: tuple[IndexModel, ...] = (
    IndexModel(
        [("updated_at", DESCENDING), ("_id", DESCENDING)],
        name="idx_sessions_updated_id",
    ),
    IndexModel(
        [("user_id", ASCENDING), ("updated_at", DESCENDING), ("_id", DESCENDING)],
        name="idx_sessions_user_updated_id",
        partialFilterExpression={"user_id": {"$type": "string"}},
    ),
    IndexModel(
        [("scope.mode", ASCENDING), ("updated_at", DESCENDING)],
        name="idx_sessions_scope_updated",
    ),
)

MESSAGE_INDEXES: tuple[IndexModel, ...] = (
    IndexModel(
        [("session_id", ASCENDING), ("sequence", ASCENDING)],
        name="uq_messages_session_sequence",
        unique=True,
    ),
    IndexModel(
        [("session_id", ASCENDING), ("created_at", ASCENDING), ("_id", ASCENDING)],
        name="idx_messages_session_created_id",
    ),
    IndexModel(
        [("session_id", ASCENDING), ("request_id", ASCENDING)],
        name="idx_messages_session_request",
    ),
    IndexModel(
        [("session_id", ASCENDING), ("status", ASCENDING), ("updated_at", DESCENDING)],
        name="idx_messages_session_status_updated",
    ),
)

CONVERSATION_INDEX_DEFINITIONS: Mapping[str, Sequence[IndexModel]] = {
    SESSIONS_COLLECTION: SESSION_INDEXES,
    MESSAGES_COLLECTION: MESSAGE_INDEXES,
}


def initialize_conversation_indexes(database: Any) -> dict[str, list[str]]:
    """Tạo indexes có tên cố định; gọi lại an toàn khi spec không đổi."""
    return {
        collection_name: database[collection_name].create_indexes(list(indexes))
        for collection_name, indexes in CONVERSATION_INDEX_DEFINITIONS.items()
    }
