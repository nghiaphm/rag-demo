import type { DateTimeString, PaginationQuery } from "./api";

export type DocumentStatus =
  | "UPLOADED"
  | "PROCESSING"
  | "INDEXED"
  | "FAILED"
  | "DELETED";

export interface DocumentInfo {
  document_id: string;
  file_name: string;
  status: DocumentStatus;
  active_version_id?: string | null;
  chunk_count: number;
  version_count: number;
  cleanup_pending: boolean;
  created_at: DateTimeString;
  updated_at: DateTimeString;
  deleted_at?: DateTimeString | null;
}

export interface DocumentVersionInfo {
  version_id: string;
  version: number;
  file_name: string;
  status: DocumentStatus;
  checksum_sha256: string;
  size_bytes: number;
  chunk_count: number;
  embedding_model?: string | null;
  created_at: DateTimeString;
  indexed_at?: DateTimeString | null;
}

export interface DocumentDetail extends DocumentInfo {
  versions: DocumentVersionInfo[];
}

/** offset=0, limit=100 (1..500), include_deleted=false; no status filter. */
export interface ListDocumentsQuery extends PaginationQuery {
  include_deleted?: boolean;
}

/** GET /documents returns a plain array, not an items/total envelope. */
export type DocumentListResponse = DocumentInfo[];

/** Multipart form field file for POST /documents/upload and PUT /documents/{id}. */
export interface DocumentUploadRequest {
  file: File;
}

/** Synchronous ingestion result; job_id is not a polling/progress endpoint. */
export interface DocumentIndexInfo {
  document_id: string;
  version_id: string;
  job_id: string;
  file_name: string;
  num_chunks: number;
  status?: DocumentStatus;
  activated: boolean;
}

/** HTTP 200 or 202 (cleanup pending); defaults are optional per OpenAPI. */
export interface DeleteDocumentResponse {
  document_id: string;
  status?: DocumentStatus;
  deleted_chunks: number;
  raw_file_policy?: string;
  retained_files: number;
  cleanup_pending: boolean;
  retrieval_eligible?: boolean;
}
