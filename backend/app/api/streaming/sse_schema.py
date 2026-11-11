"""P3-03 typed SSE contract, ordering rules and wire encoding.

This module defines the transport contract only. The streaming endpoint/provider
integration is implemented in Phase 4.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.schemas.chat_documents import (
    ChatError,
    ChatResponseMode,
    ChatUsage,
    Citation,
    Source,
)


class _EventData(BaseModel):
    sequence: int = Field(ge=1)

    model_config = ConfigDict(extra="forbid")


class SSEStartData(_EventData):
    request_id: UUID
    session_id: UUID | None
    user_message_id: UUID | None
    assistant_message_id: UUID | None
    mode: ChatResponseMode

    @model_validator(mode="after")
    def _validate_ids(self) -> "SSEStartData":
        message_ids = (self.user_message_id, self.assistant_message_id)
        if self.mode is ChatResponseMode.STATELESS:
            if self.session_id is not None or any(value is not None for value in message_ids):
                raise ValueError("stateless start không có session/message IDs")
        elif self.session_id is None or any(value is None for value in message_ids):
            raise ValueError("persistent start cần session và đủ hai message IDs")
        return self


class SSEMetadataData(_EventData):
    model: str | None = Field(min_length=1, max_length=255)
    sources: list[Source]


class SSECitationData(_EventData):
    citation: Citation


class SSEDeltaData(_EventData):
    content: str = Field(min_length=1, max_length=1_000_000)


class SSEDoneData(_EventData):
    status: Literal["COMPLETED"] = "COMPLETED"
    usage: ChatUsage | None


class SSEErrorData(_EventData):
    status: Literal["FAILED", "PARTIAL"]
    error: ChatError
    usage: ChatUsage | None


class _Event(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SSEStartEvent(_Event):
    event: Literal["start"] = "start"
    data: SSEStartData


class SSEMetadataEvent(_Event):
    event: Literal["metadata"] = "metadata"
    data: SSEMetadataData


class SSECitationEvent(_Event):
    event: Literal["citation"] = "citation"
    data: SSECitationData


class SSEDeltaEvent(_Event):
    event: Literal["delta"] = "delta"
    data: SSEDeltaData


class SSEDoneEvent(_Event):
    event: Literal["done"] = "done"
    data: SSEDoneData


class SSEErrorEvent(_Event):
    event: Literal["error"] = "error"
    data: SSEErrorData


SSEEvent = Annotated[
    SSEStartEvent
    | SSEMetadataEvent
    | SSECitationEvent
    | SSEDeltaEvent
    | SSEDoneEvent
    | SSEErrorEvent,
    Field(discriminator="event"),
]


class SSETranscript(BaseModel):
    """A complete logical reply represented as an ordered SSE event list."""

    events: list[SSEEvent] = Field(min_length=2)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_transcript(self) -> "SSETranscript":
        names = [event.event for event in self.events]
        if names[0] != "start" or names.count("start") != 1:
            raise ValueError("transcript phải bắt đầu bằng đúng một start")
        if names[-1] not in {"done", "error"}:
            raise ValueError("transcript phải kết thúc bằng done hoặc error")
        if names.count("done") + names.count("error") != 1:
            raise ValueError("transcript chỉ có một terminal event")

        sequences = [event.data.sequence for event in self.events]
        if sequences != list(range(1, len(self.events) + 1)):
            raise ValueError("event sequence phải liên tục, bắt đầu từ 1")

        metadata_positions = [index for index, name in enumerate(names) if name == "metadata"]
        if len(metadata_positions) > 1:
            raise ValueError("transcript chỉ có tối đa một metadata")
        metadata_index = metadata_positions[0] if metadata_positions else None
        content_names = {"citation", "delta", "done"}
        if any(name in content_names for name in names) and metadata_index is None:
            raise ValueError("metadata phải có trước citation/delta/done")

        first_delta = names.index("delta") if "delta" in names else None
        for index, name in enumerate(names):
            if name in {"citation", "delta"}:
                if metadata_index is None or index <= metadata_index:
                    raise ValueError("citation/delta phải đứng sau metadata")
            if name == "citation" and first_delta is not None and index > first_delta:
                raise ValueError("citation phải được phát trước delta đầu tiên")

        source_refs: set[tuple[str, str, str, int | None]] = set()
        if metadata_index is not None:
            metadata_event = self.events[metadata_index]
            for source in metadata_event.data.sources:
                try:
                    source_refs.add(
                        (
                            str(UUID(str(source.chunk_id))),
                            str(UUID(str(source.document_id))),
                            str(UUID(str(source.version_id))),
                            source.page,
                        )
                    )
                except (TypeError, ValueError):
                    continue

        seen_citations: set[tuple[str, str, str, int | None]] = set()
        for event in self.events:
            if event.event != "citation":
                continue
            citation = event.data.citation
            reference = (
                str(citation.chunk_id),
                str(citation.document_id),
                str(citation.version_id),
                citation.page,
            )
            if reference not in source_refs:
                raise ValueError("citation event phải tham chiếu metadata source thực")
            if reference in seen_citations:
                raise ValueError("citation event không được trùng")
            seen_citations.add(reference)

        has_delta = first_delta is not None
        terminal = self.events[-1]
        if terminal.event == "done":
            if not has_delta or not self.reconstructed_answer:
                raise ValueError("done cần ít nhất một content delta")
        else:
            expected = "PARTIAL" if has_delta else "FAILED"
            if terminal.data.status != expected:
                raise ValueError("error status phải khớp việc đã phát delta hay chưa")
        return self

    @property
    def reconstructed_answer(self) -> str:
        """Client reconstruction rule: concatenate delta content in sequence order."""
        return "".join(
            event.data.content for event in self.events if event.event == "delta"
        )


def encode_sse_event(event: SSEEvent) -> str:
    """Encode one typed event using the normative SSE ``event``/``data`` framing."""
    return f"event: {event.event}\ndata: {event.data.model_dump_json()}\n\n"
