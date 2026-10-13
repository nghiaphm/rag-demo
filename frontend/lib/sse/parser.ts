import type {
  ChatError,
  ChatUsage,
  Citation,
  Source,
  SSEDeltaEvent,
  SSEDoneEvent,
  SSEErrorEvent,
  SSEEvent,
  SSECitationEvent,
  SSEMetadataEvent,
  SSEStartEvent,
} from "@/types/chat";

const KNOWN_EVENTS = new Set(["start", "metadata", "citation", "delta", "done", "error"]);

export type SSEParserErrorKind =
  | "invalid_utf8"
  | "invalid_json"
  | "invalid_contract"
  | "closed";

export class SSEParserError extends Error {
  readonly kind: SSEParserErrorKind;
  readonly event: string | null;

  constructor(kind: SSEParserErrorKind, message: string, event: string | null = null) {
    super(message);
    this.name = "SSEParserError";
    this.kind = kind;
    this.event = event;
  }
}

export type ParsedKnownSSEEvent = {
  recognized: true;
  event: SSEEvent;
};

export type ParsedUnknownSSEEvent = {
  recognized: false;
  /** Event name from the wire; `message` is the SSE default when omitted. */
  event: string;
  data: unknown;
};

export type ParsedSSEEvent = ParsedKnownSSEEvent | ParsedUnknownSSEEvent;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]) {
  const actual = Object.keys(value);
  return actual.length === keys.length && keys.every((key) => Object.hasOwn(value, key));
}

function isInteger(value: unknown, minimum = Number.MIN_SAFE_INTEGER): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= minimum;
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isUuid(value: unknown): value is string {
  return typeof value === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}

function isNullableUuid(value: unknown): value is string | null {
  return value === null || isUuid(value);
}

function hasSequence(value: Record<string, unknown>): value is Record<string, unknown> & { sequence: number } {
  return isInteger(value.sequence, 1);
}

function isSource(value: unknown): value is Source {
  if (!isRecord(value)) return false;
  const nullableStrings = ["file_name", "source", "document_id", "version_id", "chunk_id"];
  if (!nullableStrings.every((key) => !Object.hasOwn(value, key) || isNullableString(value[key]))) return false;
  return (!Object.hasOwn(value, "chunk_index") || value.chunk_index === null || isInteger(value.chunk_index)) &&
    (!Object.hasOwn(value, "page") || value.page === null || isInteger(value.page));
}

function isCitation(value: unknown): value is Citation {
  if (!isRecord(value) || !isUuid(value.chunk_id) || !isUuid(value.document_id) || !isUuid(value.version_id)) return false;
  return (!Object.hasOwn(value, "file_name") || isNullableString(value.file_name)) &&
    (!Object.hasOwn(value, "page") || value.page === null || isInteger(value.page, 0));
}

function isUsage(value: unknown): value is ChatUsage {
  if (!isRecord(value) || !hasExactKeys(value, ["input_tokens", "output_tokens", "total_tokens"])) return false;
  return isInteger(value.input_tokens, 0) && isInteger(value.output_tokens, 0) && isInteger(value.total_tokens, 0) &&
    value.total_tokens >= value.input_tokens + value.output_tokens;
}

function isNullableUsage(value: unknown): value is ChatUsage | null {
  return value === null || isUsage(value);
}

function isChatError(value: unknown): value is ChatError {
  if (!isRecord(value)) return false;
  const keys = Object.keys(value);
  if (!keys.every((key) => ["code", "message", "retryable"].includes(key))) return false;
  return typeof value.code === "string" && value.code.length >= 1 && value.code.length <= 100 &&
    typeof value.message === "string" && value.message.length >= 1 && value.message.length <= 500 &&
    (!Object.hasOwn(value, "retryable") || typeof value.retryable === "boolean");
}

