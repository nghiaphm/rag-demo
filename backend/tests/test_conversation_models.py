"""Unit tests cho P2-01 session/message models và MongoDB indexes."""

import unittest
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.conversations.indexes import (
    CONVERSATION_INDEX_DEFINITIONS,
    MESSAGE_INDEXES,
    initialize_conversation_indexes,
)
from app.conversations.models import (
    MessageCitation,
    MessageRecord,
    MessageRole,
    MessageStatus,
    MessageUsage,
    SessionRecord,
    SessionScope,
    SessionScopeMode,
)


class ConversationModelTests(unittest.TestCase):
    def setUp(self):
        self.session_id = str(uuid4())

    def test_session_defaults_use_uuid_utc_and_all_active_scope(self):
        session = SessionRecord()
        self.assertEqual(UUID(session.session_id).version, 4)
        self.assertEqual(session.scope.mode, SessionScopeMode.ALL_ACTIVE)
        self.assertEqual(session.scope.document_ids, [])
        self.assertIsNone(session.user_id)
        self.assertEqual(session.next_message_sequence, 1)
        self.assertIsNotNone(session.created_at.utcoffset())
        self.assertEqual(session.to_mongo()["_id"], session.session_id)

    def test_selected_scope_requires_unique_uuid_document_ids(self):
        document_id = str(uuid4())
        scope = SessionScope(
            mode=SessionScopeMode.SELECTED_DOCUMENTS,
            document_ids=[document_id],
        )
        self.assertEqual(scope.document_ids, [document_id])
        with self.assertRaises(ValidationError):
            SessionScope(mode=SessionScopeMode.SELECTED_DOCUMENTS)
        with self.assertRaises(ValidationError):
            SessionScope(document_ids=[document_id])
        with self.assertRaises(ValidationError):
            SessionScope(
                mode=SessionScopeMode.SELECTED_DOCUMENTS,
                document_ids=[document_id, document_id],
            )

    def test_session_rejects_naive_datetime_and_blank_optional_user(self):
        with self.assertRaises(ValidationError):
            SessionRecord(created_at=datetime(2026, 1, 1))
        with self.assertRaises(ValidationError):
            SessionRecord(user_id="   ")

    def test_generation_guard_requires_uuid_and_utc_timestamp_together(self):
        generation_id = str(uuid4())
        guarded = SessionRecord(
            active_generation_id=generation_id,
            active_generation_started_at=datetime.now().astimezone(),
        )
        self.assertEqual(guarded.active_generation_id, generation_id)
        with self.assertRaises(ValidationError):
            SessionRecord(active_generation_id=generation_id)
        with self.assertRaises(ValidationError):
            SessionRecord(active_generation_started_at=datetime.now().astimezone())

    def test_user_message_has_stable_ids_and_completed_state(self):
        message = MessageRecord(
            session_id=self.session_id,
            sequence=1,
            role=MessageRole.USER,
            content="Câu hỏi",
            status=MessageStatus.COMPLETED,
        )
        self.assertEqual(UUID(message.message_id).version, 4)
        self.assertEqual(UUID(message.request_id).version, 4)
        self.assertEqual(message.to_mongo()["_id"], message.message_id)
        with self.assertRaises(ValidationError):
            MessageRecord(
                session_id=self.session_id,
                sequence=1,
                role=MessageRole.USER,
                content="Câu hỏi",
                status=MessageStatus.PENDING,
            )

    def test_assistant_lifecycle_and_failure_validation(self):
        pending = MessageRecord(
            session_id=self.session_id,
            sequence=2,
            role=MessageRole.ASSISTANT,
            status=MessageStatus.PENDING,
        )
        self.assertEqual(pending.content, "")
        with self.assertRaises(ValidationError):
            MessageRecord(
                session_id=self.session_id,
                sequence=2,
                role=MessageRole.ASSISTANT,
                status=MessageStatus.COMPLETED,
            )
        failed = MessageRecord(
            session_id=self.session_id,
            sequence=2,
            role=MessageRole.ASSISTANT,
            status=MessageStatus.FAILED,
            error_code="PROVIDER_ERROR",
        )
        self.assertEqual(failed.error_code, "PROVIDER_ERROR")

    def test_citation_and_usage_validation(self):
        citation = MessageCitation(
            chunk_id=str(uuid4()),
            document_id=str(uuid4()),
            version_id=str(uuid4()),
            page=0,
        )
        usage = MessageUsage(input_tokens=10, output_tokens=5, total_tokens=15)
        message = MessageRecord(
            session_id=self.session_id,
            sequence=2,
            role=MessageRole.ASSISTANT,
            content="Trả lời có căn cứ",
            status=MessageStatus.COMPLETED,
            citations=[citation],
            model="provider/model",
            usage=usage,
        )
        self.assertEqual(message.citations[0].version_id, citation.version_id)
        with self.assertRaises(ValidationError):
            MessageUsage(input_tokens=10, output_tokens=5, total_tokens=14)
        with self.assertRaises(ValidationError):
            MessageCitation(
                chunk_id="invalid",
                document_id=str(uuid4()),
                version_id=str(uuid4()),
            )

    def test_same_request_id_can_link_user_and_assistant(self):
        request_id = str(uuid4())
        user = MessageRecord(
            session_id=self.session_id,
            sequence=1,
            role=MessageRole.USER,
            content="Câu hỏi",
            status=MessageStatus.COMPLETED,
            request_id=request_id,
        )
        assistant = MessageRecord(
            session_id=self.session_id,
            sequence=2,
            role=MessageRole.ASSISTANT,
            content="Câu trả lời",
            status=MessageStatus.COMPLETED,
            request_id=request_id,
        )
        self.assertEqual(user.request_id, assistant.request_id)


class FakeCollection:
    def __init__(self):
        self.calls = []

    def create_indexes(self, indexes):
        self.calls.append(indexes)
        return [index.document["name"] for index in indexes]


class FakeDatabase:
    def __init__(self):
        self.collections = {
            name: FakeCollection() for name in CONVERSATION_INDEX_DEFINITIONS
        }

    def __getitem__(self, name):
        return self.collections[name]


class ConversationIndexTests(unittest.TestCase):
    def test_session_sequence_is_the_only_unique_application_index(self):
        unique = [
            index.document for index in MESSAGE_INDEXES if index.document.get("unique")
        ]
        self.assertEqual(len(unique), 1)
        self.assertEqual(
            list(unique[0]["key"].items()),
            [("session_id", 1), ("sequence", 1)],
        )

    def test_stable_history_index_has_id_tiebreaker(self):
        history = next(
            index.document
            for index in MESSAGE_INDEXES
            if index.document["name"] == "idx_messages_session_created_id"
        )
        self.assertEqual(
            list(history["key"].items()),
            [("session_id", 1), ("created_at", 1), ("_id", 1)],
        )

    def test_request_index_is_not_unique_for_message_pair(self):
        request = next(
            index.document
            for index in MESSAGE_INDEXES
            if index.document["name"] == "idx_messages_session_request"
        )
        self.assertFalse(request.get("unique", False))

    def test_index_initialization_is_idempotent_for_unchanged_specs(self):
        database = FakeDatabase()
        first = initialize_conversation_indexes(database)
        second = initialize_conversation_indexes(database)
        self.assertEqual(first, second)
        self.assertTrue(
            all(len(collection.calls) == 2 for collection in database.collections.values())
        )


if __name__ == "__main__":
    unittest.main()
