import type { createApiClient } from "@/lib/api/client";
import type { DeleteDocumentResponse, DocumentDetail, DocumentIndexInfo, DocumentInfo, DocumentVersionInfo, ListDocumentsQuery } from "@/types/document";
import { validateUploadFile } from "@/lib/documents/upload-validation";

type ApiClient = ReturnType<typeof createApiClient>;

export async function getDocumentPreview(api: ApiClient, documentId: string, versionId: string, signal?: AbortSignal): Promise<import("@/types/document").DocumentPreviewResponse> {
  assertDocumentId(documentId);
  assertDocumentId(versionId);
  const response = await api.request<unknown>(`/documents/${documentId}/versions/${versionId}/preview`, { method: "GET", signal });
  const value = response.data;
  if (response.status !== 200 || !record(value) || value.document_id !== documentId || value.version_id !== versionId
    || typeof value.file_name !== "string" || !["text", "excel", "unsupported"].includes(String(value.kind))
    || (value.kind === "text" && typeof value.text !== "string")
    || !Array.isArray(value.sheets) || value.sheets.some(sheet => !record(sheet) || typeof sheet.name !== "string"
      || !Array.isArray(sheet.columns) || !sheet.columns.every(column => typeof column === "string")
      || !Array.isArray(sheet.rows) || sheet.rows.some(row => !Array.isArray(row) || !row.every(cell => typeof cell === "string"))
      || !count(sheet.total_rows) || typeof sheet.truncated !== "boolean") || typeof value.truncated !== "boolean") {
    throw new TypeError("Document preview không khớp API contract.");
  }
  return value as unknown as import("@/types/document").DocumentPreviewResponse;
}
const statuses = ["UPLOADED", "PROCESSING", "INDEXED", "FAILED", "DELETED"];
const record = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const count = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
const text = (value: unknown): value is string => typeof value === "string" && value.length > 0;
const date = (value: unknown): value is string => typeof value === "string" && Number.isFinite(Date.parse(value));
const optionalText = (value: unknown) => value === undefined || value === null || typeof value === "string";
const optionalDate = (value: unknown) => value === undefined || value === null || date(value);

function isDocument(value: unknown): value is DocumentInfo {
  return record(value) && text(value.document_id) && typeof value.file_name === "string"
    && statuses.includes(String(value.status)) && optionalText(value.active_version_id)
    && count(value.chunk_count) && count(value.version_count) && typeof value.cleanup_pending === "boolean"
    && date(value.created_at) && date(value.updated_at) && optionalDate(value.deleted_at);
}

function isVersion(value: unknown): value is DocumentVersionInfo {
  return record(value) && text(value.version_id) && count(value.version) && value.version >= 1
    && typeof value.file_name === "string" && statuses.includes(String(value.status))
    && typeof value.checksum_sha256 === "string" && count(value.size_bytes) && count(value.chunk_count)
    && optionalText(value.embedding_model) && date(value.created_at) && optionalDate(value.indexed_at);
}

export async function listDocuments(api: ApiClient, query: ListDocumentsQuery = {}, signal?: AbortSignal): Promise<DocumentInfo[]> {
  const offset = query.offset ?? 0;
  const limit = query.limit ?? 100;
  const includeDeleted = query.include_deleted ?? false;
  if (!count(offset) || !count(limit) || limit < 1 || limit > 500 || typeof includeDeleted !== "boolean") {
    throw new TypeError("Document pagination/filter không hợp lệ.");
  }
  const response = await api.request<unknown>(`/documents?offset=${offset}&limit=${limit}&include_deleted=${includeDeleted}`, { method: "GET", signal });
  if (response.status !== 200 || !Array.isArray(response.data) || !response.data.every(isDocument)
    || response.data.length > limit || (!includeDeleted && response.data.some(item => item.status === "DELETED"))
    || new Set(response.data.map(item => item.document_id)).size !== response.data.length) {
    throw new TypeError("Danh sách document không khớp API contract.");
  }
  return response.data;
}

