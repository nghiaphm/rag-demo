"""Request-local RAG/tool orchestration, deliberately not connected to HTTP yet.

Tools default off. Installed LangChain message/binding APIs are used here, but
configured Groq capability remains NOT_VERIFIED until a separately approved gate.
Logical deadlines cannot hard-stop an SDK or a synchronous database worker.
"""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Literal

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.utils import convert_to_openai_messages, count_tokens_approximately

from app.shared.config import settings
from app.shared.observability import NoOpTracer, TraceContext, Tracer
from app.chat.context_budget import ApproximateTokenCounter, ContextBudgetConfig
from app.conversations.repository import ConversationRepositoryError, MongoConversationRepository
from app.documents.queries import DocumentQueries
from app.conversations.history import ConversationHistoryLoader, HistoryTurn
from app.rag.llm import get_llm
from app.chat.events import ProviderStreamChunk
from app.chat.pipeline import (
    PreparedRagStream,
    astream_rag_answer,
    generate_prepared_answer,
    prepare_rag_request,
)
from app.tool_use.contracts import ToolCall, ToolContractError, serialize_result, validate_arguments
from app.documents.tool_handlers import create_document_tool_registry, document_tool_definitions
from app.tool_use.executor import MAX_CALL_ID_BYTES, MAX_TOOL_CALLS, ToolExecutor

from app.chat.prompts import EXCEL_SQL_AGENT_GUIDANCE, FINAL_INSTRUCTION, SELECTOR_INSTRUCTION
from app.chat.ui_context import (
    UiPageContext,
    build_selector_ui_note,
    fit_ui_system_instruction,
    format_dashboard_snapshot_context,
)
from app.chat.agent import AGENT_SYSTEM_INSTRUCTION, AgenticRunner
from app.chat.agent_tools import (
    agent_tool_schemas,
    create_agent_tool_registry,
    create_query_excel_handler,
    create_rag_search_handler,
)
from app.documents.excel.sql_service import (
    create_excel_sql_service,
    create_run_sql_handler,
    format_catalog_summary_for_prompt,
)

PROVIDER_CAPABILITY_STATUS: str = settings.provider_capability_status
MAX_SELECTOR_SECONDS: float = settings.tool_selector_timeout_seconds
MAX_TURN_SECONDS: float = settings.chat_turn_timeout_seconds
MAX_ANSWER_CHARS: int = settings.chat_max_answer_chars

Usage = dict[str, int]


class ChatOrchestrationError(Exception):
    """Safe internal error; a future transport owns status/SSE/persistence mapping."""

    def __init__(self, code: str, *, usage: Usage | None = None) -> None:
        super().__init__("Không thể hoàn tất xử lý câu hỏi.")
        self.code = code
        self.usage = usage


def _usage(value: object) -> Usage | None:
    if not isinstance(value, dict):
        return None
    input_tokens = value.get("input_tokens", value.get("prompt_tokens"))
    output_tokens = value.get("output_tokens", value.get("completion_tokens"))
    total = value.get("total_tokens")
    if any(type(number) is not int or number < 0 for number in (input_tokens, output_tokens)):
        return None
    if total is None:
        total = input_tokens + output_tokens
    if type(total) is not int or total < input_tokens + output_tokens:
        return None
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total}


def _message_usage(message: AIMessage) -> Usage | None:
    for value in (
        message.usage_metadata,
        message.response_metadata.get("token_usage"),
        message.response_metadata.get("usage"),
    ):
        normalized = _usage(value)
        if normalized is not None:
            return normalized
    return None


@dataclass
class UsageLedger:
    """One entry per invocation; missing actual usage makes the whole total unknown."""

    entries: list[tuple[str, Usage | None]] = field(default_factory=list)

    def begin(self, stage: str) -> int:
        self.entries.append((stage, None))
        return len(self.entries) - 1

    def complete(self, entry: int, usage: Usage | None) -> None:
        self.entries[entry] = (self.entries[entry][0], _usage(usage))

    @property
    def total(self) -> Usage | None:
        if not self.entries or any(usage is None for _, usage in self.entries):
            return None
        return {key: sum(usage[key] for _, usage in self.entries)
                for key in ("input_tokens", "output_tokens", "total_tokens")}


