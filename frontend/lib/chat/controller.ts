import type { ChatStreamRequestOptions, ChatStreamResult } from "@/lib/api/chat";
import { safeApiErrorMessage, safeStreamErrorMessage } from "@/lib/api/error-ux";
import type {
  ChatError,
  ChatRequest,
  ChatUsage,
  Citation,
  Source,
  SSEEvent,
} from "@/types/chat";
import type { MessageStatus } from "@/types/sessions";

export interface ChatViewMessage {
  /** UI provenance only; never serialized into the API message DTO. */
  origin?: "history";
  key: string;
  messageId: string | null;
  requestId: string | null;
  role: "user" | "assistant";
  content: string;
  status: MessageStatus;
  model: string | null;
  sources: readonly Source[];
  citations: readonly Citation[];
  usage: ChatUsage | null;
  error: ChatError | null;
}

export interface ChatState {
  sessionId: string | null;
  messages: readonly ChatViewMessage[];
  isGenerating: boolean;
  isVerifyingHistory: boolean;
  persistenceError: string | null;
  historyVerified: boolean;
}

export interface ChatControllerServices {
  createSession: (signal: AbortSignal) => Promise<{ session_id: string }>;
  stream: (payload: ChatRequest, options?: ChatStreamRequestOptions) => Promise<ChatStreamResult>;
  loadHistory?: (sessionId: string, signal: AbortSignal) => Promise<readonly ChatViewMessage[]>;
}

type Listener = () => void;
type CancellationReason = "user" | "navigation" | "timeout";

interface ActiveTurn {
  userKey: string;
  assistantKey: string;
  sessionId: string | null;
  abortController: AbortController;
  cancellationReason: CancellationReason | null;
  terminal: boolean;
}

function safeGenerationError(error: unknown): ChatError {
  return {
    code: "CLIENT_STREAM_ERROR",
    message: safeApiErrorMessage(error, "Không thể hoàn tất câu trả lời. Kiểm tra lịch sử trước khi gửi lại chủ động."),
    retryable: true,
  };
}

function safeCancellationError(reason: CancellationReason): ChatError {
  return {
    code: reason === "timeout" ? "CLIENT_STREAM_TIMEOUT" : "RAG_STREAM_CANCELLED",
    message: reason === "timeout" ? "Đã hết thời gian chờ câu trả lời. Nội dung nhận được được giữ lại; kiểm tra lịch sử trước khi gửi lại."
      : reason === "user"
      ? "Bạn đã dừng tạo câu trả lời."
      : "Luồng trả lời đã dừng khi rời trang.",
    retryable: false,
  };
}

/** Release UI even if a mock/transport ignores abort; consume late rejections safely. */
function waitForSignal<T>(promise: Promise<T>, signal: AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    const aborted = () => reject(new Error("Turn aborted"));
    if (signal.aborted) aborted();
    else signal.addEventListener("abort", aborted, { once: true });
    promise.then(value => { signal.removeEventListener("abort", aborted); resolve(value); }, error => {
      signal.removeEventListener("abort", aborted); reject(error);
    });
  });
}

export class ChatController {
  private state: ChatState;
  private readonly listeners = new Set<Listener>();
  private turnNumber = 0;
  private activeTurn: ActiveTurn | null = null;

  constructor(
    private readonly services: ChatControllerServices,
    initialSessionId: string | null = null,
    initialMessages: readonly ChatViewMessage[] = [],
    private readonly waitTimeoutMs = 180_000
  ) {
    if (!Number.isInteger(waitTimeoutMs) || waitTimeoutMs < 1 || waitTimeoutMs > 2_147_483_647) throw new TypeError("Invalid chat wait timeout.");
    this.state = {
      sessionId: initialSessionId,
      messages: [...initialMessages],
      isGenerating: false,
      isVerifyingHistory: false,
      persistenceError: null,
      historyVerified: false,
    };
  }

  readonly getSnapshot = () => this.state;

  readonly subscribe = (listener: Listener) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private publish(next: ChatState) {
    this.state = next;
    for (const listener of this.listeners) listener();
  }

