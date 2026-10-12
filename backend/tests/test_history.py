"""P5-01 tests for session-scoped, whole-turn history loading."""

import unittest
from uuid import uuid4

from app.conversation_models import (
    MessageRecord,
    MessageRole,
    MessageStatus,
    SessionRecord,
    SessionScope,
    SessionScopeMode,
)
from app.conversation_repository import ConversationRepositoryError
from app.history import ConversationHistoryLoader


class FakeHistoryRepository:
    def __init__(self, session: SessionRecord, messages: list[MessageRecord]) -> None:
        self.session = session
        self.messages = messages
        self.calls: list[tuple[int, int]] = []

    def get_session(self, session_id: str) -> SessionRecord:
        if session_id != self.session.session_id:
            raise AssertionError("loader requested the wrong session")
        return self.session

    def list_messages(self, session_id: str, *, offset: int, limit: int):
        if session_id != self.session.session_id:
            raise AssertionError("loader requested messages from the wrong session")
        self.calls.append((offset, limit))
        values = sorted(self.messages, key=lambda item: (item.sequence, item.message_id))
        return values[offset : offset + limit], len(values)


def _pair(
    session_id: str,
    sequence: int,
    *,
    assistant_status: MessageStatus = MessageStatus.COMPLETED,
) -> list[MessageRecord]:
    request_id = str(uuid4())
    user = MessageRecord(
        session_id=session_id,
        sequence=sequence,
        role=MessageRole.USER,
        content=f"question-{sequence}",
        status=MessageStatus.COMPLETED,
        request_id=request_id,
    )
    assistant = MessageRecord(
        session_id=session_id,
        sequence=sequence + 1,
        role=MessageRole.ASSISTANT,
        content=("" if assistant_status is MessageStatus.FAILED else f"answer-{sequence}"),
        status=assistant_status,
        request_id=request_id,
        error_code=(
            "TEST_FAILURE"
            if assistant_status in {MessageStatus.PARTIAL, MessageStatus.FAILED}
            else None
        ),
    )
    return [user, assistant]


class ConversationHistoryLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document_id = str(uuid4())
        self.session = SessionRecord(
            scope=SessionScope(
                mode=SessionScopeMode.SELECTED_DOCUMENTS,
                document_ids=[self.document_id],
            )
        )

    def test_loads_correct_session_scope_order_and_all_pages(self):
        first = _pair(self.session.session_id, 1)
        second = _pair(self.session.session_id, 3)
        repository = FakeHistoryRepository(
            self.session, [second[1], first[0], second[0], first[1]]
        )

        loaded = ConversationHistoryLoader(repository, page_size=2).load(
            self.session.session_id
        )

        self.assertEqual(loaded.session.session_id, self.session.session_id)
        self.assertEqual(loaded.scope.document_ids, [self.document_id])
        self.assertEqual([turn.user.sequence for turn in loaded.turns], [1, 3])
        self.assertEqual([message.sequence for message in loaded.messages], [1, 2, 3, 4])
        self.assertEqual(repository.calls, [(0, 2), (2, 2)])

    def test_default_drops_whole_partial_failed_and_active_turns(self):
        complete = _pair(self.session.session_id, 1)
        partial = _pair(
            self.session.session_id, 3, assistant_status=MessageStatus.PARTIAL
        )
        failed = _pair(
            self.session.session_id, 5, assistant_status=MessageStatus.FAILED
        )
        pending = _pair(
            self.session.session_id, 7, assistant_status=MessageStatus.PENDING
        )
        streaming = _pair(
            self.session.session_id, 9, assistant_status=MessageStatus.STREAMING
        )
        repository = FakeHistoryRepository(
            self.session, complete + partial + failed + pending + streaming
        )

        loaded = ConversationHistoryLoader(repository).load(self.session.session_id)

        self.assertEqual([turn.user.sequence for turn in loaded.turns], [1])
        self.assertEqual([message.sequence for message in loaded.messages], [1, 2])

    def test_diagnostic_opt_in_includes_terminal_unsuccessful_but_not_active(self):
        partial = _pair(
            self.session.session_id, 1, assistant_status=MessageStatus.PARTIAL
        )
        failed = _pair(
            self.session.session_id, 3, assistant_status=MessageStatus.FAILED
        )
        streaming = _pair(
            self.session.session_id, 5, assistant_status=MessageStatus.STREAMING
        )
        repository = FakeHistoryRepository(self.session, partial + failed + streaming)

        loaded = ConversationHistoryLoader(repository).load(
            self.session.session_id, include_unsuccessful_assistant=True
        )

        self.assertEqual([turn.user.sequence for turn in loaded.turns], [1, 3])

    def test_orphans_cross_session_and_non_adjacent_pairs_are_never_returned(self):
        orphan_user = _pair(self.session.session_id, 1)[0]
        non_adjacent = _pair(self.session.session_id, 3)
        non_adjacent[1] = MessageRecord(
            **{**non_adjacent[1].model_dump(), "sequence": 6}
        )
        other = _pair(str(uuid4()), 7)
        repository = FakeHistoryRepository(
            self.session, [orphan_user, *non_adjacent, *other]
        )

        loaded = ConversationHistoryLoader(repository).load(self.session.session_id)

        self.assertEqual(loaded.turns, ())
        self.assertEqual(loaded.messages, ())

    def test_pagination_without_progress_fails_safely(self):
        class StalledRepository(FakeHistoryRepository):
            def list_messages(self, session_id: str, *, offset: int, limit: int):
                return [], 1

        loader = ConversationHistoryLoader(StalledRepository(self.session, []))
        with self.assertRaises(ConversationRepositoryError):
            loader.load(self.session.session_id)

    def test_page_size_must_be_positive(self):
        with self.assertRaises(ValueError):
            ConversationHistoryLoader(FakeHistoryRepository(self.session, []), page_size=0)


if __name__ == "__main__":
    unittest.main()
