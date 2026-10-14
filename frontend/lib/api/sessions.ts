import type { createApiClient } from "@/lib/api/client";
import type {
  CreateSessionRequest,
  ListMessagesQuery,
  ListSessionsQuery,
  MessagePageResponse,
  MessageResponse,
  SessionPageResponse,
  SessionResponse,
} from "@/types/sessions";

type ApiClient = ReturnType<typeof createApiClient>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isSessionId(value: unknown): value is string {
  return typeof value === "string"
    && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

function isSessionResponse(value: unknown): value is SessionResponse {
  if (!isRecord(value) || !isRecord(value.scope)) return false;
  return isSessionId(value.session_id)
    && typeof value.title === "string"
    && (value.scope.mode === "ALL_ACTIVE" || value.scope.mode === "SELECTED_DOCUMENTS")
    && Array.isArray(value.scope.document_ids)
    && value.scope.document_ids.every((id) => typeof id === "string")
    && (value.user_id === null || typeof value.user_id === "string")
    && typeof value.created_at === "string"
    && typeof value.updated_at === "string";
}

function isSessionPageResponse(value: unknown): value is SessionPageResponse {
  return isRecord(value)
    && Array.isArray(value.items)
    && value.items.every(isSessionResponse)
    && Number.isInteger(value.offset)
    && typeof value.offset === "number"
    && value.offset >= 0
    && Number.isInteger(value.limit)
    && typeof value.limit === "number"
    && value.limit >= 1
    && Number.isInteger(value.total)
    && typeof value.total === "number"
    && value.total >= 0;
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isUsageResponse(value: unknown) {
  return isRecord(value)
    && Number.isInteger(value.input_tokens)
    && typeof value.input_tokens === "number"
    && value.input_tokens >= 0
    && Number.isInteger(value.output_tokens)
    && typeof value.output_tokens === "number"
    && value.output_tokens >= 0
    && Number.isInteger(value.total_tokens)
    && typeof value.total_tokens === "number"
    && value.total_tokens >= value.input_tokens + value.output_tokens;
}

function isCitationResponse(value: unknown) {
  return isRecord(value)
    && typeof value.chunk_id === "string"
    && typeof value.document_id === "string"
    && typeof value.version_id === "string"
    && (value.file_name === undefined || isNullableString(value.file_name))
    && (value.page === undefined || value.page === null
      || (Number.isInteger(value.page) && typeof value.page === "number" && value.page >= 0));
}

function isMessageResponse(value: unknown): value is MessageResponse {
  if (!isRecord(value)) return false;
  return typeof value.message_id === "string"
    && isSessionId(value.session_id)
    && Number.isSafeInteger(value.sequence)
    && typeof value.sequence === "number"
    && value.sequence >= 1
    && (value.role === "USER" || value.role === "ASSISTANT")
    && ["PENDING", "STREAMING", "COMPLETED", "PARTIAL", "FAILED"].includes(String(value.status))
    && typeof value.content === "string"
    && Array.isArray(value.citations)
    && value.citations.every(isCitationResponse)
    && isNullableString(value.model)
    && (value.usage === null || isUsageResponse(value.usage))
    && typeof value.request_id === "string"
    && isNullableString(value.error_code)
    && typeof value.created_at === "string"
    && typeof value.updated_at === "string"
    && isNullableString(value.completed_at);
}

function isMessagePageResponse(value: unknown): value is MessagePageResponse {
  return isRecord(value)
    && Array.isArray(value.items)
    && value.items.every(isMessageResponse)
    && Number.isInteger(value.offset)
    && typeof value.offset === "number"
    && value.offset >= 0
    && Number.isInteger(value.limit)
    && typeof value.limit === "number"
    && value.limit >= 1
    && Number.isInteger(value.total)
    && typeof value.total === "number"
    && value.total >= 0;
}

/** Create only; session listing/history belongs to F4. */
export async function createSession(
  api: ApiClient,
  payload: CreateSessionRequest = {},
  signal?: AbortSignal
): Promise<SessionResponse> {
  const response = await api.request<SessionResponse>("/sessions", {
    method: "POST",
    json: payload,
    signal,
  });
  if (response.status !== 201 || !isSessionResponse(response.data)) {
    throw new TypeError("Phản hồi tạo session không khớp API contract.");
  }
  return response.data;
}

/** F4-01 requests the first backend-ordered page; later pagination belongs to F4-02. */
export async function listSessions(
  api: ApiClient,
  query: ListSessionsQuery = { offset: 0, limit: 50 },
  signal?: AbortSignal
): Promise<SessionPageResponse> {
  const offset = query.offset ?? 0;
  const limit = query.limit ?? 50;
  if (!Number.isInteger(offset) || offset < 0 || !Number.isInteger(limit) || limit < 1 || limit > 200) {
    throw new TypeError("Pagination session không hợp lệ.");
  }
  const response = await api.request<SessionPageResponse>(
    `/sessions?offset=${offset}&limit=${limit}`,
    { method: "GET", signal }
  );
  if (response.status !== 200 || !isSessionPageResponse(response.data)) {
    throw new TypeError("Phản hồi danh sách session không khớp API contract.");
  }
  return response.data;
}

export async function getSession(
  api: ApiClient,
  sessionId: string,
  signal?: AbortSignal
): Promise<SessionResponse> {
  if (!isSessionId(sessionId)) throw new TypeError("Session ID không hợp lệ.");
  const response = await api.request<SessionResponse>(`/sessions/${sessionId}`, {
    method: "GET",
    signal,
  });
  if (response.status !== 200 || !isSessionResponse(response.data)) {
    throw new TypeError("Phản hồi session không khớp API contract.");
  }
  return response.data;
}

export async function listSessionMessages(
  api: ApiClient,
  sessionId: string,
  query: ListMessagesQuery = { offset: 0, limit: 100 },
  signal?: AbortSignal
): Promise<MessagePageResponse> {
  if (!isSessionId(sessionId)) throw new TypeError("Session ID không hợp lệ.");
  const offset = query.offset ?? 0;
  const limit = query.limit ?? 100;
  if (!Number.isInteger(offset) || offset < 0 || !Number.isInteger(limit) || limit < 1 || limit > 500) {
    throw new TypeError("Pagination message không hợp lệ.");
  }
  const response = await api.request<MessagePageResponse>(
    `/sessions/${sessionId}/messages?offset=${offset}&limit=${limit}`,
    { method: "GET", signal }
  );
  if (response.status !== 200 || !isMessagePageResponse(response.data)) {
    throw new TypeError("Phản hồi message history không khớp API contract.");
  }
  if (
    response.data.offset !== offset
    || response.data.limit !== limit
    || response.data.items.length > limit
    || response.data.items.some((message) => message.session_id !== sessionId)
  ) {
    throw new TypeError("Message history không khớp session hoặc pagination đã yêu cầu.");
  }
  return response.data;
}
