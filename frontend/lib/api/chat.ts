import { SSEParser, SSEParserError, type ParsedSSEEvent } from "@/lib/sse/parser";
import type {
  ChatRequest,
  ChatUsage,
  SSECitationEvent,
  SSEDeltaEvent,
  SSEDoneEvent,
  SSEErrorEvent,
  SSEEvent,
  SSEMetadataEvent,
  SSEStartEvent,
} from "@/types/chat";

export type ChatStreamErrorStage = "before_response" | "stream";

export type ChatStreamErrorKind =
  | "http"
  | "network"
  | "aborted"
  | "invalid_response"
  | "transport"
  | "protocol"
  | "incomplete"
  | "consumer";

/** Safe client error. It never retains raw response, event payload or question text. */
export class ChatStreamClientError extends Error {
  readonly stage: ChatStreamErrorStage;
  readonly kind: ChatStreamErrorKind;
  readonly status: number | null;
  readonly code: string | null;
  readonly retryable: boolean;

  constructor(
    stage: ChatStreamErrorStage,
    kind: ChatStreamErrorKind,
    message: string,
    status: number | null = null,
    code: string | null = null,
    retryable = false
  ) {
    super(message);
    this.name = "ChatStreamClientError";
    this.stage = stage;
    this.kind = kind;
    this.status = status;
    this.code = code;
    this.retryable = retryable;
  }
}

export interface ChatStreamResult {
  /** Exact validated events in wire order; every event retains its sequence. */
  events: readonly SSEEvent[];
  /** Carries request/session/user-message/assistant-message IDs and mode. */
  start: SSEStartEvent;
  metadata: SSEMetadataEvent | null;
  citations: readonly SSECitationEvent[];
  deltas: readonly SSEDeltaEvent[];
  /** A valid SSE error is a terminal result, not a thrown transport error. */
  terminal: SSEDoneEvent | SSEErrorEvent;
  /** Exact concatenation of delta contents; deltas are not treated as tokens/words. */
  answer: string;
  usage: ChatUsage | null;
}

export interface ChatStreamRequestOptions {
  signal?: AbortSignal;
  onEvent?: (event: SSEEvent) => void | Promise<void>;
}

export interface ChatStreamClientOptions {
  /** Explicit HTTP(S) API URL; environment/CORS configuration remains separate. */
  baseUrl: string;
  fetch?: typeof globalThis.fetch;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function preResponseHttpError(status: number, payload: unknown): ChatStreamClientError {
  const messages: Record<number, string> = {
    400: "Yêu cầu chat không hợp lệ.",
    404: "Không tìm thấy phiên trò chuyện.",
    409: "Phiên trò chuyện đang có yêu cầu khác.",
    410: "Phiên trò chuyện đã bị xóa.",
    422: "Dữ liệu chat gửi lên không hợp lệ.",
    429: "Quá nhiều yêu cầu. Vui lòng thử lại sau.",
    502: "Không thể khởi tạo luồng trả lời.",
    503: "Dịch vụ chat tạm thời không khả dụng.",
  };
  const safeError = isRecord(payload) && isRecord(payload.error) ? payload.error : undefined;
  const code = typeof safeError?.code === "string" && /^[A-Z0-9_-]{1,100}$/.test(safeError.code)
    ? safeError.code
    : null;
  return new ChatStreamClientError(
    "before_response",
    "http",
    messages[status] ?? "Yêu cầu chat thất bại trước khi mở luồng.",
    status,
    code,
    safeError?.retryable === true
  );
}

function protocolError(kind: "protocol" | "incomplete", message: string) {
  return new ChatStreamClientError("stream", kind, message, 200);
}

function sourceReference(source: SSEMetadataEvent["data"]["sources"][number]) {
  if (!source.chunk_id || !source.document_id || !source.version_id) return null;
  return [
    source.chunk_id.toLowerCase(),
    source.document_id.toLowerCase(),
    source.version_id.toLowerCase(),
    source.page ?? null,
  ].join("|");
}

function citationReference(event: SSECitationEvent) {
  const citation = event.data.citation;
  return [
    citation.chunk_id.toLowerCase(),
    citation.document_id.toLowerCase(),
    citation.version_id.toLowerCase(),
    citation.page ?? null,
  ].join("|");
}

class TranscriptValidator {
  private readonly events: SSEEvent[] = [];
  private readonly citations: SSECitationEvent[] = [];
  private readonly deltas: SSEDeltaEvent[] = [];
  private readonly sourceReferences = new Set<string>();
  private readonly citationReferences = new Set<string>();
  private startEvent: SSEStartEvent | null = null;
  private metadataEvent: SSEMetadataEvent | null = null;
  private terminalEvent: SSEDoneEvent | SSEErrorEvent | null = null;

