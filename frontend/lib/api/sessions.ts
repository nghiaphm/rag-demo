import type { createApiClient } from "@/lib/api/client";
import type { CreateSessionRequest, SessionResponse } from "@/types/sessions";

type ApiClient = ReturnType<typeof createApiClient>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isUuid(value: unknown): value is string {
  return typeof value === "string"
    && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

function isSessionResponse(value: unknown): value is SessionResponse {
  if (!isRecord(value) || !isRecord(value.scope)) return false;
  return isUuid(value.session_id)
    && typeof value.title === "string"
    && (value.scope.mode === "ALL_ACTIVE" || value.scope.mode === "SELECTED_DOCUMENTS")
    && Array.isArray(value.scope.document_ids)
    && value.scope.document_ids.every((id) => typeof id === "string")
    && (value.user_id === null || typeof value.user_id === "string")
    && typeof value.created_at === "string"
    && typeof value.updated_at === "string";
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
