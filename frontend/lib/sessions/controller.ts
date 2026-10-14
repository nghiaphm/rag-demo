import type { SessionPageResponse, SessionResponse } from "@/types/sessions";

type Listener = () => void;
type LoadStatus = "idle" | "loading" | "ready" | "error";

export interface SessionsState {
  status: LoadStatus;
  sessions: readonly SessionResponse[];
  total: number;
  isCreating: boolean;
  error: string | null;
}

export interface SessionsServices {
  list: (signal: AbortSignal) => Promise<SessionPageResponse>;
  create: (signal: AbortSignal) => Promise<SessionResponse>;
}

export class SessionsController {
  private state: SessionsState = {
    status: "idle",
    sessions: [],
    total: 0,
    isCreating: false,
    error: null,
  };
  private readonly listeners = new Set<Listener>();
  private loadAbort: AbortController | null = null;
  private createAbort: AbortController | null = null;

  constructor(private readonly services: SessionsServices) {}

  readonly getSnapshot = () => this.state;

  readonly subscribe = (listener: Listener) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private publish(next: SessionsState) {
    this.state = next;
    for (const listener of this.listeners) listener();
  }

  readonly load = async () => {
    this.loadAbort?.abort();
    const abort = new AbortController();
    this.loadAbort = abort;
    this.publish({ ...this.state, status: "loading", error: null });
    try {
      const page = await this.services.list(abort.signal);
      if (abort.signal.aborted || this.loadAbort !== abort) return;
      this.publish({
        ...this.state,
        status: "ready",
        sessions: [...page.items],
        total: page.total,
        error: null,
      });
    } catch {
      if (abort.signal.aborted || this.loadAbort !== abort) return;
      this.publish({
        ...this.state,
        status: "error",
        error: "Không thể tải danh sách phiên trò chuyện.",
      });
    } finally {
      if (this.loadAbort === abort) this.loadAbort = null;
    }
  };

  readonly createNew = async (): Promise<SessionResponse | null> => {
    if (this.createAbort) return null;
    const abort = new AbortController();
    this.createAbort = abort;
    this.publish({ ...this.state, isCreating: true, error: null });
    try {
      const session = await this.services.create(abort.signal);
      if (abort.signal.aborted || this.createAbort !== abort) return null;
      const sessions = [session, ...this.state.sessions.filter(
        (item) => item.session_id !== session.session_id
      )];
      this.publish({
        ...this.state,
        status: "ready",
        sessions,
        total: Math.max(this.state.total + 1, sessions.length),
        error: null,
      });
      return session;
    } catch {
      if (!abort.signal.aborted && this.createAbort === abort) {
        this.publish({ ...this.state, error: "Không thể tạo phiên trò chuyện mới." });
      }
      return null;
    } finally {
      if (this.createAbort === abort) {
        this.createAbort = null;
        this.publish({ ...this.state, isCreating: false });
      }
    }
  };

  dispose() {
    this.loadAbort?.abort();
    this.createAbort?.abort();
  }
}

export type SessionLookupStatus = "idle" | "loading" | "ready" | "invalid" | "missing" | "error";

export interface SessionLookupState {
  status: SessionLookupStatus;
  session: SessionResponse | null;
}

export interface SessionLookupServices {
  isValidId: (sessionId: string) => boolean;
  get: (sessionId: string, signal: AbortSignal) => Promise<SessionResponse>;
}

function errorStatus(error: unknown): number | null {
  if (typeof error !== "object" || error === null || !("status" in error)) return null;
  return typeof error.status === "number" ? error.status : null;
}

export class SessionLookupController {
  private state: SessionLookupState;
  private readonly listeners = new Set<Listener>();
  private abort: AbortController | null = null;

  constructor(
    private readonly sessionId: string,
    private readonly services: SessionLookupServices
  ) {
    this.state = {
      status: services.isValidId(sessionId) ? "idle" : "invalid",
      session: null,
    };
  }

  readonly getSnapshot = () => this.state;

  readonly subscribe = (listener: Listener) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private publish(next: SessionLookupState) {
    this.state = next;
    for (const listener of this.listeners) listener();
  }

  readonly load = async () => {
    if (!this.services.isValidId(this.sessionId)) {
      this.publish({ status: "invalid", session: null });
      return;
    }
    this.abort?.abort();
    const abort = new AbortController();
    this.abort = abort;
    this.publish({ status: "loading", session: null });
    try {
      const session = await this.services.get(this.sessionId, abort.signal);
      if (abort.signal.aborted || this.abort !== abort) return;
      this.publish({ status: "ready", session });
    } catch (error) {
      if (abort.signal.aborted || this.abort !== abort) return;
      const status = errorStatus(error);
      this.publish({
        status: status === 404 || status === 410 ? "missing" : "error",
        session: null,
      });
    } finally {
      if (this.abort === abort) this.abort = null;
    }
  };

  dispose() {
    this.abort?.abort();
  }
}
