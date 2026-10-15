import type { DeleteSessionResponse, ListSessionsQuery, SessionPageResponse, SessionResponse } from "@/types/sessions";
import { safeApiErrorMessage } from "@/lib/api/error-ux";

type Listener = () => void;
type LoadStatus = "idle" | "loading" | "ready" | "error";

export interface SessionsState {
  status: LoadStatus;
  sessions: readonly SessionResponse[];
  total: number;
  isCreating: boolean;
  error: string | null;
  isMutating: boolean;
  mutationError: string | null;
}

export interface SessionsServices {
  list: (signal: AbortSignal, query?: Required<ListSessionsQuery>) => Promise<SessionPageResponse>;
  create: (signal: AbortSignal) => Promise<SessionResponse>;
  rename?: (id: string, title: string, signal: AbortSignal) => Promise<SessionResponse>;
  remove?: (id: string, signal: AbortSignal) => Promise<DeleteSessionResponse>;
}

export class SessionsController {
  private state: SessionsState = {
    status: "idle",
    sessions: [],
    total: 0,
    isCreating: false,
    error: null,
    isMutating: false,
    mutationError: null,
  };
  private readonly listeners = new Set<Listener>();
  private loadAbort: AbortController | null = null;
  private createAbort: AbortController | null = null;
  private mutationAbort: AbortController | null = null;
  private nextOffset = 0;
  private refreshPending = false;

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

  readonly load = () => this.loadPage(true);
  readonly loadMore = () => this.loadPage(false);

  readonly invalidate = () => {
    this.refreshPending = true;
    if (!this.mutationAbort && !this.createAbort) void this.load();
  };

  private async loadPage(reset: boolean) {
    if (this.mutationAbort || this.createAbort || (!reset && (this.loadAbort || this.nextOffset >= this.state.total))) return;
    if (reset) this.refreshPending = false;
    this.loadAbort?.abort();
    const abort = new AbortController();
    this.loadAbort = abort;
    this.publish({ ...this.state, status: "loading", error: null });
    try {
      const offset = reset ? 0 : this.nextOffset;
      const page = await this.services.list(abort.signal, { offset, limit: 50 });
      if (abort.signal.aborted || this.loadAbort !== abort) return;
      const combined = reset ? [...page.items] : [...this.state.sessions, ...page.items];
      if (page.offset !== offset || page.limit !== 50 || page.items.length > 50
        || new Set(combined.map(item => item.session_id)).size !== combined.length
        || (page.items.length === 0 && offset < page.total)) throw new Error("Invalid session pagination");
      this.nextOffset = offset + page.items.length;
      this.publish({
        ...this.state,
        status: "ready",
        sessions: combined,
        total: page.total,
        error: null,
      });
    } catch (error) {
      if (abort.signal.aborted || this.loadAbort !== abort) return;
      this.publish({
        ...this.state,
        status: "error",
        error: safeApiErrorMessage(error, "Không thể tải danh sách phiên trò chuyện."),
      });
    } finally {
      if (this.loadAbort === abort) this.loadAbort = null;
    }
  };