function parseKnownEvent(event: string, data: unknown): SSEEvent | null {
  if (!isRecord(data) || !hasSequence(data)) return null;
  switch (event) {
    case "start": {
      if (!hasExactKeys(data, ["sequence", "request_id", "session_id", "user_message_id", "assistant_message_id", "mode"]) ||
          !isUuid(data.request_id) || !isNullableUuid(data.session_id) || !isNullableUuid(data.user_message_id) ||
          !isNullableUuid(data.assistant_message_id) || (data.mode !== "STATELESS" && data.mode !== "PERSISTENT")) return null;
      const idsAreValid = data.mode === "STATELESS"
        ? data.session_id === null && data.user_message_id === null && data.assistant_message_id === null
        : data.session_id !== null && data.user_message_id !== null && data.assistant_message_id !== null;
      return idsAreValid ? { event, data: {
        sequence: data.sequence,
        request_id: data.request_id,
        session_id: data.session_id,
        user_message_id: data.user_message_id,
        assistant_message_id: data.assistant_message_id,
        mode: data.mode,
      } } satisfies SSEStartEvent : null;
    }
    case "metadata": {
      if (!hasExactKeys(data, ["sequence", "model", "sources"]) ||
          !(data.model === null || (typeof data.model === "string" && data.model.length > 0 && data.model.length <= 255)) ||
          !Array.isArray(data.sources) || !data.sources.every(isSource)) return null;
      return { event, data: { sequence: data.sequence, model: data.model, sources: data.sources } } satisfies SSEMetadataEvent;
    }
    case "citation": {
      if (!hasExactKeys(data, ["sequence", "citation"]) || !isCitation(data.citation)) return null;
      return { event, data: { sequence: data.sequence, citation: data.citation } } satisfies SSECitationEvent;
    }
    case "delta": {
      if (!hasExactKeys(data, ["sequence", "content"]) || typeof data.content !== "string" ||
          data.content.length === 0 || data.content.length > 1_000_000) return null;
      return { event, data: { sequence: data.sequence, content: data.content } } satisfies SSEDeltaEvent;
    }
    case "done": {
      if (!hasExactKeys(data, ["sequence", "status", "usage"]) || data.status !== "COMPLETED" || !isNullableUsage(data.usage)) return null;
      return { event, data: { sequence: data.sequence, status: data.status, usage: data.usage } } satisfies SSEDoneEvent;
    }
    case "error": {
      if (!hasExactKeys(data, ["sequence", "status", "error", "usage"]) ||
          (data.status !== "FAILED" && data.status !== "PARTIAL") || !isChatError(data.error) || !isNullableUsage(data.usage)) return null;
      return { event, data: { sequence: data.sequence, status: data.status, error: data.error, usage: data.usage } } satisfies SSEErrorEvent;
    }
    default:
      return null;
  }
}

/**
 * Incremental, transport-only SSE parser. It validates individual known event
 * payloads but intentionally does not enforce transcript ordering/terminal rules.
 */
export class SSEParser {
  private readonly decoder = new TextDecoder("utf-8", { fatal: true });
  private line = "";
  private skipLeadingLf = false;
  private eventName = "";
  private dataLines: string[] = [];
  private closed = false;

  push(chunk: Uint8Array): ParsedSSEEvent[] {
    if (this.closed) throw new SSEParserError("closed", "SSE parser đã kết thúc.");
    try {
      return this.consume(this.decoder.decode(chunk, { stream: true }));
    } catch (error) {
      if (error instanceof SSEParserError) throw error;
      this.closed = true;
      throw new SSEParserError("invalid_utf8", "Luồng SSE chứa UTF-8 không hợp lệ.");
    }
  }

  finish(): ParsedSSEEvent[] {
    if (this.closed) return [];
    this.closed = true;
    let tail: string;
    try {
      tail = this.decoder.decode();
    } catch {
      throw new SSEParserError("invalid_utf8", "Luồng SSE kết thúc giữa một ký tự UTF-8.");
    }
    const events = this.consume(tail);
    if (this.line.length > 0) {
      this.processLine(this.line, events);
      this.line = "";
    }
    this.dispatch(events);
    return events;
  }

  private consume(text: string): ParsedSSEEvent[] {
    const events: ParsedSSEEvent[] = [];
    for (const character of text) {
      if (character === "\r") {
        this.processLine(this.line, events);
        this.line = "";
        this.skipLeadingLf = true;
      } else if (character === "\n") {
        if (this.skipLeadingLf) this.skipLeadingLf = false;
        else {
          this.processLine(this.line, events);
          this.line = "";
        }
      } else {
        this.skipLeadingLf = false;
        this.line += character;
      }
    }
    return events;
  }

  private processLine(line: string, events: ParsedSSEEvent[]) {
    if (line === "") {
      this.dispatch(events);
      return;
    }
    if (line.startsWith(":")) return;
    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    let value = separator === -1 ? "" : line.slice(separator + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") this.eventName = value;
    else if (field === "data") this.dataLines.push(value);
    // id/retry and extension fields are irrelevant to the backend contract.
  }

  private dispatch(events: ParsedSSEEvent[]) {
    if (this.dataLines.length === 0) {
      this.eventName = "";
      return;
    }
    const event = this.eventName || "message";
    const rawData = this.dataLines.join("\n");
    this.eventName = "";
    this.dataLines = [];
    let data: unknown;
    try {
      data = JSON.parse(rawData);
    } catch {
      this.closed = true;
      throw new SSEParserError("invalid_json", "SSE data không phải JSON hợp lệ.", event);
    }
    if (!KNOWN_EVENTS.has(event)) {
      events.push({ recognized: false, event, data });
      return;
    }
    const known = parseKnownEvent(event, data);
    if (!known) {
      this.closed = true;
      throw new SSEParserError("invalid_contract", "SSE event không khớp contract.", event);
    }
    events.push({ recognized: true, event: known });
  }
}

export function parseSSE(chunks: Iterable<Uint8Array>): ParsedSSEEvent[] {
  const parser = new SSEParser();
  const events: ParsedSSEEvent[] = [];
  for (const chunk of chunks) events.push(...parser.push(chunk));
  events.push(...parser.finish());
  return events;
}
