"""Offline deterministic smoke for the P5-02 context budget contract."""

import sys
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.shared.config import settings
from app.chat.context_budget import ContextBudgetBuilder, ContextBudgetConfig
from app.conversations.models import MessageRecord, MessageRole, MessageStatus
from app.conversations.history import HistoryTurn
from app.rag.prompt import SYSTEM_INSTRUCTION


def _turn(sequence: int, label: str) -> HistoryTurn:
    session_id = str(uuid4())
    request_id = str(uuid4())
    return HistoryTurn(
        user=MessageRecord(
            session_id=session_id,
            sequence=sequence,
            role=MessageRole.USER,
            content=f"Question {label} " + (label * 40),
            status=MessageStatus.COMPLETED,
            request_id=request_id,
        ),
        assistant=MessageRecord(
            session_id=session_id,
            sequence=sequence + 1,
            role=MessageRole.ASSISTANT,
            content=f"Answer {label} " + (label * 40),
            status=MessageStatus.COMPLETED,
            request_id=request_id,
        ),
    )


def main() -> int:
    config = ContextBudgetConfig.from_settings(settings)
    builder = ContextBudgetBuilder(config)
    turns = tuple(_turn(index * 2 + 1, str(index)) for index in range(30))
    chunks = tuple(
        f"[{index}] (smoke-{index}.md)\n" + (f"chunk-{index} " * 600)
        for index in range(1, 8)
    )
    query = "BEGIN " + ("follow-up context " * 200) + " END"
    result = builder.build(
        system=SYSTEM_INSTRUCTION,
        history_turns=turns,
        chunks=chunks,
        query=query,
    )
    if result.usage.total > config.context_window_tokens:
        raise RuntimeError("context window exceeded")
    if result.usage.history > config.history_max_tokens:
        raise RuntimeError("history allocation exceeded")
    if result.usage.chunks > config.chunks_max_tokens:
        raise RuntimeError("chunks allocation exceeded")
    if result.usage.query > config.query_max_tokens:
        raise RuntimeError("query allocation exceeded")
    if not result.history_turns or result.history_turns[-1] is not turns[-1]:
        raise RuntimeError("most recent whole turn was not retained")
    if any(
        turn.assistant.sequence != turn.user.sequence + 1
        for turn in result.history_turns
    ):
        raise RuntimeError("history turn was split")
    if not result.query_truncated or not result.chunks_truncated:
        raise RuntimeError("expected deterministic truncation did not occur")
    print(
        "PASS: P5-02 bounded system/history/chunks/query/output reserve, "
        "recent whole turns and deterministic truncation."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