  readonly createNew = async (): Promise<SessionResponse | null> => {
    if (this.createAbort || this.mutationAbort) return null;
    this.loadAbort?.abort();
    this.loadAbort = null;
    const abort = new AbortController();
    this.createAbort = abort;
    this.publish({ ...this.state, status: this.state.status === "loading" ? "idle" : this.state.status, isCreating: true, error: null });
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
      this.nextOffset = sessions.length;
      return session;
    } catch (error) {
      if (!abort.signal.aborted && this.createAbort === abort) {
        this.publish({ ...this.state, error: safeApiErrorMessage(error, "Không thể tạo phiên trò chuyện mới. Kiểm tra danh sách trước khi tạo lại." ) });
      }
      return null;
    } finally {
      if (this.createAbort === abort) {
        this.createAbort = null;
        this.publish({ ...this.state, isCreating: false });
        if (this.refreshPending) void this.load();
      }
    }
  };

  readonly rename = async (id: string, title: string): Promise<SessionResponse | null> => {
    return this.mutate("rename", id, title) as Promise<SessionResponse | null>;
  };
  readonly remove = async (id: string, confirmed: boolean): Promise<DeleteSessionResponse | null> => {
    if (!confirmed) return null;
    return this.mutate("delete", id) as Promise<DeleteSessionResponse | null>;
  };
  private async mutate(kind: "rename" | "delete", id: string, title = "") {
    if (this.mutationAbort || this.createAbort) return null;
    const abort = new AbortController();
    this.mutationAbort = abort;
    this.loadAbort?.abort();
    this.loadAbort = null;
    this.publish({ ...this.state, status: "ready", isMutating: true, mutationError: null });
    let result: SessionResponse | DeleteSessionResponse | null = null;
    try {
      if (kind === "rename") {
        if (!this.services.rename) throw new Error("Unsupported action");
        result = await this.services.rename(id, title, abort.signal);
      } else {
        if (!this.services.remove) throw new Error("Unsupported action");
        result = await this.services.remove(id, abort.signal);
      }
      if (abort.signal.aborted || this.mutationAbort !== abort) return null;
      if (result.session_id !== id) throw new Error("Wrong mutation session");
      const sessions = kind === "delete" ? this.state.sessions.filter(item => item.session_id !== id)
        : this.state.sessions.map(item => item.session_id === id ? result as SessionResponse : item)
          .sort((a, b) => b.updated_at.localeCompare(a.updated_at) || b.session_id.localeCompare(a.session_id));
      this.nextOffset = sessions.length;
      this.publish({ ...this.state, sessions, total: kind === "delete" ? Math.max(0, this.state.total - 1) : this.state.total });
    } catch (error) {
      result = null;
      if (!abort.signal.aborted) this.publish({ ...this.state,
        mutationError: `${safeApiErrorMessage(error, "Không thể xác nhận thao tác phiên.")} Không tự gửi lại; hãy làm mới danh sách để kiểm tra.`,
      });
    } finally {
      if (this.mutationAbort === abort) {
        this.mutationAbort = null;
        this.publish({ ...this.state, isMutating: false });
      }
    }
    if (abort.signal.aborted) return null;
    if (result || this.refreshPending) void this.load();
    return result;
  }

  dispose() {
    this.refreshPending = false;
    this.loadAbort?.abort();
    this.createAbort?.abort();
    this.mutationAbort?.abort();
    if (this.mutationAbort) {
      this.mutationAbort = null;
      this.publish({ ...this.state, isMutating: false, mutationError: "Đã dừng chờ phản hồi. Hãy làm mới danh sách trước khi gửi lại." });
    }
  }
}

export type SessionLookupStatus = "idle" | "loading" | "ready" | "invalid" | "missing" | "error";

export interface SessionLookupState {
  status: SessionLookupStatus;
  session: SessionResponse | null;
  error: string | null;
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
      error: null,
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
      this.publish({ status: "invalid", session: null, error: null });
      return;
    }
    this.abort?.abort();
    const abort = new AbortController();
    this.abort = abort;
    this.publish({ status: "loading", session: null, error: null });
    try {
      const session = await this.services.get(this.sessionId, abort.signal);
      if (abort.signal.aborted || this.abort !== abort) return;
      this.publish({ status: "ready", session, error: null });
    } catch (error) {
      if (abort.signal.aborted || this.abort !== abort) return;
      const status = errorStatus(error);
      this.publish({
        status: status === 404 || status === 410 ? "missing" : "error",
        session: null,
        error: safeApiErrorMessage(error, "Không thể xác minh phiên với API. Bạn có thể thử tải lại."),
      });
    } finally {
      if (this.abort === abort) this.abort = null;
    }
  };

  dispose() {
    this.abort?.abort();
  }
}
