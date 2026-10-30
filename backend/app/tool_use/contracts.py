"""Provider-independent argument, invocation and JSON result contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, ValidationError

ToolName = Literal["count_documents", "list_documents"]
ToolErrorCode = Literal[
    "TOOL_UNKNOWN", "TOOL_INVALID_ARGUMENTS", "TOOL_QUERY_FAILED",
    "TOOL_TIMEOUT", "TOOL_OUTPUT_LIMIT", "TOOL_LIMIT_EXCEEDED",
]
ALLOWED_TOOL_NAMES = frozenset({"count_documents", "list_documents"})
MAX_ARGUMENT_BYTES = 2 * 1024
MAX_RESULT_BYTES = 8 * 1024
MAX_BATCH_RESULT_BYTES = 16 * 1024


class CountDocumentsArguments(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    include_deleted: bool = Field(default=False, description="Include DELETED identities.")


class ListDocumentsArguments(CountDocumentsArguments):
    offset: int = Field(default=0, ge=0, le=(1 << 63) - 1)
    limit: int = Field(default=10, ge=1, le=20)


class ToolError(TypedDict):
    code: ToolErrorCode
    message: str
    retryable: bool


class ToolEnvelope(TypedDict):
    ok: bool
    tool: ToolName | None
    data: dict[str, Any] | None
    error: ToolError | None


ToolHandler = Callable[[dict[str, Any]], ToolEnvelope]


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: object


@dataclass(frozen=True)
class ToolCallResult:
    call_id: str | None
    envelope: ToolEnvelope


@dataclass(frozen=True)
class ToolBatchResult:
    """On failure results contain only a validation error, or an executed prefix/error.

    A successful prefix must never be presented as a completed batch. No result
    is fabricated for calls that were not executed.
    """

    ok: bool
    results: tuple[ToolCallResult, ...]


@dataclass(frozen=True)
class ToolDefinition:
    name: ToolName
    description: str
    arguments_type: type[BaseModel]

    def input_schema(self) -> dict[str, Any]:
        """Return a fresh JSON schema; no LangChain/provider binding happens here."""
        return self.arguments_type.model_json_schema()


class ToolContractError(ValueError):
    def __init__(self, code: ToolErrorCode):
        super().__init__(code)
        self.code = code


def _json(value: object) -> str:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError, RecursionError):
        raise ToolContractError("TOOL_QUERY_FAILED") from None


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate argument key")
        value[key] = item
    return value


def validate_arguments(name: str, arguments: object) -> dict[str, Any]:
    if name not in ALLOWED_TOOL_NAMES:
        raise ToolContractError("TOOL_UNKNOWN")
    try:
        if type(arguments) is str:
            if len(arguments.encode("utf-8")) > MAX_ARGUMENT_BYTES:
                raise ValueError("argument size")
            value = json.loads(arguments, object_pairs_hook=_unique_object)
        elif type(arguments) is dict:
            if len(_json(arguments).encode("utf-8")) > MAX_ARGUMENT_BYTES:
                raise ValueError("argument size")
            value = arguments
        else:
            raise ValueError("arguments must be a JSON object")
        model = CountDocumentsArguments if name == "count_documents" else ListDocumentsArguments
        return model.model_validate(value).model_dump()
    except (ToolContractError, ValidationError, TypeError, ValueError, RecursionError):
        raise ToolContractError("TOOL_INVALID_ARGUMENTS") from None


def failure_result(name: str | None, code: ToolErrorCode) -> ToolEnvelope:
    messages: dict[ToolErrorCode, str] = {
        "TOOL_UNKNOWN": "Công cụ không được hỗ trợ.",
        "TOOL_INVALID_ARGUMENTS": "Tham số công cụ không hợp lệ.",
        "TOOL_QUERY_FAILED": "Không thể truy vấn tài liệu.",
        "TOOL_TIMEOUT": "Truy vấn tài liệu hết thời gian.",
        "TOOL_OUTPUT_LIMIT": "Kết quả công cụ vượt giới hạn output.",
        "TOOL_LIMIT_EXCEEDED": "Vượt giới hạn round, số calls hoặc call ID không hợp lệ.",
    }
    return {
        "ok": False,
        "tool": name if name in ALLOWED_TOOL_NAMES else None,
        "data": None,
        "error": {"code": code, "message": messages[code], "retryable": code == "TOOL_TIMEOUT"},
    }


def serialize_result(result: ToolEnvelope) -> str:
    """Canonical compact UTF-8 JSON, bounded including the complete envelope."""
    try:
        text = _json(result)
        size = len(text.encode("utf-8"))
    except (ToolContractError, UnicodeError):
        raise ToolContractError("TOOL_QUERY_FAILED") from None
    if size > MAX_RESULT_BYTES:
        raise ToolContractError("TOOL_OUTPUT_LIMIT")
    return text


def normalize_result(name: str, result: object) -> ToolEnvelope:
    """Check injected handler output and never forward arbitrary error messages."""
    if type(result) is not dict or set(result) != {"ok", "tool", "data", "error"}:
        raise ToolContractError("TOOL_QUERY_FAILED")
    if type(result["ok"]) is not bool or result["tool"] != name:
        raise ToolContractError("TOOL_QUERY_FAILED")
    if result["ok"]:
        if type(result["data"]) is not dict or result["error"] is not None:
            raise ToolContractError("TOOL_QUERY_FAILED")
    else:
        error = result["error"]
        if result["data"] is not None or type(error) is not dict:
            raise ToolContractError("TOOL_QUERY_FAILED")
        code = error.get("code")
        if code not in (
            "TOOL_UNKNOWN", "TOOL_INVALID_ARGUMENTS", "TOOL_QUERY_FAILED",
            "TOOL_TIMEOUT", "TOOL_OUTPUT_LIMIT", "TOOL_LIMIT_EXCEEDED",
        ):
            raise ToolContractError("TOOL_QUERY_FAILED")
        result = failure_result(name, code)
    # The returned snapshot cannot be mutated by a handler after it returns.
    return json.loads(serialize_result(result))


def success_result(name: ToolName, data: dict[str, Any]) -> ToolEnvelope:
    return normalize_result(name, {"ok": True, "tool": name, "data": data, "error": None})
