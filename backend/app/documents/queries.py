"""Bounded, read-only library metadata queries, independent of chat and ingestion."""

from __future__ import annotations

import json
from typing import Literal, TypedDict

from app.documents.models import DocumentRecord
from app.documents.repository import (
    DOCUMENT_QUERY_MAX_FETCH,
    DocumentQueryParameterError,
    MongoDocumentRepository,
    RepositoryError,
    validate_document_query_parameters,
)

MAX_DOCUMENT_LIST_ITEMS = DOCUMENT_QUERY_MAX_FETCH - 1
MAX_DOCUMENT_LIST_RESULT_BYTES = 8 * 1024
# Leave room for the approved future {ok, tool, data, error} wrapper; no tool
# protocol is constructed here. Both the data and that wrapper remain <=8 KiB.
_LIST_RESULT_ENVELOPE_RESERVE_BYTES = 64


class DocumentCountResult(TypedDict):
    count: int
    unit: Literal["document"]
    scope: Literal["library"]
    include_deleted: bool


class DocumentMetadata(TypedDict):
    document_id: str
    file_name: str
    status: str
    active_version_id: str | None
    created_at: str
    updated_at: str


class DocumentListResult(TypedDict):
    items: list[DocumentMetadata]
    scope: Literal["library"]
    include_deleted: bool
    offset: int
    limit: int
    returned_count: int
    has_more: bool
    next_offset: int | None
    truncated_by_bytes: bool
    order: list[str]


class DocumentQueryOutputLimitError(RepositoryError):
    """A nonempty page cannot fit a complete item within the result byte cap."""


def _project_document(document: DocumentRecord) -> DocumentMetadata:
    return {
        "document_id": document.document_id,
        "file_name": document.file_name,
        "status": document.status.value,
        "active_version_id": document.active_version_id,
        "created_at": document.created_at.isoformat(),
        "updated_at": document.updated_at.isoformat(),
    }


class DocumentQueries:
    """Inject the existing Mongo repository; never construct clients or providers."""

    def __init__(self, repository: MongoDocumentRepository) -> None:
        self.repository = repository

    def count_documents(self, *, include_deleted: bool = False) -> DocumentCountResult:
        validate_document_query_parameters(include_deleted=include_deleted)
        count = self.repository.count_documents_for_tools(include_deleted=include_deleted)
        if type(count) is not int or count < 0:
            raise RepositoryError("Kết quả đếm document metadata không hợp lệ")
        return {
            "count": count,
            "unit": "document",
            "scope": "library",
            "include_deleted": include_deleted,
        }

    def list_documents(
        self,
        *,
        include_deleted: bool = False,
        offset: int = 0,
        limit: int = 10,
    ) -> DocumentListResult:
        validate_document_query_parameters(
            include_deleted=include_deleted, offset=offset, limit=limit
        )
        if limit > MAX_DOCUMENT_LIST_ITEMS:
            raise DocumentQueryParameterError("limit kết quả phải từ 1 đến 20")
        documents = self.repository.list_documents_for_tools(
            include_deleted=include_deleted, offset=offset, limit=limit + 1
        )
        try:
            items = [_project_document(document) for document in documents[:limit]]
        except (AttributeError, TypeError, ValueError):
            raise RepositoryError("Document metadata không hợp lệ") from None
        sentinel = len(documents) > limit
        truncated = False
        while True:
            has_more = sentinel or truncated
            result: DocumentListResult = {
                "items": items,
                "scope": "library",
                "include_deleted": include_deleted,
                "offset": offset,
                "limit": limit,
                "returned_count": len(items),
                "has_more": has_more,
                "next_offset": offset + len(items) if has_more else None,
                "truncated_by_bytes": truncated,
                "order": ["created_at:desc", "document_id:desc"],
            }
            try:
                size = len(json.dumps(
                    result, ensure_ascii=False, separators=(",", ":"), allow_nan=False
                ).encode("utf-8"))
            except (TypeError, ValueError, UnicodeError):
                raise RepositoryError("Document metadata không thể serialize an toàn") from None
            if size + _LIST_RESULT_ENVELOPE_RESERVE_BYTES <= MAX_DOCUMENT_LIST_RESULT_BYTES:
                return result
            if len(items) <= 1:
                raise DocumentQueryOutputLimitError("Document list vượt giới hạn output")
            items.pop()
            truncated = True
