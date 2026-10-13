import type { DateTimeString, PaginatedResponse, PaginationQuery } from "./api";

export type SessionScopeMode = "ALL_ACTIVE" | "SELECTED_DOCUMENTS";
export type MessageRole = "USER" | "ASSISTANT";
export type MessageStatus =
  | "PENDING"
  | "STREAMING"
  | "COMPLETED"
  | "PARTIAL"
  | "FAILED";

/** POST /sessions requires a JSON body ({} is valid), not scope/history fields. */
export interface CreateSessionRequest {
  title?: string | null;
}

export interface UpdateSessionTitleRequest {
  /** Backend trims/rejects blank values, maximum 200 characters. */
  title: string;
}

/** Read-only DTO: public APIs cannot set/change scope. */
export interface SessionScopeResponse {
  mode: SessionScopeMode;
  document_ids: string[];
}

export interface SessionResponse {
  session_id: string;
  title: string;
  scope: SessionScopeResponse;
  user_id: string | null;
  created_at: DateTimeString;
  updated_at: DateTimeString;
}

/** offset=0, limit=50 by default; limit 1..200, offset >=0. */
export type ListSessionsQuery = PaginationQuery;
export type SessionPageResponse = PaginatedResponse<SessionResponse>;

/** History citation schema uses plain strings (no UUID format in OpenAPI). */
export interface CitationResponse {
  chunk_id: string;
  document_id: string;
  version_id: string;
  file_name?: string | null;
  page?: number | null;
}

export interface UsageResponse {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

/** History has citations, but no sources or [n] -> source ordinal mapping. */
export interface MessageResponse {
  message_id: string;
  session_id: string;
  sequence: number;
  role: MessageRole;
  content: string;
  status: MessageStatus;
  citations: CitationResponse[];
  model: string | null;
  usage: UsageResponse | null;
  request_id: string;
  error_code: string | null;
  created_at: DateTimeString;
  updated_at: DateTimeString;
  completed_at: DateTimeString | null;
}

/** offset=0, limit=100 by default; limit 1..500, sequence-ordered history. */
export type ListMessagesQuery = PaginationQuery;
export type MessagePageResponse = PaginatedResponse<MessageResponse>;

/** Defaults are optional in OpenAPI; server currently serializes all fields. */
export interface DeleteSessionResponse {
  session_id: string;
  status?: string;
  deleted_messages: number;
  already_deleted: boolean;
  message_policy?: string;
  tombstone_retained?: boolean;
  deleted_at: DateTimeString;
}
