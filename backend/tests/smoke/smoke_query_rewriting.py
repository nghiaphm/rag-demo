"""Offline deterministic P5-03 smoke for rewrite gating, grounding and metrics."""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.shared.config import settings
from app.conversations.models import MessageRecord, MessageRole, MessageStatus
from app.conversations.history import HistoryTurn
from app.chat.query_rewriting import ProviderRewrite, QueryRewriter, RewriteStatus


class Provider:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0

    async def rewrite(self, _prompt: str) -> ProviderRewrite:
        self.calls += 1
        return ProviderRewrite(
            self.content,
            usage={"input_tokens": 20, "output_tokens": 6, "total_tokens": 26},
        )


def _turn() -> HistoryTurn:
    session_id = str(uuid4())
    request_id = str(uuid4())
    return HistoryTurn(
        MessageRecord(
            session_id=session_id,
            sequence=1,
            role=MessageRole.USER,
            content="Thông tin sản phẩm Alpha",
            status=MessageStatus.COMPLETED,
            request_id=request_id,
        ),
        MessageRecord(
            session_id=session_id,
            sequence=2,
            role=MessageRole.ASSISTANT,
            content="Sản phẩm Alpha có bảo hành hai năm",
            status=MessageStatus.COMPLETED,
            request_id=request_id,
        ),
    )


async def _run() -> None:
    history = [_turn()]
    provider = Provider("Bảo hành của sản phẩm Alpha?")
    rewriter = QueryRewriter(
        provider,
        timeout_seconds=settings.rag_rewrite_timeout_seconds,
        max_chars=settings.rag_rewrite_max_chars,
        chars_per_token=settings.rag_token_chars_per_token,
    )
    independent = await rewriter.rewrite("Giá Alpha là bao nhiêu?", history)
    if independent.status is not RewriteStatus.SKIPPED_INDEPENDENT or provider.calls:
        raise RuntimeError("independent query unexpectedly called provider")
    original = "Còn bảo hành của nó?"
    rewritten = await rewriter.rewrite(original, history)
    if not rewritten.rewritten or rewritten.original_query != original:
        raise RuntimeError("dependent rewrite/original preservation failed")
    if rewritten.metrics.total_tokens != 26 or rewritten.metrics.provider_calls != 1:
        raise RuntimeError("rewrite token cost metrics failed")

    rejected = await QueryRewriter(
        Provider("Alpha bảo hành 5 năm?"),
        timeout_seconds=1,
        max_chars=200,
    ).rewrite(original, history)
    if rejected.status is not RewriteStatus.REJECTED_UNGROUNDED:
        raise RuntimeError("unsupported fact was not rejected")
    if rejected.retrieval_query != original:
        raise RuntimeError("unsafe rewrite did not fall back to original")


def main() -> int:
    asyncio.run(_run())
    print(
        "PASS: P5-03 conditional rewrite, original preservation, lexical grounding, "
        "safe fallback and token/latency metrics."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
