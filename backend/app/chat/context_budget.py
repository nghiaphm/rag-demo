"""Deterministic context budgeting for history-aware RAG.

P5-02 allocates system, history, retrieved chunks, current query and output
reserve without changing the runtime prompt yet.  Exact model tokenizers vary,
so the implementation uses LangChain's installed approximate counter with a
configurable multilingual chars-per-token factor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately

from app.conversations.history import HistoryTurn


class ContextBudgetError(ValueError):
    """The fixed prompt cannot be represented safely inside its allocation."""


@dataclass(frozen=True)
class ContextBudgetConfig:
    context_window_tokens: int
    system_max_tokens: int
    history_max_tokens: int
    chunks_max_tokens: int
    query_max_tokens: int
    output_reserve_tokens: int
    chars_per_token: float = 3.0

    def __post_init__(self) -> None:
        integer_values = (
            self.context_window_tokens,
            self.system_max_tokens,
            self.history_max_tokens,
            self.chunks_max_tokens,
            self.query_max_tokens,
            self.output_reserve_tokens,
        )
        if any(value <= 0 for value in integer_values):
            raise ValueError("Các giới hạn token phải lớn hơn 0")
        if self.chars_per_token <= 0:
            raise ValueError("chars_per_token phải lớn hơn 0")
        if self.allocated_tokens > self.context_window_tokens:
            raise ValueError("Tổng allocation vượt context window")

    @property
    def allocated_tokens(self) -> int:
        return (
            self.system_max_tokens
            + self.history_max_tokens
            + self.chunks_max_tokens
            + self.query_max_tokens
            + self.output_reserve_tokens
        )

    @classmethod
    def from_settings(cls, settings: object) -> "ContextBudgetConfig":
        return cls(
            context_window_tokens=settings.rag_context_window_tokens,
            system_max_tokens=settings.rag_system_max_tokens,
            history_max_tokens=settings.rag_history_max_tokens,
            chunks_max_tokens=settings.rag_chunks_max_tokens,
            query_max_tokens=settings.rag_query_max_tokens,
            output_reserve_tokens=settings.rag_output_reserve_tokens,
            chars_per_token=settings.rag_token_chars_per_token,
        )


@dataclass(frozen=True)
class ContextTokenUsage:
    system: int
    history: int
    chunks: int
    query: int
    output_reserve: int
    total: int


@dataclass(frozen=True)
class BudgetedContext:
    system: str
    history_turns: tuple[HistoryTurn, ...]
    chunks: tuple[str, ...]
    query: str
    usage: ContextTokenUsage
    query_truncated: bool
    chunks_truncated: bool
    omitted_history_turns: int
    omitted_chunks: int


class ApproximateTokenCounter:
    """Composable token estimate using message roles and per-message overhead."""

    def __init__(self, *, chars_per_token: float) -> None:
        self.chars_per_token = chars_per_token

    def system(self, text: str) -> int:
        return self._messages([SystemMessage(content=text)])

    def human(self, text: str) -> int:
        return self._messages([HumanMessage(content=text)])

    def turn(self, turn: HistoryTurn) -> int:
        return self._messages(
            [
                HumanMessage(content=turn.user.content),
                AIMessage(content=turn.assistant.content),
            ]
        )

    def _messages(self, messages: list[object]) -> int:
        return count_tokens_approximately(
            messages, chars_per_token=self.chars_per_token
        )


class ContextBudgetBuilder:
    """Select whole recent turns and truncate variable text deterministically."""

    QUERY_MARKER = " …[truncated]… "
    CHUNK_MARKER = "\n…[truncated]"

    def __init__(self, config: ContextBudgetConfig) -> None:
        self.config = config
        self.counter = ApproximateTokenCounter(
            chars_per_token=config.chars_per_token
        )

    def build(
        self,
        *,
        system: str,
        history_turns: Sequence[HistoryTurn],
        chunks: Sequence[str],
        query: str,
    ) -> BudgetedContext:
        if not system.strip():
            raise ContextBudgetError("System instruction không được rỗng")
        if not query.strip():
            raise ContextBudgetError("Query không được rỗng")

        system_tokens = self.counter.system(system)
        if system_tokens > self.config.system_max_tokens:
            raise ContextBudgetError(
                "System instruction vượt allocation; không được truncate safety prompt"
            )

        selected_history, history_tokens = self._select_recent_turns(history_turns)
        selected_chunks, chunk_tokens, chunks_truncated = self._select_chunks(chunks)
        budgeted_query = self._truncate_text(
            query,
            max_tokens=self.config.query_max_tokens,
            mode="head_tail",
            marker=self.QUERY_MARKER,
        )
        if not budgeted_query:
            raise ContextBudgetError("Query allocation quá nhỏ để giữ nội dung")
        query_tokens = self.counter.human(budgeted_query)
        query_truncated = budgeted_query != query
        total = (
            system_tokens
            + history_tokens
            + chunk_tokens
            + query_tokens
            + self.config.output_reserve_tokens
        )
        if total > self.config.context_window_tokens:
            raise ContextBudgetError("Context thực tế vượt context window")

        return BudgetedContext(
            system=system,
            history_turns=selected_history,
            chunks=selected_chunks,
            query=budgeted_query,
            usage=ContextTokenUsage(
                system=system_tokens,
                history=history_tokens,
                chunks=chunk_tokens,
                query=query_tokens,
                output_reserve=self.config.output_reserve_tokens,
                total=total,
            ),
            query_truncated=query_truncated,
            chunks_truncated=chunks_truncated,
            omitted_history_turns=len(history_turns) - len(selected_history),
            omitted_chunks=len(chunks) - len(selected_chunks),
        )

    def _select_recent_turns(
        self, turns: Sequence[HistoryTurn]
    ) -> tuple[tuple[HistoryTurn, ...], int]:
        selected_reversed: list[HistoryTurn] = []
        used = 0
        for turn in reversed(turns):
            turn_tokens = self.counter.turn(turn)
            if used + turn_tokens > self.config.history_max_tokens:
                break
            selected_reversed.append(turn)
            used += turn_tokens
        return tuple(reversed(selected_reversed)), used

    def _select_chunks(
        self, chunks: Sequence[str]
    ) -> tuple[tuple[str, ...], int, bool]:
        selected: list[str] = []
        used = 0
        truncated = False
        for index, chunk in enumerate(chunks):
            if not chunk.strip():
                truncated = True
                continue
            chunk_tokens = self.counter.human(chunk)
            remaining = self.config.chunks_max_tokens - used
            if chunk_tokens <= remaining:
                selected.append(chunk)
                used += chunk_tokens
                continue
            shortened = self._truncate_text(
                chunk,
                max_tokens=remaining,
                mode="prefix",
                marker=self.CHUNK_MARKER,
            )
            if shortened:
                selected.append(shortened)
                used += self.counter.human(shortened)
            truncated = True
            if index < len(chunks) - 1:
                truncated = True
            break
        if len(selected) < len(chunks):
            truncated = True
        return tuple(selected), used, truncated

    def _truncate_text(
        self,
        text: str,
        *,
        max_tokens: int,
        mode: str,
        marker: str,
    ) -> str:
        if max_tokens <= 0:
            return ""
        if self.counter.human(text) <= max_tokens:
            return text

        low, high = 0, len(text)
        best = ""
        while low <= high:
            keep = (low + high) // 2
            candidate = self._candidate(text, keep=keep, mode=mode, marker=marker)
            if candidate and self.counter.human(candidate) <= max_tokens:
                best = candidate
                low = keep + 1
            else:
                high = keep - 1
        return best

    @staticmethod
    def _candidate(text: str, *, keep: int, mode: str, marker: str) -> str:
        if keep <= 0:
            return ""
        if keep >= len(text):
            return text
        if mode == "prefix":
            return text[:keep].rstrip() + marker
        if mode != "head_tail":
            raise ValueError("Truncation mode không được hỗ trợ")
        head = (keep + 1) // 2
        tail = keep - head
        suffix = "" if tail == 0 else text[-tail:].lstrip()
        return text[:head].rstrip() + marker + suffix
