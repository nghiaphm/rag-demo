"""One-turn, one-batch executor; no model, transport or persistence ownership."""

from __future__ import annotations

import asyncio
import inspect
import math
from collections.abc import Mapping, Sequence
from time import monotonic
from types import MappingProxyType

from app.tool_use.contracts import (
    ALLOWED_TOOL_NAMES,
    MAX_BATCH_RESULT_BYTES,
    ToolBatchResult,
    ToolCall,
    ToolCallResult,
    ToolContractError,
    ToolErrorCode,
    ToolHandler,
    failure_result,
    normalize_result,
    serialize_result,
    validate_arguments,
)

MAX_TOOL_CALLS = 2
MAX_TOOL_STAGE_SECONDS = 10.0
MAX_TOOL_QUERY_SECONDS = 5.0
MAX_CALL_ID_BYTES = 128


def _call_id(call: object) -> str | None:
    if not isinstance(call, ToolCall) or type(call.call_id) is not str or not call.call_id.strip():
        return None
    try:
        return call.call_id if len(call.call_id.encode("utf-8")) <= MAX_CALL_ID_BYTES else None
    except UnicodeError:
        return None


def _failure(call: object, code: ToolErrorCode) -> ToolCallResult:
    name = call.name if isinstance(call, ToolCall) and type(call.name) is str else None
    return ToolCallResult(_call_id(call), failure_result(name, code))


class ToolExecutor:
    """Create exactly one instance per turn; every execute attempt consumes its round.

    Synchronous injected handlers run in a thread. Cancellation/timeout stops
    awaiting and scheduling further calls, not an already running Mongo read.
    Late worker results have no callback that executes tools or persists messages.
    """

    def __init__(self, registry: Mapping[str, ToolHandler]) -> None:
        snapshot = dict(registry)
        if set(snapshot) - ALLOWED_TOOL_NAMES or not all(callable(h) for h in snapshot.values()):
            raise ValueError("Registry chỉ được chứa count_documents/list_documents handlers")
        for handler in snapshot.values():
            target = getattr(handler, "__call__", handler)
            if any(check(value) for check in (inspect.iscoroutinefunction, inspect.isasyncgenfunction)
                   for value in (handler, target)):
                raise ValueError("Tool handlers phải đồng bộ")
        self._registry = MappingProxyType(snapshot)
        self._round_used = False

    async def execute(
        self, calls: Sequence[ToolCall], *, deadline: float | None = None
    ) -> ToolBatchResult:
        """Validate the complete batch before I/O; preserve order and fail fast.

        deadline is an optional server-supplied absolute monotonic turn deadline;
        it can shorten, never extend, the 10-second stage/5-second call budgets.
        Calls must be a list/tuple. A no-tool model decision skips this executor.
        """
        first = calls[0] if isinstance(calls, (list, tuple)) and calls else None
        if self._round_used:
            return ToolBatchResult(False, (_failure(first, "TOOL_LIMIT_EXCEEDED"),))
        self._round_used = True
        stage_deadline = monotonic() + MAX_TOOL_STAGE_SECONDS
        if deadline is not None:
            try:
                valid_deadline = type(deadline) in (int, float) and math.isfinite(deadline)
            except OverflowError:
                valid_deadline = False
            if not valid_deadline:
                return ToolBatchResult(False, (_failure(first, "TOOL_INVALID_ARGUMENTS"),))
            stage_deadline = min(stage_deadline, deadline)
        if not isinstance(calls, (list, tuple)):
            return ToolBatchResult(False, (_failure(None, "TOOL_INVALID_ARGUMENTS"),))
        if not 1 <= len(calls) <= MAX_TOOL_CALLS:
            return ToolBatchResult(False, (_failure(first, "TOOL_LIMIT_EXCEEDED"),))
        prepared = []
        seen = set()
        for call in calls:
            call_id = _call_id(call)
            if call_id is None or call_id in seen:
                return ToolBatchResult(False, (_failure(call, "TOOL_LIMIT_EXCEEDED"),))
            seen.add(call_id)
            if type(call.name) is not str or call.name not in self._registry:
                return ToolBatchResult(False, (_failure(call, "TOOL_UNKNOWN"),))
            try:
                arguments = validate_arguments(call.name, call.arguments)
            except ToolContractError as exc:
                return ToolBatchResult(False, (_failure(call, exc.code),))
            prepared.append((call, arguments))

        results: list[ToolCallResult] = []
        result_bytes = 0
        for call, arguments in prepared:
            call_deadline = min(stage_deadline, monotonic() + MAX_TOOL_QUERY_SECONDS)
            remaining = call_deadline - monotonic()
            if remaining <= 0:
                results.append(_failure(call, "TOOL_TIMEOUT"))
                return ToolBatchResult(False, tuple(results))
            try:
                raw = await asyncio.wait_for(
                    asyncio.to_thread(self._registry[call.name], arguments), timeout=remaining
                )
                if inspect.iscoroutine(raw):
                    raw.close()
                    raise ToolContractError("TOOL_QUERY_FAILED")
                if monotonic() >= call_deadline:
                    raise asyncio.TimeoutError
                envelope = normalize_result(call.name, raw)
                size = len(serialize_result(envelope).encode("utf-8"))
                if result_bytes + size > MAX_BATCH_RESULT_BYTES:
                    raise ToolContractError("TOOL_OUTPUT_LIMIT")
                result = ToolCallResult(call.call_id, envelope)
            except asyncio.CancelledError:
                raise
            except (asyncio.TimeoutError, TimeoutError):
                result = _failure(call, "TOOL_TIMEOUT")
            except ToolContractError as exc:
                result = _failure(call, exc.code)
            except Exception:
                result = _failure(call, "TOOL_QUERY_FAILED")
            results.append(result)
            if not result.envelope["ok"]:
                return ToolBatchResult(False, tuple(results))
            result_bytes += size
        return ToolBatchResult(True, tuple(results))
