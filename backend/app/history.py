"""Load durable conversation history as complete user/assistant turns.

P5-01 intentionally stops before token budgeting, prompt construction and query
rewriting.  Consumers receive the persisted session (including retrieval scope)
and stable, whole turns so later stages never need to infer pair boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.conversation_models import (
    MessageRecord,
    MessageRole,
    MessageStatus,
    SessionRecord,
    SessionScope,
)
from app.conversation_repository import ConversationRepositoryError


class HistoryRepository(Protocol):
    """Minimal persistence contract required by the history loader."""

    def get_session(self, session_id: str) -> SessionRecord: ...

    def list_messages(
        self, session_id: str, *, offset: int, limit: int
    ) -> tuple[list[MessageRecord], int]: ...


@dataclass(frozen=True)
class HistoryTurn:
    """One indivisible persisted user/assistant exchange."""

    user: MessageRecord
    assistant: MessageRecord


@dataclass(frozen=True)
class LoadedHistory:
    """Session identity/scope plus complete turns in ascending sequence order."""

    session: SessionRecord
    turns: tuple[HistoryTurn, ...]

    @property
    def scope(self) -> SessionScope:
        return self.session.scope

    @property
    def messages(self) -> tuple[MessageRecord, ...]:
        return tuple(message for turn in self.turns for message in (turn.user, turn.assistant))


class ConversationHistoryLoader:
    """Read all persisted messages and keep only valid, complete turn pairs."""

    def __init__(self, repository: HistoryRepository, *, page_size: int = 100) -> None:
        if page_size < 1:
            raise ValueError("page_size phải lớn hơn 0")
        self.repository = repository
        self.page_size = page_size

    def load(
        self,
        session_id: str,
        *,
        include_unsuccessful_assistant: bool = False,
    ) -> LoadedHistory:
        """Load one session without returning orphaned or active message halves.

        By default an assistant must be ``COMPLETED``.  An explicit diagnostic
        caller may include terminal ``PARTIAL``/``FAILED`` turns, but active
        ``PENDING``/``STREAMING`` messages are never history.
        """

        session = self.repository.get_session(session_id)
        messages = self._load_all_messages(session.session_id)
        turns = self._complete_turns(
            messages,
            session_id=session.session_id,
            include_unsuccessful_assistant=include_unsuccessful_assistant,
        )
        return LoadedHistory(session=session, turns=tuple(turns))

    def _load_all_messages(self, session_id: str) -> list[MessageRecord]:
        offset = 0
        values: list[MessageRecord] = []
        while True:
            page, total = self.repository.list_messages(
                session_id, offset=offset, limit=self.page_size
            )
            values.extend(page)
            offset += len(page)
            if offset >= total:
                break
            if not page:
                raise ConversationRepositoryError(
                    "Không thể tải đầy đủ message history"
                )
        return values

    @staticmethod
    def _complete_turns(
        messages: list[MessageRecord],
        *,
        session_id: str,
        include_unsuccessful_assistant: bool,
    ) -> list[HistoryTurn]:
        grouped: dict[str, list[MessageRecord]] = {}
        for message in messages:
            if message.session_id != session_id:
                continue
            grouped.setdefault(message.request_id, []).append(message)

        allowed_assistant_statuses = {MessageStatus.COMPLETED}
        if include_unsuccessful_assistant:
            allowed_assistant_statuses.update(
                {MessageStatus.PARTIAL, MessageStatus.FAILED}
            )

        turns: list[HistoryTurn] = []
        for pair in grouped.values():
            if len(pair) != 2:
                continue
            first, second = sorted(pair, key=lambda item: (item.sequence, item.message_id))
            if (
                first.role is not MessageRole.USER
                or first.status is not MessageStatus.COMPLETED
                or second.role is not MessageRole.ASSISTANT
                or second.status not in allowed_assistant_statuses
                or second.sequence != first.sequence + 1
            ):
                continue
            turns.append(HistoryTurn(user=first, assistant=second))
        turns.sort(key=lambda turn: (turn.user.sequence, turn.user.message_id))
        return turns