@dataclass
class PreparedChatAnswer:
    route: Literal["RAG", "DOCUMENT_TOOLS", "AGENTIC"]
    original_question: str
    sources: list[dict]
    deadline: float | None
    ledger: UsageLedger
    tools_enabled: bool
    rag: PreparedRagStream | None = None
    history_turns: tuple[HistoryTurn, ...] = ()
    selector: AIMessage | None = None
    calls: tuple[ToolCall, ...] = ()
    executor: ToolExecutor | None = field(default=None, repr=False)
    model: Any = field(default=None, repr=False)
    agent_messages: list[BaseMessage] = field(default_factory=list, repr=False)
    qdrant_client: Any = field(default=None, repr=False)
    active_version_ids: tuple[str, ...] = ()
    include_run_sql: bool = False
    session_scope: Any = field(default=None, repr=False)
    _owner: object = field(default=None, repr=False)
    _started: bool = field(default=False, repr=False)

    @property
    def usage(self) -> Usage | None:
        return self.ledger.total


def _fit_excel_sql_system_instruction(
    base_instruction: str,
    bindings: Sequence[Any],
    *,
    question: str,
    count_system_tokens: Callable[[str], int],
    max_system_tokens: int,
) -> str:
    """Gắn hướng dẫn `run_sql` + bản tóm tắt Table Catalog mà không bao giờ vượt `max_system_tokens`."""
    if not bindings:
        return base_instruction
    candidate_with_guidance = f"{base_instruction}\n\n{EXCEL_SQL_AGENT_GUIDANCE}"
    if count_system_tokens(candidate_with_guidance) <= max_system_tokens:
        prefix = candidate_with_guidance
    else:
        compact_guidance = (
            "Dùng `run_sql` (DuckDB SELECT) cho thống kê/lọc bảng Excel bên dưới; "
            "dùng `rag_search` cho văn bản tự do; không tự bịa số liệu."
        )
        candidate_compact = f"{base_instruction}\n\n{compact_guidance}"
        prefix = (
            candidate_compact
            if count_system_tokens(candidate_compact) <= max_system_tokens
            else base_instruction
        )

    catalog_summary = format_catalog_summary_for_prompt(
        bindings,
        question=question,
        count_tokens=lambda summary: count_system_tokens(f"{prefix}\n\n{summary}"),
        max_tokens=max_system_tokens,
    )
    if not catalog_summary:
        return prefix
    combined = f"{prefix}\n\n{catalog_summary}"
    if count_system_tokens(combined) <= max_system_tokens:
        return combined
    return prefix


def estimate_context_tokens(
    messages: Sequence[BaseMessage], config: ContextBudgetConfig,
    tools: list[dict] | None = None,
) -> int:
    """Public SDK counter plus a conservative serialized-protocol estimate.

    Installed count_tokens_approximately counts native tool calls/IDs/schemas.
    The wire estimate also covers calls on list-content AI messages and JSON
    escaping/field overhead; neither estimate is actual provider token usage.
    """
    schemas = tools or []
    native = count_tokens_approximately(
        messages, chars_per_token=config.chars_per_token, tools=schemas,
        use_usage_metadata_scaling=False,
    )
    wire = json.dumps(
        {"messages": convert_to_openai_messages(messages), "tools": schemas},
        ensure_ascii=True, separators=(",", ":"), allow_nan=False,
    )
    return max(native, math.ceil(len(wire) / config.chars_per_token) + 3 * len(messages))


def _history_messages(turns: Sequence[HistoryTurn]) -> list[BaseMessage]:
    return [message for turn in turns for message in (
        HumanMessage(content=turn.user.content), AIMessage(content=turn.assistant.content),
    )]


def _has_calls(message: AIMessage) -> bool:
    return bool(
        message.tool_calls or message.invalid_tool_calls
        or getattr(message, "tool_call_chunks", None)
        or message.additional_kwargs.get("tool_calls")
        or message.additional_kwargs.get("function_call")
        or message.response_metadata.get("finish_reason") in {"tool_calls", "function_call"}
        or (isinstance(message.content, list) and any(
            isinstance(block, dict) and block.get("type") in {
                "tool_call", "tool_use", "function_call", "tool_call_chunk",
            } for block in message.content
        ))
    )


