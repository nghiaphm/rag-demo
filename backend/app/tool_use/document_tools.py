"""Read-only handlers delegating all document query semantics to Documents."""

from __future__ import annotations

from functools import partial

from app.document_queries import DocumentQueries, DocumentQueryOutputLimitError
from app.document_repository import (
    DocumentQueryParameterError,
    RepositoryError,
    RepositoryQueryTimeoutError,
)
from app.tool_use.contracts import (
    CountDocumentsArguments,
    ListDocumentsArguments,
    ToolContractError,
    ToolDefinition,
    ToolEnvelope,
    ToolHandler,
    ToolName,
    failure_result,
    success_result,
    validate_arguments,
)


def _query(name: ToolName, arguments: object, queries: DocumentQueries) -> ToolEnvelope:
    try:
        values = validate_arguments(name, arguments)
        if name == "count_documents":
            data = queries.count_documents(**values)
        else:
            data = queries.list_documents(**values)
        return success_result(name, data)
    except ToolContractError as exc:
        return failure_result(name, exc.code)
    except DocumentQueryOutputLimitError:
        return failure_result(name, "TOOL_OUTPUT_LIMIT")
    except RepositoryQueryTimeoutError:
        return failure_result(name, "TOOL_TIMEOUT")
    except DocumentQueryParameterError:
        return failure_result(name, "TOOL_INVALID_ARGUMENTS")
    except RepositoryError:
        return failure_result(name, "TOOL_QUERY_FAILED")
    except Exception:
        return failure_result(name, "TOOL_QUERY_FAILED")


def count_documents(arguments: object, *, queries: DocumentQueries) -> ToolEnvelope:
    return _query("count_documents", arguments, queries)


def list_documents(arguments: object, *, queries: DocumentQueries) -> ToolEnvelope:
    return _query("list_documents", arguments, queries)


def create_document_tool_registry(queries: DocumentQueries) -> dict[str, ToolHandler]:
    """Composition helper only; no global registry or client construction."""
    return {
        "count_documents": partial(count_documents, queries=queries),
        "list_documents": partial(list_documents, queries=queries),
    }


def document_tool_definitions() -> tuple[ToolDefinition, ...]:
    return (
        ToolDefinition(
            name="count_documents",
            description=(
                "Count document identities across the library, not versions or vector chunks. "
                "Exclude DELETED by default; include UPLOADED, PROCESSING, INDEXED and FAILED. "
                "This is not limited to the session retrieval scope. Read-only."
            ),
            arguments_type=CountDocumentsArguments,
        ),
        ToolDefinition(
            name="list_documents",
            description=(
                "List one library metadata page in created_at DESC, document_id DESC order. "
                "Exclude DELETED by default; return at most 20 items with returned_count, "
                "has_more and next_offset. If has_more=true, disclose that the list is incomplete; "
                "the user may request the next page in a subsequent turn. Do not auto-paginate "
                "or claim all documents were listed from an incomplete range. Read-only."
            ),
            arguments_type=ListDocumentsArguments,
        ),
    )
