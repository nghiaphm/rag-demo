import type { ChatStreamRequestOptions, ChatStreamResult } from "@/lib/api/chat";
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
}

export interface ChatControllerServices {
  createSession: (signal: AbortSignal) => Promise<{ session_id: string }>;
  stream: (payload: ChatRequest, options?: ChatStreamRequestOptions) => Promise<ChatStreamResult>;
}

type Listener = () => void;
type CancellationReason = "user" | "navigation";

interface ActiveTurn {
  userKey: string;
  assistantKey: string;
  sessionId: string | null;
  abortController: AbortController;
  cancellationReason: CancellationReason | null;
  terminal: boolean;
}

function safeGenerationError(): ChatError {
  return {
    code: "CLIENT_STREAM_ERROR",
    message: "Không thể hoàn tất câu trả lời. Vui lòng thử lại.",
    retryable: true,
  };
}

function safeCancellationError(reason: CancellationReason): ChatError {
  return {
    code: "RAG_STREAM_CANCELLED",
    message: reason === "user"
      ? "Bạn đã dừng tạo câu trả lời."
      : "Luồng trả lời đã dừng khi rời trang.",
    retryable: false,
  };
}

export class ChatController {
  private state: ChatState;
  private readonly listeners = new Set<Listener>();
  private turnNumber = 0;
  private activeTurn: ActiveTurn | null = null;

  constructor(
    private readonly services: ChatControllerServices,
    initialSessionId: string | null = null
  ) {
    this.state = { sessionId: initialSessionId, messages: [], isGenerating: false };
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

  private acceptEvent(event: SSEEvent) {
    const turn = this.activeTurn;
    if (!turn) throw new Error("Không có lượt chat đang hoạt động.");

    switch (event.event) {
      case "start": {
        const data = event.data;
        if (
          data.mode !== "PERSISTENT"
          || !data.session_id
          || !data.user_message_id
          || !data.assistant_message_id
          || data.session_id !== turn.sessionId
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
          error: event.data.error,
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
    if (!turn || turn.terminal || turn.abortController.signal.aborted) return;
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
    this.publish({
      ...this.state,
      isGenerating: true,
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
        const session = await this.services.createSession(turn.abortController.signal);
        sessionId = session.session_id;
        if (turn.abortController.signal.aborted) throw new Error("Lượt chat đã bị hủy.");
        turn.sessionId = sessionId;
        this.publish({ ...this.state, sessionId });
      }
      await this.services.stream(
        { question, session_id: sessionId },
        {
          signal: turn.abortController.signal,
          onEvent: (event) => this.acceptEvent(event),
        }
      );
    } catch {
      if (!turn.terminal) {
        this.updateMessage(assistantKey, (message) => ({
          ...message,
          status: message.content ? "PARTIAL" : "FAILED",
          error: message.error ?? (
            turn.cancellationReason
              ? safeCancellationError(turn.cancellationReason)
              : safeGenerationError()
          ),
        }));
      }
    } finally {
      if (this.activeTurn === turn) this.activeTurn = null;
      this.publish({ ...this.state, isGenerating: false });
    }
    return true;
  }
}