def _text(message: AIMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    return "".join(block if isinstance(block, str) else block.get("text", "")
                   for block in message.content
                   if isinstance(block, str) or (isinstance(block, dict) and isinstance(block.get("text"), str)))


class _FinalModel:
    """Pass native responses through existing RAG generators, checking before text loss."""

    def __init__(self, model: Any, reserve: int) -> None:
        self.model = model
        self.reserve = reserve
        self.usage: Usage | None = None
        self.completed = False
        self._iterator: Any = None
        self._close_task: asyncio.Task | None = None

    def _accept(self, message: object) -> None:
        if not isinstance(message, AIMessage) or _has_calls(message):
            raise ChatOrchestrationError("CHAT_PROVIDER_PROTOCOL_ERROR")
        usage = _message_usage(message)
        if usage is not None:
            self.usage = usage  # Last cumulative snapshot; never sum stream snapshots.

    async def ainvoke(self, prompt: object) -> AIMessage:
        message = await self.model.ainvoke(
            prompt, tools=[], tool_choice="none", max_tokens=self.reserve,
        )
        if isinstance(message, AIMessage):
            self.usage = _message_usage(message)
            self.completed = True
        self._accept(message)
        if not _text(message).strip():
            raise ChatOrchestrationError("CHAT_EMPTY_ANSWER")
        return message

    async def astream(self, prompt: object) -> AsyncIterator[AIMessage]:
        iterator = self.model.astream(
            prompt, tools=[], tool_choice="none", max_tokens=self.reserve,
        ).__aiter__()
        self._iterator = iterator
        try:
            async for message in iterator:
                self._accept(message)
                yield message
            self.completed = True
        finally:
            await self.aclose()

    async def aclose(self) -> None:
        if self._close_task is None and self._iterator is not None:
            iterator, self._iterator = self._iterator, None
            self._close_task = asyncio.create_task(_close(iterator))
        if self._close_task is not None:
            await self._close_task  # Join the same cleanup even if async-generator GC started it.


async def _close(iterator: object) -> None:
    close = getattr(iterator, "aclose", None)
    if close is not None:
        try:
            await asyncio.wait_for(close(), timeout=2.0)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass  # Best effort only; not a hard SDK/process shutdown guarantee.


async def _wait(operation: Callable[[], Awaitable[Any]], deadline: float | None,
                limit: float | None = None) -> Any:
    started = monotonic()
    if limit is not None:
        remaining = limit if deadline is None else min(limit, max(0.0, deadline - started))
        cutoff = started + remaining
    elif deadline is not None:
        remaining = max(0.0, deadline - started)
        cutoff = deadline
    else:
        remaining = None
        cutoff = None
    if remaining is not None and remaining <= 0:
        raise ChatOrchestrationError("CHAT_TIMEOUT")
    try:
        value = await operation() if remaining is None else await asyncio.wait_for(operation(), remaining)
        if cutoff is not None and monotonic() >= cutoff:
            raise ChatOrchestrationError("CHAT_TIMEOUT")
        return value
    except asyncio.CancelledError:
        raise
    except (asyncio.TimeoutError, TimeoutError):
        raise ChatOrchestrationError("CHAT_TIMEOUT") from None


class ChatOrchestrator:
    """Inject an unbound configured model and Documents capability; no cloud clients.

    prepare_plan performs selection/RAG preparation only, never tool queries.
    A plan is consumed once by generate_json or stream_final, after a future
    transport has acquired its existing ConversationService turn if applicable.
    """

    def __init__(
        self, *, llm: Any = None, queries: DocumentQueries | None = None,
        history_loader: ConversationHistoryLoader | None = None,
        budget_config: ContextBudgetConfig | None = None,
        tools_enabled: bool = False,
        rag_prepare: Callable[..., Awaitable[PreparedRagStream]] | None = None,
        tracer: Tracer | None = None,
        agentic_mode: bool | None = None,
        max_agent_steps: int | None = None,
        rag_search_fn: Callable[[str, int], list[Any]] | None = None,
        excel_loader_fn: Callable[[str | None], tuple[str, bytes]] | None = None,
        sql_service: Any = None,
        current_user: Any = None,
        tenant_id: str | None = None,
        excel_sql_enabled: bool | None = None,
    ) -> None:
        if type(tools_enabled) is not bool:
            raise ValueError("tools_enabled phải là boolean")
        self.model = llm
        self.queries = queries
        self.history_loader = history_loader
        self.config = budget_config or ContextBudgetConfig.from_settings(settings)
        self.tools_enabled = tools_enabled
        self.rag_prepare = rag_prepare or prepare_rag_request
        self.tracer: Tracer = tracer or NoOpTracer()
        self.agentic_mode = settings.agentic_mode_enabled if agentic_mode is None else agentic_mode
        self.max_agent_steps = settings.max_agent_steps if max_agent_steps is None else max_agent_steps
        self.rag_search_fn = rag_search_fn
        self.excel_loader_fn = excel_loader_fn
        self.sql_service = sql_service
        self.current_user = current_user
        self.tenant_id = tenant_id
        self.excel_sql_enabled = (
            (False if agentic_mode is False else settings.excel_sql_enabled)
            if excel_sql_enabled is None
            else bool(excel_sql_enabled)
        )
        if self.excel_sql_enabled:
            missing_flags: list[str] = []
            if not self.agentic_mode:
                missing_flags.append("AGENTIC_MODE_ENABLED=true")
            if getattr(settings, "storage_backend", "local") != "s3":
                missing_flags.append("STORAGE_BACKEND=s3")
            if not getattr(settings, "excel_parquet_ingestion_enabled", False):
                missing_flags.append("EXCEL_PARQUET_INGESTION_ENABLED=true")
            if missing_flags:
                raise ValueError(
                    "Khi EXCEL_SQL_ENABLED=true, bắt buộc phải bật các cấu hình sau: "
                    + ", ".join(missing_flags)
                )

    def _schemas(self) -> list[dict]:
        return [{"type": "function", "function": {
            "name": definition.name, "description": definition.description,
            "parameters": definition.input_schema(),
        }} for definition in document_tool_definitions()]

    def _fit(
        self, question: str, turns: Sequence[HistoryTurn], system: str,
        tail: Sequence[BaseMessage] = (), tools: list[dict] | None = None,
    ) -> tuple[list[BaseMessage], tuple[HistoryTurn, ...]]:
        counter = ApproximateTokenCounter(chars_per_token=self.config.chars_per_token)
        if counter.human(question) > self.config.query_max_tokens or counter.system(system) > self.config.system_max_tokens:
            raise ChatOrchestrationError("CHAT_CONTEXT_LIMIT")
        selected = list(turns)
        while True:
            messages = [SystemMessage(content=system), *_history_messages(selected),
                        HumanMessage(content=question), *tail]
            history_size = sum(counter.turn(turn) for turn in selected)
            if history_size <= self.config.history_max_tokens and (
                estimate_context_tokens(messages, self.config, tools)
                + self.config.output_reserve_tokens <= self.config.context_window_tokens
            ):
                return messages, tuple(selected)
            if not selected:
                raise ChatOrchestrationError("CHAT_CONTEXT_LIMIT")
            selected.pop(0)  # Whole oldest turns only; never alter question/IDs/result JSON.

    @staticmethod
    def _calls(response: AIMessage) -> tuple[ToolCall, ...]:
        if response.invalid_tool_calls or response.additional_kwargs.get("function_call"):
            raise ChatOrchestrationError("TOOL_INVALID_ARGUMENTS")
        raw = response.additional_kwargs.get("tool_calls")
        native = response.tool_calls
        if raw is not None and (not isinstance(raw, list) or len(raw) != len(native)):
            raise ChatOrchestrationError("TOOL_INVALID_ARGUMENTS")
        if not native:
            if _has_calls(response):
                raise ChatOrchestrationError("TOOL_INVALID_ARGUMENTS")
            return ()
        if len(native) > MAX_TOOL_CALLS:
            raise ChatOrchestrationError("TOOL_LIMIT_EXCEEDED")
        calls, seen = [], set()
        for index, call in enumerate(native):
            if not isinstance(call, dict):
                raise ChatOrchestrationError("TOOL_INVALID_ARGUMENTS")
            call_id, name, arguments = call.get("id"), call.get("name"), call.get("args")
            try:
                valid_id = type(call_id) is str and bool(call_id.strip()) and len(call_id.encode("utf-8")) <= MAX_CALL_ID_BYTES
            except UnicodeError:
                valid_id = False
            if not valid_id or call_id in seen:
                raise ChatOrchestrationError("TOOL_LIMIT_EXCEEDED")
            seen.add(call_id)
            if type(name) is not str:
                raise ChatOrchestrationError("TOOL_UNKNOWN")
            if raw is not None:
                source = raw[index]
                if not isinstance(source, dict) or not isinstance(source.get("function"), dict):
                    raise ChatOrchestrationError("TOOL_INVALID_ARGUMENTS")
                if source.get("id") != call_id or source["function"].get("name") != name:
                    raise ChatOrchestrationError("TOOL_INVALID_ARGUMENTS")
                original = source["function"].get("arguments")
                if validate_arguments(name, original) != validate_arguments(name, arguments):
                    raise ChatOrchestrationError("TOOL_INVALID_ARGUMENTS")
                arguments = original  # Preserve raw JSON byte/duplicate-key validation.
            else:
                validate_arguments(name, arguments)
            calls.append(ToolCall(call_id, name, arguments))
        return tuple(calls)

    async def prepare_plan(
        self, question: str, *, database: Any = None, qdrant_client: Any = None,
        session_id: str | None = None, deadline: float | None = None,
        ui_context: UiPageContext | None = None,
    ) -> PreparedChatAnswer:
        ledger = UsageLedger()
        trace = self.tracer.trace(
            "chat_turn",
            session_id=session_id,
            input={"question": question, "tools_enabled": self.tools_enabled},
        )
        try:
            if type(question) is not str or not question.strip():
                raise ChatOrchestrationError("CHAT_INVALID_QUESTION")
            if deadline is not None and (type(deadline) not in (int, float) or not math.isfinite(deadline)):
                raise ChatOrchestrationError("CHAT_TIMEOUT")
            if self.tools_enabled:
                bound = monotonic() + min(MAX_TURN_SECONDS, settings.stream_timeout_seconds)
                deadline = bound if deadline is None else min(deadline, bound)
            turns: tuple[HistoryTurn, ...] = ()
            model = self.model if self.model is not None else get_llm()
            response, calls = None, ()
            counter = ApproximateTokenCounter(chars_per_token=self.config.chars_per_token)
            if self.tools_enabled and self.agentic_mode:
                session_scope = None
                if session_id is not None:
                    loader = self.history_loader or ConversationHistoryLoader(MongoConversationRepository(database))
                    loaded = await _wait(lambda: asyncio.to_thread(loader.load, session_id), deadline)
                    turns = loaded.turns
                    session_scope = getattr(loaded, "retrieval_scope", None)
                agent_instruction = fit_ui_system_instruction(
                    AGENT_SYSTEM_INSTRUCTION,
                    ui_context,
                    counter.system,
                    self.config.system_max_tokens,
                )
                include_run_sql = False
                if self.excel_sql_enabled:
                    if self.sql_service is None and database is not None:
                        self.sql_service = create_excel_sql_service(database)
                    if self.sql_service is not None:
                        authorized_tables = await _wait(
                            lambda: asyncio.to_thread(
                                self.sql_service.list_authorized_tables,
                                user=self.current_user,
                                tenant_id=self.tenant_id,
                                session_scope=session_scope,
                            ),
                            deadline,
                        )
                        if authorized_tables:
                            include_run_sql = True
                            agent_instruction = _fit_excel_sql_system_instruction(
                                agent_instruction,
                                authorized_tables,
                                question=question,
                                count_system_tokens=counter.system,
                                max_system_tokens=self.config.system_max_tokens,
                            )
                schemas = agent_tool_schemas(include_run_sql=include_run_sql)
                agent_messages, turns = self._fit(
                    question,
                    turns,
                    agent_instruction,
                    tools=schemas,
                )
                dashboard_block = format_dashboard_snapshot_context(ui_context)
                if dashboard_block and agent_messages and isinstance(agent_messages[-1], HumanMessage):
                    enriched_messages = [
                        *agent_messages[:-1],
                        HumanMessage(content=f"{dashboard_block}\n\nCâu hỏi của người dùng: {question}"),
                    ]
                    if (
                        estimate_context_tokens(enriched_messages, self.config, schemas)
                        + self.config.output_reserve_tokens
                        <= self.config.context_window_tokens
                    ):
                        agent_messages = enriched_messages
                return PreparedChatAnswer(
                    "AGENTIC",
                    question,
                    [],
                    deadline,
                    ledger,
                    True,
                    history_turns=turns,
                    model=model,
                    agent_messages=agent_messages,
                    qdrant_client=qdrant_client,
                    include_run_sql=include_run_sql,
                    session_scope=session_scope,
                    _owner=self,
                )
            if self.tools_enabled:
                if session_id is not None:
                    loader = self.history_loader or ConversationHistoryLoader(MongoConversationRepository(database))
                    loaded = await _wait(lambda: asyncio.to_thread(loader.load, session_id), deadline)
                    turns = loaded.turns
                schemas = self._schemas()
                selector_instruction = SELECTOR_INSTRUCTION
                if ui_context is not None:
                    candidate_selector = SELECTOR_INSTRUCTION + build_selector_ui_note(ui_context)
                    if counter.system(candidate_selector) <= self.config.system_max_tokens:
                        selector_instruction = candidate_selector
                messages, turns = self._fit(question, turns, selector_instruction, tools=schemas)
                entry = ledger.begin("selector")
                try:
                    selector = model.bind_tools(schemas, tool_choice="auto")
                    response = await _wait(lambda: selector.ainvoke(
                        messages, max_tokens=self.config.output_reserve_tokens,
                    ), deadline, MAX_SELECTOR_SECONDS)
                except (ChatOrchestrationError, asyncio.CancelledError):
                    raise
                except Exception:
                    raise ChatOrchestrationError("TOOL_PROVIDER_UNAVAILABLE") from None
                if not isinstance(response, AIMessage) or isinstance(response, AIMessageChunk):
                    raise ChatOrchestrationError("CHAT_PROVIDER_PROTOCOL_ERROR")
                ledger.complete(entry, _message_usage(response))
                calls = self._calls(response)
            if calls:
                if self.queries is None:
                    raise ChatOrchestrationError("CHAT_DEPENDENCY_UNAVAILABLE")
                return PreparedChatAnswer(
                    "DOCUMENT_TOOLS", question, [], deadline, ledger, True,
                    history_turns=turns, selector=response.model_copy(deep=True), calls=calls,
                    executor=ToolExecutor(create_document_tool_registry(self.queries)),
                    model=model, _owner=self,
                )
            if self.rag_prepare is prepare_rag_request:
                rag = await _wait(lambda: self.rag_prepare(
                    question, database=database, qdrant_client=qdrant_client, session_id=session_id,
                    trace=trace, **({"ui_context": ui_context} if ui_context is not None else {}),
                ), deadline)
            elif ui_context is not None:
                rag = await _wait(lambda: self.rag_prepare(
                    question, database=database, qdrant_client=qdrant_client, session_id=session_id,
                    ui_context=ui_context,
                ), deadline)
            else:
                rag = await _wait(lambda: self.rag_prepare(
                    question, database=database, qdrant_client=qdrant_client, session_id=session_id,
                ), deadline)
            if self.tools_enabled and rag.rewrite is not None:
                metrics = rag.rewrite.metrics
                for _ in range(metrics.provider_calls):
                    entry = ledger.begin("rewrite")
                    if metrics.provider_calls == 1 and metrics.usage_source == "provider":
                        ledger.complete(entry, {
                            "input_tokens": metrics.input_tokens, "output_tokens": metrics.output_tokens,
                            "total_tokens": metrics.total_tokens,
                        })
            return PreparedChatAnswer(
                "RAG", question, list(rag.sources), deadline, ledger, self.tools_enabled,
                rag=rag, model=model, _owner=self,
            )
        except asyncio.CancelledError:
            raise
        except ConversationRepositoryError:
            raise  # Existing typed session errors remain available to the future transport.
        except ToolContractError as exc:
            raise ChatOrchestrationError(exc.code, usage=ledger.total) from None
        except ChatOrchestrationError as exc:
            exc.usage = ledger.total
            raise
        except Exception:
            raise ChatOrchestrationError("CHAT_PREPARATION_FAILED", usage=ledger.total) from None

    def _claim(self, plan: PreparedChatAnswer) -> None:
        if plan._owner is not self or plan._started:
            raise ChatOrchestrationError("CHAT_PLAN_CONSUMED", usage=plan.usage)
        plan._started = True

    async def _tool_context(self, plan: PreparedChatAnswer) -> tuple[list[BaseMessage], str]:
        batch = await _wait(lambda: plan.executor.execute(plan.calls, deadline=plan.deadline), plan.deadline)
        if not batch.ok:
            error = next(result.envelope["error"] for result in batch.results if not result.envelope["ok"])
            raise ChatOrchestrationError(error["code"], usage=plan.usage)
        tool_messages, notices = [], []
        for call, result in zip(plan.calls, batch.results, strict=True):
            if result.call_id != call.call_id:
                raise ChatOrchestrationError("CHAT_PROVIDER_PROTOCOL_ERROR")
            tool_messages.append(ToolMessage(
                content=serialize_result(result.envelope), tool_call_id=call.call_id, name=call.name,
            ))
            if call.name == "list_documents":
                data = result.envelope["data"]
                if data["has_more"] or data["truncated_by_bytes"]:
                    notices.append(
                        f"Danh sách này chưa đầy đủ: trang từ offset {data['offset']} trả "
                        f"{data['returned_count']} tài liệu. Có thể yêu cầu trang tiếp theo ở lượt "
                        f"chat sau (next_offset={data['next_offset']})."
                    )
                elif data["offset"] > 0:
                    notices.append(
                        f"Trang từ offset {data['offset']} chỉ xác nhận hết phần còn lại, "
                        "không phải toàn bộ thư viện."
                    )
        messages, _ = self._fit(
            plan.original_question, plan.history_turns, FINAL_INSTRUCTION,
            tail=(plan.selector, *tool_messages),
        )
        return messages, "\n".join(notices) + ("\n\n" if notices else "")

    def _check_rag_context(self, plan: PreparedChatAnswer) -> None:
        if plan.tools_enabled and (
            estimate_context_tokens(plan.rag.prompt_value.to_messages(), self.config)
            + self.config.output_reserve_tokens > self.config.context_window_tokens
        ):
            raise ChatOrchestrationError("CHAT_CONTEXT_LIMIT")

    async def _execute_agentic_plan(
        self,
        plan: PreparedChatAnswer,
        *,
        trace: Any = None,
    ) -> tuple[str, list[dict]]:
        collected_sources: list[dict] = []
        rag_handler = create_rag_search_handler(
            retrieve_fn=self.rag_search_fn,
            qdrant_client=plan.qdrant_client,
            active_version_ids=plan.active_version_ids,
            collected_sources=collected_sources,
        )
        excel_handler = (
            create_query_excel_handler(excel_loader_fn=self.excel_loader_fn)
            if self.excel_loader_fn is not None
            else None
        )
        run_sql_handler = (
            create_run_sql_handler(
                self.sql_service,
                user=self.current_user,
                tenant_id=self.tenant_id,
                session_scope=plan.session_scope,
                collected_sources=collected_sources,
            )
            if (plan.include_run_sql and self.sql_service is not None)
            else None
        )
        registry = create_agent_tool_registry(
            self.queries,
            rag_search_handler=rag_handler,
            query_excel_handler=excel_handler,
            run_sql_handler=run_sql_handler,
        )
        runner = AgenticRunner(
            model=plan.model,
            schemas=agent_tool_schemas(include_run_sql=plan.include_run_sql),
            registry=registry,
            parse_calls=self._calls,
            extract_text=_text,
            extract_usage=_message_usage,
            wait_fn=_wait,
            output_reserve_tokens=self.config.output_reserve_tokens,
            max_steps=self.max_agent_steps,
        )
        answer, final_sources, _state = await runner.run(
            initial_messages=plan.agent_messages,
            collected_sources=collected_sources,
            ledger=plan.ledger,
            error_cls=ChatOrchestrationError,
            deadline=plan.deadline,
            trace=trace,
        )
        plan.sources[:] = final_sources
        return answer, final_sources

    async def generate_json(self, plan: PreparedChatAnswer) -> dict:
        self._claim(plan)
        entry = None
        adapter = _FinalModel(plan.model, self.config.output_reserve_tokens)
        trace = self.tracer.trace("llm_generation_turn", input={"route": plan.route})
        try:
            with trace.span("llm_generation", input={"route": plan.route}) as span:
                if plan.route == "AGENTIC":
                    answer, final_sources = await self._execute_agentic_plan(
                        plan,
                        trace=trace,
                    )
                    result = {"answer": answer, "sources": final_sources, "usage": plan.usage}
                elif plan.route == "DOCUMENT_TOOLS":
                    messages, notice = await self._tool_context(plan)
                    entry = plan.ledger.begin("final")
                    response = await _wait(lambda: adapter.ainvoke(messages), plan.deadline)
                    answer = _text(response)
                    if not answer.strip():
                        raise ChatOrchestrationError("CHAT_EMPTY_ANSWER")
                    plan.ledger.complete(entry, adapter.usage)
                    result = {"answer": notice + answer, "sources": [], "usage": plan.usage}
                else:
                    self._check_rag_context(plan)
                    entry = plan.ledger.begin("final")
                    result = await _wait(lambda: generate_prepared_answer(
                        plan.rag, llm=adapter if plan.tools_enabled else plan.model,
                    ), plan.deadline)
                    plan.ledger.complete(entry, adapter.usage if plan.tools_enabled else result["usage"])
                    if plan.tools_enabled:
                        result["usage"] = plan.usage
                if result.get("usage"):
                    span.record_usage(
                        prompt_tokens=result["usage"].get("input_tokens", 0) or 0,
                        completion_tokens=result["usage"].get("output_tokens", 0) or 0,
                        total_tokens=result["usage"].get("total_tokens", 0) or 0,
                    )
                span.set_output({"answer_chars": len(result["answer"]), "source_count": len(result.get("sources", []))})
            if len(result["answer"]) > MAX_ANSWER_CHARS:
                raise ChatOrchestrationError("CHAT_OUTPUT_LIMIT")
            return result
        except asyncio.CancelledError:
            raise
        except ChatOrchestrationError as exc:
            if entry is not None and adapter.completed:
                plan.ledger.complete(entry, adapter.usage)
            exc.usage = plan.usage
            raise
        except Exception:
            if entry is not None and adapter.completed:
                plan.ledger.complete(entry, adapter.usage)
            raise ChatOrchestrationError("CHAT_GENERATION_FAILED", usage=plan.usage) from None

    async def stream_final(self, plan: PreparedChatAnswer) -> AsyncIterator[ProviderStreamChunk]:
        self._claim(plan)
        iterator = None
        adapter = _FinalModel(plan.model, self.config.output_reserve_tokens)
        try:
            if plan.route == "AGENTIC":
                trace = self.tracer.trace("llm_generation_turn", input={"route": plan.route})
                with trace.span("llm_generation", input={"route": plan.route}) as span:
                    answer, final_sources = await self._execute_agentic_plan(
                        plan,
                        trace=trace,
                    )
                    if plan.usage:
                        span.record_usage(
                            prompt_tokens=plan.usage.get("input_tokens", 0) or 0,
                            completion_tokens=plan.usage.get("output_tokens", 0) or 0,
                            total_tokens=plan.usage.get("total_tokens", 0) or 0,
                        )
                    span.set_output(
                        {
                            "answer_chars": len(answer),
                            "source_count": len(final_sources),
                        }
                    )
                if not answer.strip():
                    raise ChatOrchestrationError("CHAT_EMPTY_ANSWER")
                if len(answer) > MAX_ANSWER_CHARS:
                    raise ChatOrchestrationError("CHAT_OUTPUT_LIMIT")
                yield ProviderStreamChunk(answer, None)
                if plan.tools_enabled:
                    yield ProviderStreamChunk(None, plan.usage)
                return
            if plan.route == "DOCUMENT_TOOLS":
                messages, notice = await self._tool_context(plan)
                prepared = PreparedRagStream(prompt_value=messages, sources=[])
            else:
                self._check_rag_context(plan)
                prepared, notice = plan.rag, ""
            entry = plan.ledger.begin("final")
            iterator = astream_rag_answer(
                prepared, llm=adapter if plan.tools_enabled else plan.model,
            ).__aiter__()
            meaningful, pending, size, legacy_usage = False, [], len(notice), None
            while True:
                try:
                    chunk = await _wait(iterator.__anext__, plan.deadline)
                except StopAsyncIteration:
                    break
                if not plan.tools_enabled:
                    legacy_usage = chunk.usage if chunk.usage is not None else legacy_usage
                    yield chunk  # Disabled path preserves existing RAG chunk/usage behavior.
                    meaningful = meaningful or bool(chunk.content and chunk.content.strip())
                    continue
                if chunk.content is None:
                    continue
                size += len(chunk.content)
                if size > MAX_ANSWER_CHARS:
                    raise ChatOrchestrationError("CHAT_OUTPUT_LIMIT")
                if not meaningful and notice:
                    if not chunk.content.strip():
                        pending.append(chunk.content)
                        continue
                    yield ProviderStreamChunk(notice, None)
                    if pending:
                        yield ProviderStreamChunk("".join(pending), None)
                        pending.clear()
                meaningful = meaningful or bool(chunk.content.strip())
                yield ProviderStreamChunk(chunk.content, None)
            if pending:
                yield ProviderStreamChunk("".join(pending), None)
            plan.ledger.complete(entry, adapter.usage if plan.tools_enabled else legacy_usage)
            if not meaningful:
                raise ChatOrchestrationError("CHAT_EMPTY_ANSWER")
            if plan.tools_enabled:
                yield ProviderStreamChunk(None, plan.usage)
        except asyncio.CancelledError:
            raise
        except ChatOrchestrationError as exc:
            exc.usage = plan.usage
            raise
        except Exception:
            raise ChatOrchestrationError("CHAT_GENERATION_FAILED", usage=plan.usage) from None
        finally:
            try:
                if iterator is not None:
                    await _close(iterator)
            finally:
                await adapter.aclose()
