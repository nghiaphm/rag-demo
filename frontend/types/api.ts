import type { ChatResponse } from "./chat";

/** Wire values remain strings; these aliases do not perform runtime validation. */
export type UUID = string;
export type DateTimeString = string;

/** Source: backend/app/main.py (OpenAPI only describes a string-valued map). */
export interface HealthResponse {
  status: "ok";
  llm_model: string;
}

/** Source: backend/app/cloud_connections.py ConnectionStatus.to_dict(). */
export interface ConnectionStatus {
  service: string;
  ok: boolean;
  code: string;
  message: string;
}

/** GET /health/dependencies returns this body with HTTP 200 or 503. */
export interface DependencyHealthResponse {
  status: "ok" | "degraded";
  dependencies: {
    mongodb: ConnectionStatus;
    qdrant: ConnectionStatus;
  };
}

/** Query values are optional, non-null; bounds/defaults are endpoint-specific. */
export interface PaginationQuery {
  offset?: number;
  limit?: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  offset: number;
  limit: number;
  total: number;
}

/** FastAPI's generated validation schema, including unconstrained input/context. */
export interface ValidationError {
  loc: (string | number)[];
  msg: string;
  type: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
}

export interface HTTPValidationError {
  detail?: ValidationError[];
}

/** Explicit HTTPException handlers currently use string detail. */
export interface HTTPErrorResponse {
  detail: string;
}

/** Known JSON bodies, not a normalized client error or an exhaustive transport type. */
export type ApiErrorResponse =
  | HTTPErrorResponse
  | HTTPValidationError
  | ChatResponse;