export async function getDocument(api: ApiClient, documentId: string, signal?: AbortSignal): Promise<DocumentDetail> {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(documentId)) {
    throw new TypeError("Document ID không hợp lệ.");
  }
  const response = await api.request<unknown>(`/documents/${documentId}`, { method: "GET", signal });
  const value = response.data;
  if (response.status !== 200 || !isDocument(value) || value.document_id !== documentId || !record(value)
    || !Array.isArray(value.versions) || !value.versions.every(isVersion)
    || new Set(value.versions.map(version => version.version_id)).size !== value.versions.length) {
    throw new TypeError("Document detail không khớp API contract.");
  }
  return { ...value, versions: value.versions };
}

export async function uploadDocument(api: ApiClient, file: File, signal?: AbortSignal): Promise<DocumentIndexInfo> {
  return sendDocumentFile(api, "/documents/upload", "POST", file, signal);
}

function assertDocumentId(id: string) {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) throw new TypeError("Document ID không hợp lệ.");
}

function indexResult(value: unknown, status: number): DocumentIndexInfo {
  if (status !== 201 || !record(value) || !text(value.document_id) || !text(value.version_id)
    || !text(value.job_id) || typeof value.file_name !== "string" || !count(value.num_chunks)
    || typeof value.activated !== "boolean" || (value.status !== undefined && !statuses.includes(String(value.status)))) {
    throw new TypeError("Phản hồi ingestion không khớp API contract.");
  }
  return value as unknown as DocumentIndexInfo;
}

async function sendDocumentFile(api: ApiClient, path: string, method: "POST" | "PUT", file: File, signal?: AbortSignal): Promise<DocumentIndexInfo> {
  const error = validateUploadFile(file);
  if (error) throw new TypeError(error);
  const form = new FormData();
  form.append("file", file, file.name);
  // Ingestion includes parse/embed/index; the REST default 30s is too short.
  // This is a client wait deadline, not a server job cancellation guarantee.
  const response = await api.request<unknown>(path, { method, body: form, signal, timeoutMs: 300_000 });
  return indexResult(response.data, response.status);
}

export async function updateDocument(api: ApiClient, id: string, file: File, signal?: AbortSignal): Promise<DocumentIndexInfo> {
  assertDocumentId(id);
  const result = await sendDocumentFile(api, `/documents/${id}`, "PUT", file, signal);
  if (result.document_id !== id) throw new TypeError("Ingestion response sai document.");
  return result;
}

export async function reindexDocument(api: ApiClient, id: string, signal?: AbortSignal): Promise<DocumentIndexInfo> {
  assertDocumentId(id);
  const response = await api.request<unknown>(`/documents/${id}/re-index`, { method: "POST", signal, timeoutMs: 300_000 });
  const result = indexResult(response.data, response.status);
  if (result.document_id !== id) throw new TypeError("Ingestion response sai document.");
  return result;
}

export interface DocumentDeleteResult {
  httpStatus: 200 | 202;
  response: DeleteDocumentResponse;
}
export async function deleteDocument(api: ApiClient, id: string, signal?: AbortSignal): Promise<DocumentDeleteResult> {
  assertDocumentId(id);
  const result = await api.request<unknown>(`/documents/${id}`, { method: "DELETE", signal, timeoutMs: 300_000 });
  const value = result.data;
  if ((result.status !== 200 && result.status !== 202) || !record(value) || value.document_id !== id
    || !count(value.deleted_chunks) || !count(value.retained_files) || typeof value.cleanup_pending !== "boolean"
    || value.cleanup_pending !== (result.status === 202)
    || (value.status !== undefined && value.status !== "DELETED")
    || (value.raw_file_policy !== undefined && value.raw_file_policy !== "retained")
    || (value.retrieval_eligible !== undefined && value.retrieval_eligible !== false)) {
    throw new TypeError("Phản hồi soft-delete không khớp API contract.");
  }
  return { httpStatus: result.status, response: value as unknown as DeleteDocumentResponse };
}
