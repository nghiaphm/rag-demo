import type { ChatViewMessage } from "@/lib/chat/controller";
import { safeApiErrorMessage } from "@/lib/api/error-ux";
import type { ListMessagesQuery, MessagePageResponse, MessageResponse } from "@/types/sessions";

type Listener = () => void;

export interface HistoryState {
  status: "idle" | "loading" | "ready" | "error";
  messages: readonly MessageResponse[];
  total: number;
  error: string | null;
}

export interface HistoryServices {
  list: (
    sessionId: string,
    query: Required<ListMessagesQuery>,
    signal: AbortSignal
  ) => Promise<MessagePageResponse>;
}

function stableMessageOrder(left: MessageResponse, right: MessageResponse) {
  return left.sequence - right.sequence || left.message_id.localeCompare(right.message_id);
}

/** Shared paginated read for route restoration and post-turn reconciliation. */
export async function loadMessageHistory(
  sessionId: string,
  services: HistoryServices,
  signal: AbortSignal,
  pageSize = 100
): Promise<MessageResponse[]> {
  if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 500) {
    throw new TypeError("History pageSize phải nằm trong khoảng 1..500.");
  }
  const messages: MessageResponse[] = [];
  let offset = 0;
  let total = 0;
  do {
    signal.throwIfAborted();
    const page = await services.list(sessionId, { offset, limit: pageSize }, signal);
    signal.throwIfAborted();
    if (page.offset !== offset || page.limit !== pageSize || page.items.length > pageSize) {
      throw new Error("History pagination không liên tục.");
    }
    if (page.items.some((message) => message.session_id !== sessionId)) {
      throw new Error("History chứa message của session khác.");
    }
    messages.push(...page.items);
    total = page.total;
    if (page.items.length === 0 && messages.length < total) {
      throw new Error("History pagination không thể tiến tiếp.");
    }
    offset += page.items.length;
  } while (messages.length < total);
  const ordered = [...messages].sort(stableMessageOrder);
  if (ordered.length !== total) throw new Error("History total không khớp số message.");
  const messageIds = new Set<string>();
  const sequences = new Set<number>();
  for (const message of ordered) {
    if (messageIds.has(message.message_id) || sequences.has(message.sequence)) {
      throw new Error("History chứa message ID hoặc sequence trùng.");
    }
    messageIds.add(message.message_id);
    sequences.add(message.sequence);
  }
  return ordered;
}

export class HistoryController {
  private state: HistoryState = { status: "idle", messages: [], total: 0, error: null };
  private readonly listeners = new Set<Listener>();
  private abort: AbortController | null = null;

  constructor(
    private readonly sessionId: string,
    private readonly services: HistoryServices,
    private readonly pageSize = 100
  ) {
    if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 500) {
      throw new TypeError("History pageSize phải nằm trong khoảng 1..500.");
    }
  }

  readonly getSnapshot = () => this.state;

  readonly subscribe = (listener: Listener) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private publish(next: HistoryState) {
    this.state = next;
    for (const listener of this.listeners) listener();
  }

  readonly load = async () => {
    this.abort?.abort();
    const abort = new AbortController();
    this.abort = abort;
    this.publish({ ...this.state, status: "loading", error: null });

    try {
      const messages = await loadMessageHistory(this.sessionId, this.services, abort.signal, this.pageSize);
      if (abort.signal.aborted || this.abort !== abort) return;
      this.publish({ status: "ready", messages, total: messages.length, error: null });
    } catch (error) {
      if (abort.signal.aborted || this.abort !== abort) return;
      this.publish({ status: "error", messages: [], total: 0, error: safeApiErrorMessage(error, "Không thể tải lịch sử đầy đủ. Bạn có thể thử tải lại.") });
    } finally {
      if (this.abort === abort) this.abort = null;
    }
  };

  dispose() {
    this.abort?.abort();
  }
}

export function historyMessageToViewMessage(message: MessageResponse): ChatViewMessage {
  const hasError = message.status === "FAILED" || message.status === "PARTIAL";
  return {
    origin: "history",
    key: `${message.session_id}:${message.message_id}`,
    messageId: message.message_id,
    requestId: message.request_id,
    role: message.role === "USER" ? "user" : "assistant",
    content: message.content,
    ...(message.attachments?.length ? { attachments: message.attachments } : {}),
    status: message.status,
    model: message.model,
    sources: [],
    citations: message.citations,
    usage: message.usage,
    error: hasError ? {
      code: message.error_code ?? "HISTORY_TERMINAL_ERROR",
      message: message.status === "PARTIAL"
        ? "Câu trả lời trước đó chưa hoàn tất."
        : "Câu trả lời trước đó đã thất bại.",
      retryable: false,
    } : null,
  };
}