  private updateMessage(key: string, update: (message: ChatViewMessage) => ChatViewMessage) {
    this.publish({
      ...this.state,
      messages: this.state.messages.map((message) => message.key === key ? update(message) : message),
    });
  }

  private acceptEvent(turn: ActiveTurn, event: SSEEvent) {
    // A callback belongs to one turn, even when a cancelled transport finishes late.
    if (this.activeTurn !== turn || turn.abortController.signal.aborted || turn.terminal) return;

    switch (event.event) {
      case "start": {
        const data = event.data;
        if (
          data.mode !== "PERSISTENT"
          || !data.session_id
          || !data.user_message_id
          || !data.assistant_message_id
          || data.session_id !== turn.sessionId
          || data.user_message_id === data.assistant_message_id
          || this.state.messages.some((message) =>
            message.requestId === data.request_id
            || message.messageId === data.user_message_id
            || message.messageId === data.assistant_message_id)
        ) {
          throw new Error("Start event không khớp persistent session hiện tại.");
        }
        this.updateMessage(turn.userKey, (message) => ({
          ...message,
          messageId: data.user_message_id,
          requestId: data.request_id,
          status: "COMPLETED",
        }));
        this.updateMessage(turn.assistantKey, (message) => ({
          ...message,
          messageId: data.assistant_message_id,
          requestId: data.request_id,
          status: "STREAMING",
        }));
        break;
      }
      case "metadata":
        this.updateMessage(turn.assistantKey, (message) => ({
          ...message,
          model: event.data.model,
          sources: [...event.data.sources],
        }));
        break;
      case "citation":
        this.updateMessage(turn.assistantKey, (message) => ({
          ...message,
          citations: [...message.citations, event.data.citation],
        }));
        break;
      case "delta":
        this.updateMessage(turn.assistantKey, (message) => ({
          ...message,
          content: message.content + event.data.content,
          status: "STREAMING",
        }));
        break;
      case "done":
        turn.terminal = true;
        this.updateMessage(turn.assistantKey, (message) => ({
          ...message,
          status: event.data.status,
          usage: event.data.usage,
        }));
        break;
      case "error":
        turn.terminal = true;
        this.updateMessage(turn.assistantKey, (message) => ({
          ...message,
          status: event.data.status,
          error: { ...event.data.error, message: safeStreamErrorMessage(event.data.error.code) },
          usage: event.data.usage,
        }));
        break;
    }
  }

  /** Abort the active request once. The submitted turn is never retried automatically. */
  stop(): boolean {
    const turn = this.activeTurn;
    if (!turn || turn.terminal || turn.abortController.signal.aborted) return false;
    turn.cancellationReason = "user";
    turn.abortController.abort();
    return true;
  }

  /** React unmount/navigation cleanup; safe to call more than once. */
  dispose() {
    const turn = this.activeTurn;
    if (!turn || turn.abortController.signal.aborted) return;
    turn.cancellationReason = "navigation";
    turn.abortController.abort();
  }

