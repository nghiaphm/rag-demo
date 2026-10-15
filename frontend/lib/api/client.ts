export type ApiErrorKind = "http" | "network" | "timeout" | "aborted" | "invalid_response";

/** Client error state is separate from backend DTOs; never contains raw response/input. */
export class ApiClientError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly code: string | null;
  readonly retryable: boolean;

  constructor(kind: ApiErrorKind, message: string, status: number | null = null,
    code: string | null = null, retryable = false) {
    super(message);
    this.name = "ApiClientError";
    this.kind = kind;
    this.status = status;
    this.code = code;
    this.retryable = retryable;
  }
}

export interface ApiResponse<T> {
  /** Empty 204/205 or zero-length bodies return undefined; JSON null stays null. */
  data: T | undefined;
  status: number;
  headers: Headers;
}

type RequestOptionsBase = Omit<RequestInit, "body" | "signal"> & {
  signal?: AbortSignal;
  /** Total fetch + body-read deadline; 0 disables timeout. Default 30 seconds. */
  timeoutMs?: number;
  /** Explicit alternate response codes for endpoints with typed non-2xx bodies (health only). */
  acceptedStatuses?: readonly number[];
};

export type ApiRequestOptions = RequestOptionsBase & (
  | { json?: unknown; body?: never }
  | { body?: BodyInit | null; json?: never }
);

export interface ApiClientOptions {
  /** Explicit HTTP(S) API URL; environment/CORS configuration is a separate task. */
  baseUrl: string;
  timeoutMs?: number;
  fetch?: typeof globalThis.fetch;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function httpError(status: number, payload?: unknown): ApiClientError {
  const messages: Record<number, string> = {
    400: "Yêu cầu không hợp lệ.",
    404: "Không tìm thấy dữ liệu yêu cầu.",
    409: "Dữ liệu đang có xung đột trạng thái.",
    410: "Dữ liệu đã bị xóa.",
    422: "Dữ liệu gửi lên không hợp lệ.",
    429: "Quá nhiều yêu cầu. Vui lòng thử lại sau.",
    502: "Không thể hoàn tất yêu cầu tới dịch vụ.",
    503: "Dịch vụ tạm thời không khả dụng.",
  };
  // ChatResponse FAILED exposes a safe code/retryable flag; detail, validation
  // input/ctx and arbitrary server messages are never copied into user-facing errors.
  const error = isRecord(payload) && isRecord(payload.error) ? payload.error : undefined;
  const code = typeof error?.code === "string" && /^[A-Z0-9_-]{1,100}$/.test(error.code)
    ? error.code : null;
  return new ApiClientError("http", messages[status] ?? "Yêu cầu API thất bại.",
    status, code, error?.retryable === true);
}

function validateTimeout(timeoutMs: number) {
  if (!Number.isFinite(timeoutMs) || timeoutMs < 0 || timeoutMs > 2_147_483_647) {
    throw new TypeError("timeoutMs phải nằm trong khoảng 0..2147483647.");
  }
}

/** JSON REST transport only; no retries, SSE parsing, auth or DTO runtime validation. */
export function createApiClient({ baseUrl, timeoutMs = 30_000, fetch: fetchOverride }: ApiClientOptions) {
  const base = new URL(baseUrl);
  if (!/^https?:$/.test(base.protocol) || base.username || base.password || base.search || base.hash) {
    throw new TypeError("baseUrl phải là HTTP(S) URL không chứa credentials/query/fragment.");
  }
  validateTimeout(timeoutMs);
  const basePath = base.pathname.replace(/\/+$/, "");
  const baseAddress = `${base.origin}${basePath}`;

  return {
    async request<T>(path: string, options: ApiRequestOptions = {}): Promise<ApiResponse<T>> {
      if (!path.startsWith("/") || path.startsWith("//") || path.includes("#")) {
        throw new TypeError("API path phải bắt đầu bằng một dấu / và không có fragment.");
      }
      const url = new URL(`${baseAddress}${path}`);
      if (basePath && !url.pathname.startsWith(`${basePath}/`)) {
        throw new TypeError("API path phải nằm trong baseUrl.");
      }
      const { json, body, signal, acceptedStatuses = [], timeoutMs: requestTimeout = timeoutMs, ...init } = options;
      if (acceptedStatuses.some(status => !Number.isInteger(status) || status < 400 || status > 599)) {
        throw new TypeError("acceptedStatuses phải là HTTP error status hợp lệ.");
      }
      if (json !== undefined && body !== undefined) throw new TypeError("Chỉ dùng json hoặc body.");
      validateTimeout(requestTimeout);
      const headers = new Headers(init.headers);
      if (!headers.has("Accept")) headers.set("Accept", "application/json");
      if (json !== undefined) headers.set("Content-Type", "application/json");
      // For FormData, leave Content-Type unset so fetch generates the multipart boundary.
      const requestBody = json !== undefined ? JSON.stringify(json) : body;
      const controller = new AbortController();
      const onAbort = () => controller.abort();
      signal?.addEventListener("abort", onAbort, { once: true });
      if (signal?.aborted) controller.abort();
      let timedOut = false;
      const timer = requestTimeout > 0 ? setTimeout(() => {
        if (!controller.signal.aborted) {
          timedOut = true;
          controller.abort();
        }
      }, requestTimeout) : undefined;
      let response: Response | undefined;
      try {
        if (controller.signal.aborted) throw new ApiClientError("aborted", "Yêu cầu đã bị hủy.");
        response = await (fetchOverride ?? globalThis.fetch)(url.toString(), {
          cache: "no-store", ...init, headers, body: requestBody, signal: controller.signal,
        });
        const text = response.status === 204 || response.status === 205 ? "" : await response.text();
        if (controller.signal.aborted) throw new Error("Request aborted");
        let data: unknown;
        if (text.length > 0) {
          try {
            data = JSON.parse(text);
          } catch {
            if (!response.ok && !acceptedStatuses.includes(response.status)) throw httpError(response.status);
            throw new ApiClientError("invalid_response", "API trả về dữ liệu JSON không hợp lệ.", response.status);
          }
        }
        if (!response.ok && !acceptedStatuses.includes(response.status)) throw httpError(response.status, data);
        return { data: data as T | undefined, status: response.status, headers: response.headers };
      } catch (error) {
        if (controller.signal.aborted) {
          throw new ApiClientError(timedOut ? "timeout" : "aborted",
            timedOut ? "Yêu cầu API đã hết thời gian chờ." : "Yêu cầu đã bị hủy.", response?.status ?? null);
        }
        if (error instanceof ApiClientError) throw error;
        // A body-read failure after error headers must preserve that HTTP status.
        if (response && !response.ok) throw httpError(response.status);
        throw new ApiClientError("network", "Không thể kết nối hoặc đọc phản hồi API.", response?.status ?? null);
      } finally {
        if (timer !== undefined) clearTimeout(timer);
        signal?.removeEventListener("abort", onAbort);
      }
    },
  };
}
