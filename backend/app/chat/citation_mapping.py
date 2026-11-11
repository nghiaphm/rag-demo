"""Server-side mapping from answer ordinals to verified retrieved candidates."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

_CITATION_ORDINAL = re.compile(r"\[(\d+)\]")


def map_verified_citations(answer: str, sources: list[dict[str, Any]]) -> list[dict]:
    """Map ``[n]`` markers to eligible server-retrieved sources.

    The answer can select only a one-based ordinal. IDs always come from ``sources``;
    UUID-like text or citation objects emitted by a model are never trusted. Invalid,
    out-of-range and duplicate references are ignored.
    """
    citations: list[dict] = []
    seen_chunk_ids: set[str] = set()
    for match in _CITATION_ORDINAL.finditer(answer):
        ordinal = int(match.group(1))
        if ordinal < 1 or ordinal > len(sources):
            continue
        citation = _eligible_citation(sources[ordinal - 1])
        if citation is None or citation["chunk_id"] in seen_chunk_ids:
            continue
        citations.append(citation)
        seen_chunk_ids.add(citation["chunk_id"])
    return citations


def _eligible_citation(source: dict[str, Any]) -> dict | None:
    try:
        chunk_id = str(UUID(str(source.get("chunk_id"))))
        document_id = str(UUID(str(source.get("document_id"))))
        version_id = str(UUID(str(source.get("version_id"))))
    except (AttributeError, TypeError, ValueError):
        return None

    page = source.get("page")
    if page is not None and (isinstance(page, bool) or not isinstance(page, int) or page < 0):
        return None
    file_name = source.get("file_name")
    if file_name is not None:
        if not isinstance(file_name, str) or not file_name.strip():
            return None
        file_name = file_name.strip()

    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "version_id": version_id,
        "file_name": file_name,
        "page": page,
    }