  /** Returns false for blank or duplicate submits; true means the turn was accepted. */
  async submit(rawQuestion: string): Promise<boolean> {
    const question = rawQuestion.trim();
    if (!question || this.activeTurn) return false;

    this.turnNumber += 1;
    const userKey = `local-user-${this.turnNumber}`;
    const assistantKey = `local-assistant-${this.turnNumber}`;
    const turn: ActiveTurn = {
      userKey,
      assistantKey,
      sessionId: this.state.sessionId,
      abortController: new AbortController(),
      cancellationReason: null,
      terminal: false,
    };
    this.activeTurn = turn;
    const deadline = setTimeout(() => {
      turn.cancellationReason = "timeout";
      turn.abortController.abort();
    }, this.waitTimeoutMs);
    this.publish({
      ...this.state,
      isGenerating: true,
      persistenceError: null,
      historyVerified: false,
      messages: [
        ...this.state.messages,
        {
          key: userKey,
          messageId: null,
          requestId: null,
          role: "user",
          content: question,
          status: "PENDING",
          model: null,
          sources: [],
          citations: [],
          usage: null,
          error: null,
        },
        {
          key: assistantKey,
          messageId: null,
          requestId: null,
          role: "assistant",
          content: "",
          status: "PENDING",
          model: null,
          sources: [],
          citations: [],
          usage: null,
          error: null,
        },
      ],
    });

    try {
      let sessionId = this.state.sessionId;
      if (!sessionId) {
        const session = await waitForSignal(this.services.createSession(turn.abortController.signal), turn.abortController.signal);
        sessionId = session.session_id;
        if (turn.abortController.signal.aborted) throw new Error("Lượt chat đã bị hủy.");
        turn.sessionId = sessionId;
        this.publish({ ...this.state, sessionId });
      }
      await waitForSignal(this.services.stream(
        { question, session_id: sessionId },
        {
          signal: turn.abortController.signal,
          onEvent: (event) => this.acceptEvent(turn, event),
        }
      ), turn.abortController.signal);
    } catch (error) {
      if (!turn.terminal) {
        this.updateMessage(assistantKey, (message) => ({
          ...message,
          status: message.content ? "PARTIAL" : "FAILED",
          error: message.error ?? (
            turn.cancellationReason
              ? safeCancellationError(turn.cancellationReason)
              : safeGenerationError(error)
          ),
        }));
      }
      if (!turn.terminal) this.updateMessage(userKey, (message) => message.status === "PENDING" ? { ...message, status: "FAILED" } : message);
    } finally {
      // Backend finalizes before emitting terminal SSE. Read it once; never retry
      // the submitted request or treat a history failure as generation failure.
      if (turn.terminal && turn.sessionId && this.services.loadHistory && !turn.abortController.signal.aborted) {
        this.publish({ ...this.state, isVerifyingHistory: true });
        try {
          const history = await waitForSignal(this.services.loadHistory(turn.sessionId, turn.abortController.signal), turn.abortController.signal);
          if (!turn.abortController.signal.aborted && this.activeTurn === turn) {
            const user = this.state.messages.find((message) => message.key === turn.userKey)!;
            const assistant = this.state.messages.find((message) => message.key === turn.assistantKey)!;
            for (const local of [user, assistant]) {
              const persisted = history.find((message) => message.messageId === local.messageId);
              if (!persisted || persisted.requestId !== local.requestId
                || persisted.role !== local.role || persisted.content !== local.content
                || persisted.status !== local.status
                || (local.role === "assistant" && (
                  persisted.model !== local.model
                  || persisted.usage?.input_tokens !== local.usage?.input_tokens
                  || persisted.usage?.output_tokens !== local.usage?.output_tokens
                  || persisted.usage?.total_tokens !== local.usage?.total_tokens
                  || (persisted.error?.code ?? null) !== (local.error?.code ?? null)
                ))) {
                throw new Error("Persisted turn không khớp SSE.");
              }
            }
            const current = new Map(this.state.messages.map((message) => [message.messageId, message]));
            this.publish({ ...this.state, historyVerified: true, messages: history.map((message) => ({
              ...message,
              sources: current.get(message.messageId)?.sources ?? message.sources,
            })) });
          }
        } catch {
          if ((!turn.abortController.signal.aborted || turn.cancellationReason === "timeout") && this.activeTurn === turn) {
            this.publish({ ...this.state, persistenceError:
              "Chưa xác minh được lịch sử đã lưu. Nội dung hiện tại được giữ lại; hãy tải lại phiên để kiểm tra." });
          }
        }
      }
      if (turn.terminal && turn.cancellationReason === "timeout" && this.services.loadHistory) {
        this.publish({ ...this.state, persistenceError: "Đã hết thời gian chờ xác minh lịch sử. Câu trả lời hiện tại được giữ lại; hãy tải lại phiên để kiểm tra." });
      }
      clearTimeout(deadline);
      if (this.activeTurn === turn) this.activeTurn = null;
      this.publish({ ...this.state, isGenerating: false, isVerifyingHistory: false });
    }
    return true;
  }
}
