import type { UUID } from "./api";

export interface AttachmentReference {
  document_id: string;
  version_id: string;
}

export interface MessageAttachment extends AttachmentReference {
  file_name: string;
}

/** POST /chat and POST /chat/stream. Omitted/null session_id is stateless. */
export interface ChatRequest {
  /** Backend trims and rejects empty/whitespace-only questions. */
  question: string;
  session_id?: UUID | null;
  attachments?: AttachmentReference[];
}

export type ChatResponseMode = "STATELESS" | "PERSISTENT";
export type ChatResponseStatus = "COMPLETED" | "PARTIAL" | "FAILED";

/** Optional nullable fields follow OpenAPI; current serializers emit defaults. */
export interface Source {
  sheet_name?: string | null;
  row_index?: number | null;
  file_name?: string | null;
  source?: string | null;
  document_id?: string | null;
  version_id?: string | null;
  chunk_id?: string | null;
  chunk_index?: number | null;
  /** PDF pages are zero-based; other loaders can omit page. */
  page?: number | null;
}

export interface Citation {
  chunk_id: UUID;
  document_id: UUID;
  version_id: UUID;
  file_name?: string | null;
  /** Backend validates non-negative pages; no citation ordinal is exposed. */
  page?: number | null;
}

export interface ChatUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface ChatError {
  code: string;
  message: string;
  /** Backend default false; OpenAPI does not require this field. */
  retryable?: boolean;
}

export interface ChatResponseMetadata {
  mode: ChatResponseMode;
  model: string | null;
}

/** Every top-level field is required, including nullable fields. */
export interface ChatResponse {
  request_id: UUID;
  session_id: UUID | null;
  user_message_id: UUID | null;
  assistant_message_id: UUID | null;
  answer: string | null;
  sources: Source[];
  citations: Citation[];
  metadata: ChatResponseMetadata;
  usage: ChatUsage | null;
  status: ChatResponseStatus;
  error: ChatError | null;
}

/** SSE wire schemas come from backend/app/sse_schema.py, not OpenAPI. */
export interface SSEStartData {
  sequence: number;
  request_id: UUID;
  session_id: UUID | null;
  user_message_id: UUID | null;
  assistant_message_id: UUID | null;
  mode: ChatResponseMode;
}

export interface SSEMetadataData {
  sequence: number;
  model: string | null;
  sources: Source[];
}

export interface SSECitationData {
  sequence: number;
  citation: Citation;
}

export interface SSEDeltaData {
  sequence: number;
  content: string;
}

export interface SSEDoneData {
  sequence: number;
  /** Default in Pydantic, always included by the current wire encoder. */
  status: "COMPLETED";
  usage: ChatUsage | null;
}

export interface SSEErrorData {
  sequence: number;
  status: "FAILED" | "PARTIAL";
  error: ChatError;
  usage: ChatUsage | null;
}

/** event comes from the SSE event: line; data is the JSON data: payload. */
export interface SSEStartEvent {
  event: "start";
  data: SSEStartData;
}
export interface SSEMetadataEvent {
  event: "metadata";
  data: SSEMetadataData;
}
export interface SSECitationEvent {
  event: "citation";
  data: SSECitationData;
}
export interface SSEDeltaEvent {
  event: "delta";
  data: SSEDeltaData;
}
export interface SSEDoneEvent {
  event: "done";
  data: SSEDoneData;
}
export interface SSEErrorEvent {
  event: "error";
  data: SSEErrorData;
}

/** citation is supported by the schema but is not emitted by today's runtime. */
export type SSEEvent =
  | SSEStartEvent
  | SSEMetadataEvent
  | SSECitationEvent
  | SSEDeltaEvent
  | SSEDoneEvent
  | SSEErrorEvent;
