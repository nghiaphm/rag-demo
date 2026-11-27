"""Stateful iterative Agent loop (Plan -> Tool Execution -> Observe -> Re-plan/Answer)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, SystemMessage, ToolMessage

from app.shared.observability import NoOpTrace, TraceContext
from app.tool_use.contracts import ToolCall, ToolHandler, serialize_result
from app.tool_use.executor import ToolExecutor


AGENT_SYSTEM_INSTRUCTION = (
    "You are a grounded enterprise RAG assistant with access to read-only tools "
    "(such as `count_documents`, `list_documents`, `rag_search`, and `run_sql` when available). "
    "Plan your steps carefully. For multi-part questions, you may call metadata tools first, "
    "run one or more `rag_search` queries with focused keywords, or use `run_sql` "
    "to filter and aggregate structured data from uploaded .xlsx spreadsheets. "
    "Always answer strictly from observed tool results and retrieved document chunks. "
    "If no supporting evidence is found, state clearly that the library does not contain the answer."
)


@dataclass
class AgentState:
    """Mutable per-turn state carried across iterative agent steps."""

    messages: list[BaseMessage]
    step_count: int = 0
    max_steps: int = 4
    collected_sources: list[dict[str, Any]] = field(default_factory=list)
    tool_history: list[dict[str, Any]] = field(default_factory=list)
    deadline: float | None = None


class AgenticRunner:
    """Executes bounded multi-step Plan -> Execute -> Observe -> Re-plan loops."""

    def __init__(
        self,
        *,
        model: Any,
        schemas: list[dict[str, Any]],
        registry: dict[str, ToolHandler],
        parse_calls: Callable[[AIMessage], tuple[ToolCall, ...]],
        extract_text: Callable[[AIMessage], str],
        extract_usage: Callable[[AIMessage], dict[str, int] | None],
        wait_fn: Callable[..., Awaitable[Any]],
        output_reserve_tokens: int = 1024,
        max_steps: int = 4,
    ) -> None:
        self._model = model
        self._schemas = schemas
        self._registry = registry
        self._parse_calls = parse_calls
        self._extract_text = extract_text
        self._extract_usage = extract_usage
        self._wait = wait_fn
        self._output_reserve_tokens = output_reserve_tokens
        self._max_steps = max(1, max_steps)

    async def run(
        self,
        *,
        initial_messages: list[BaseMessage],
        collected_sources: list[dict[str, Any]],
        ledger: Any,
        error_cls: type[Exception],
        deadline: float | None = None,
        trace: TraceContext | None = None,
        on_status: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> tuple[str, list[dict[str, Any]], AgentState]:
        active_trace = trace or NoOpTrace()
        state = AgentState(
            messages=list(initial_messages),
            step_count=0,
            max_steps=self._max_steps,
            collected_sources=collected_sources,
            deadline=deadline,
        )

        bound_model = self._model.bind_tools(self._schemas, tool_choice="auto")

        while state.step_count < state.max_steps:
            if state.deadline is not None and monotonic() >= state.deadline:
                raise error_cls("CHAT_TIMEOUT")

            state.step_count += 1
            if on_status is not None:
                await on_status("agent_plan", f"Đang lập kế hoạch bước {state.step_count}/{state.max_steps}...")

            entry = ledger.begin(f"agent_step_{state.step_count}")
            with active_trace.span(f"agent_step_{state.step_count}", input={"step": state.step_count}) as span:
                try:
                    response = await self._wait(
                        lambda: bound_model.ainvoke(
                            state.messages,
                            max_tokens=self._output_reserve_tokens,
                        ),
                        state.deadline,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if isinstance(exc, error_cls):
                        raise
                    raise error_cls("TOOL_PROVIDER_UNAVAILABLE") from None

                if not isinstance(response, AIMessage) or isinstance(response, AIMessageChunk):
                    raise error_cls("CHAT_PROVIDER_PROTOCOL_ERROR")

                ledger.complete(entry, self._extract_usage(response))
                calls = self._parse_calls(response)
                span.set_output({"tool_calls": [c.name for c in calls]})

            if not calls:
                answer = self._extract_text(response)
                if not answer.strip():
                    raise error_cls("CHAT_EMPTY_ANSWER")
                return answer, state.collected_sources, state

            state.messages.append(response.model_copy(deep=True))
            if on_status is not None:
                names = ", ".join(c.name for c in calls)
                await on_status("agent_tool", f"Đang thực thi công cụ: {names}...")

            with active_trace.span(
                f"agent_tool_exec_{state.step_count}",
                input={"tools": [c.name for c in calls]},
            ) as span:
                executor = ToolExecutor(self._registry)
                batch = await self._wait(
                    lambda: executor.execute(calls, deadline=state.deadline),
                    state.deadline,
                )
                if not batch.ok:
                    non_recoverable = [
                        r.envelope["error"]
                        for call, r in zip(calls, batch.results, strict=True)
                        if not r.envelope["ok"]
                        and not (
                            call.name == "run_sql"
                            and r.envelope.get("error", {}).get("code")
                            in {"TOOL_INVALID_ARGUMENTS", "TOOL_TIMEOUT"}
                        )
                    ]
                    if non_recoverable:
                        raise error_cls(non_recoverable[0]["code"])

                for call, result in zip(calls, batch.results, strict=True):
                    payload_json = serialize_result(result.envelope)
                    state.messages.append(
                        ToolMessage(
                            content=payload_json,
                            tool_call_id=call.call_id,
                            name=call.name,
                        )
                    )
                    state.tool_history.append(
                        {
                            "step": state.step_count,
                            "tool": call.name,
                            "arguments": call.arguments,
                            "ok": result.envelope["ok"],
                        }
                    )
                span.set_output({"executed": len(calls), "sources_total": len(state.collected_sources)})

        # Max steps reached while model kept requesting tools: force one final grounded synthesis.
        if on_status is not None:
            await on_status("agent_final", "Đang tổng hợp câu trả lời cuối cùng...")

        final_entry = ledger.begin("agent_final")
        final_model = self._model.bind_tools([], tool_choice="none")
        synthesis_messages = [
            *state.messages,
            SystemMessage(
                content="Maximum tool steps reached. Provide the final answer now using only the gathered tool outputs."
            ),
        ]
        with active_trace.span("agent_final_synthesis") as span:
            response = await self._wait(
                lambda: final_model.ainvoke(
                    synthesis_messages,
                    max_tokens=self._output_reserve_tokens,
                ),
                state.deadline,
            )
            if not isinstance(response, AIMessage) or isinstance(response, AIMessageChunk):
                raise error_cls("CHAT_PROVIDER_PROTOCOL_ERROR")
            ledger.complete(final_entry, self._extract_usage(response))
            answer = self._extract_text(response)
            if not answer.strip():
                raise error_cls("CHAT_EMPTY_ANSWER")
            span.set_output({"answer_chars": len(answer)})
            return answer, state.collected_sources, state