  accept(event: SSEEvent) {
    if (this.terminalEvent) {
      throw protocolError("protocol", "Luồng SSE có event sau terminal event.");
    }
    if (event.data.sequence !== this.events.length + 1) {
      throw protocolError("protocol", "SSE sequence không liên tục từ 1.");
    }
    if (this.events.length === 0 && event.event !== "start") {
      throw protocolError("protocol", "Luồng SSE phải bắt đầu bằng start.");
    }

    switch (event.event) {
      case "start":
        if (this.startEvent) throw protocolError("protocol", "Luồng SSE có nhiều start event.");
        this.startEvent = event;
        break;
      case "metadata":
        if (!this.startEvent || this.metadataEvent || this.citations.length || this.deltas.length) {
          throw protocolError("protocol", "Metadata SSE không đúng vị trí contract.");
        }
        this.metadataEvent = event;
        for (const source of event.data.sources) {
          const reference = sourceReference(source);
          if (reference) this.sourceReferences.add(reference);
        }
        break;
      case "citation": {
        if (!this.metadataEvent || this.deltas.length) {
          throw protocolError("protocol", "Citation phải đứng sau metadata và trước delta.");
        }
        const reference = citationReference(event);
        if (!this.sourceReferences.has(reference)) {
          throw protocolError("protocol", "Citation không tham chiếu metadata source thực.");
        }
        if (this.citationReferences.has(reference)) {
          throw protocolError("protocol", "Citation SSE bị trùng.");
        }
        this.citationReferences.add(reference);
        this.citations.push(event);
        break;
      }
      case "delta":
        if (!this.metadataEvent) {
          throw protocolError("protocol", "Delta phải đứng sau metadata.");
        }
        this.deltas.push(event);
        break;
      case "done":
        if (!this.metadataEvent || this.deltas.length === 0) {
          throw protocolError("protocol", "Done cần metadata và ít nhất một content delta.");
        }
        this.terminalEvent = event;
        break;
      case "error": {
        const expectedStatus = this.deltas.length > 0 ? "PARTIAL" : "FAILED";
        if (event.data.status !== expectedStatus) {
          throw protocolError("protocol", "Error status không khớp nội dung đã phát.");
        }
        this.terminalEvent = event;
        break;
      }
    }
    this.events.push(event);
  }

  finish(): ChatStreamResult {
    if (!this.startEvent || !this.terminalEvent) {
      throw protocolError("incomplete", "Luồng SSE kết thúc trước terminal event.");
    }
    return {
      events: this.events,
      start: this.startEvent,
      metadata: this.metadataEvent,
      citations: this.citations,
      deltas: this.deltas,
      terminal: this.terminalEvent,
      answer: this.deltas.map((event) => event.data.content).join(""),
      usage: this.terminalEvent.data.usage,
    };
  }
}

function knownEvent(parsed: ParsedSSEEvent): SSEEvent {
  if (!parsed.recognized) {
    throw protocolError("protocol", "Luồng SSE chứa event ngoài contract.");
  }
  return parsed.event;
}

async function safeErrorPayload(response: Response): Promise<unknown> {
  try {
    const text = await response.text();
    return text ? JSON.parse(text) : undefined;
  } catch {
    return undefined;
  }
}

/**
 * POST /chat/stream client. It emits validated logical events, independent of
 * arbitrary ReadableStream chunk boundaries, and never retries a sent request.
 */
export function createChatStreamClient({ baseUrl, fetch: fetchOverride }: ChatStreamClientOptions) {
  const base = new URL(baseUrl);
  if (!/^https?:$/.test(base.protocol) || base.username || base.password || base.search || base.hash) {
    throw new TypeError("baseUrl phải là HTTP(S) URL không chứa credentials/query/fragment.");
  }
  const basePath = base.pathname.replace(/\/+$/, "");
  const endpoint = `${base.origin}${basePath}/chat/stream`;

  return {
    async stream(
      payload: ChatRequest,
      { signal, onEvent }: ChatStreamRequestOptions = {}
    ): Promise<ChatStreamResult> {
      if (signal?.aborted) {
        throw new ChatStreamClientError("before_response", "aborted", "Yêu cầu chat đã bị hủy.");
      }

      let response: Response;
      try {
        response = await (fetchOverride ?? globalThis.fetch)(endpoint, {
          method: "POST",
          cache: "no-store",
          headers: {
            Accept: "text/event-stream",
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
          signal,
        });
      } catch {
        if (signal?.aborted) {
          throw new ChatStreamClientError("before_response", "aborted", "Yêu cầu chat đã bị hủy.");
        }
        throw new ChatStreamClientError(
          "before_response",
          "network",
          "Không thể kết nối để mở luồng chat."
        );
      }

      if (response.status !== 200) {
        throw preResponseHttpError(response.status, await safeErrorPayload(response));
      }
      const contentType = response.headers.get("Content-Type")?.toLowerCase() ?? "";
      if (!contentType.startsWith("text/event-stream")) {
        throw new ChatStreamClientError(
          "stream",
          "invalid_response",
          "Phản hồi chat không phải SSE.",
          response.status
        );
      }
      if (!response.body) {
        throw new ChatStreamClientError(
          "stream",
          "invalid_response",
          "Phản hồi SSE không có body stream.",
          response.status
        );
      }

      const reader = response.body.getReader();
      const parser = new SSEParser();
      const transcript = new TranscriptValidator();
      const consume = async (parsedEvents: ParsedSSEEvent[]) => {
        for (const parsed of parsedEvents) {
          const event = knownEvent(parsed);
          transcript.accept(event);
          if (onEvent) {
            try {
              await onEvent(event);
            } catch {
              throw new ChatStreamClientError(
                "stream",
                "consumer",
                "Consumer không xử lý được SSE event.",
                response.status
              );
            }
          }
        }
      };

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          await consume(parser.push(value));
        }
        await consume(parser.finish());
        return transcript.finish();
      } catch (error) {
        try {
          await reader.cancel();
        } catch {
          // Preserve the primary safe error.
        }
        if (error instanceof ChatStreamClientError) throw error;
        if (error instanceof SSEParserError) {
          throw protocolError("protocol", "Luồng SSE không khớp event contract.");
        }
        if (signal?.aborted) {
          throw new ChatStreamClientError("stream", "aborted", "Luồng chat đã bị hủy.", response.status);
        }
        throw new ChatStreamClientError(
          "stream",
          "transport",
          "Kết nối SSE bị gián đoạn.",
          response.status
        );
      } finally {
        reader.releaseLock();
      }
    },
  };
}
