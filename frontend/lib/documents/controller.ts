import type { DocumentDetail, DocumentInfo, ListDocumentsQuery } from "@/types/document";
import { safeApiErrorMessage } from "@/lib/api/error-ux";

export interface DocumentsState {
  status: "idle" | "loading" | "ready" | "error";
  items: readonly DocumentInfo[];
  includeDeleted: boolean;
  nextOffset: number;
  hasMore: boolean;
  error: string | null;
  selectedId: string | null;
  detailStatus: "idle" | "loading" | "ready" | "missing" | "error";
  detail: DocumentDetail | null;
  detailError: string | null;
}
export interface DocumentsServices {
  list: (query: ListDocumentsQuery, signal: AbortSignal) => Promise<DocumentInfo[]>;
  get: (id: string, signal: AbortSignal) => Promise<DocumentDetail>;
}

export class DocumentsController {
  private state: DocumentsState = { status: "idle", items: [], includeDeleted: false, nextOffset: 0,
    hasMore: false, error: null, selectedId: null, detailStatus: "idle", detail: null, detailError: null };
  private readonly listeners = new Set<() => void>();
  private listAbort: AbortController | null = null;
  private detailAbort: AbortController | null = null;
  constructor(private readonly services: DocumentsServices, private readonly pageSize = 20) {
    if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 500) throw new TypeError("Invalid document page size.");
  }
  readonly getSnapshot = () => this.state;
  readonly subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };
  private publish(state: DocumentsState) {
    this.state = state;
    for (const listener of this.listeners) listener();
  }
  private async load(reset: boolean) {
    if (!reset && (this.listAbort || !this.state.hasMore)) return;
    this.listAbort?.abort();
    const abort = new AbortController();
    this.listAbort = abort;
    if (reset) this.detailAbort?.abort();
    const offset = reset ? 0 : this.state.nextOffset;
    const includeDeleted = this.state.includeDeleted;
    this.publish({ ...this.state, status: "loading", error: null,
      ...(reset ? { items: [], nextOffset: 0, hasMore: false, selectedId: null, detail: null, detailError: null, detailStatus: "idle" as const } : {}) });
    try {
      const items = await this.services.list({ offset, limit: this.pageSize, include_deleted: includeDeleted }, abort.signal);
      if (abort.signal.aborted || this.listAbort !== abort) return;
      const combined = [...this.state.items, ...items];
      if (new Set(combined.map(item => item.document_id)).size !== combined.length) throw new Error("Overlapping document pages.");
      this.publish({ ...this.state, status: "ready", items: combined, nextOffset: offset + items.length,
        hasMore: items.length === this.pageSize, error: null });
    } catch (error) {
      if (abort.signal.aborted || this.listAbort !== abort) return;
      this.publish({ ...this.state, status: "error", error: safeApiErrorMessage(error, "Không thể tải danh sách tài liệu. Bạn có thể thử lại.") });
    } finally {
      if (this.listAbort === abort) this.listAbort = null;
    }
  }
  readonly reload = () => this.load(true);
  readonly loadMore = () => this.load(false);
  readonly retry = () => this.load(this.state.items.length === 0);
  readonly setIncludeDeleted = (includeDeleted: boolean) => {
    this.publish({ ...this.state, includeDeleted });
    return this.load(true);
  };
  readonly select = async (id: string) => {
    this.detailAbort?.abort();
    const abort = new AbortController();
    this.detailAbort = abort;
    this.publish({ ...this.state, selectedId: id, detail: null, detailStatus: "loading", detailError: null });
    try {
      const detail = await this.services.get(id, abort.signal);
      if (abort.signal.aborted || this.detailAbort !== abort) return;
      if (detail.document_id !== id) throw new Error("Wrong document detail.");
      this.publish({ ...this.state, detail, detailStatus: "ready" });
    } catch (error) {
      if (abort.signal.aborted || this.detailAbort !== abort) return;
      const missing = typeof error === "object" && error !== null && "status" in error && error.status === 404;
      this.publish({ ...this.state, detail: null, detailStatus: missing ? "missing" : "error", detailError: safeApiErrorMessage(error, "Không thể tải chi tiết tài liệu. Bạn có thể thử lại.") });
    } finally {
      if (this.detailAbort === abort) this.detailAbort = null;
    }
  };
  /** Authoritative detail returned after an action; never overwrite a different selection. */
  readonly reconcile = (detail: DocumentDetail) => {
    if (this.state.selectedId !== detail.document_id) return;
    this.detailAbort?.abort();
    this.listAbort?.abort();
    // The stale transport may settle late. Release its slot immediately so
    // load-more can read the new offset; existing signal/identity guards drop it.
    this.detailAbort = null;
    this.listAbort = null;
    const remove = detail.status === "DELETED" && !this.state.includeDeleted;
    const existed = this.state.items.some(item => item.document_id === detail.document_id);
    const items = remove ? this.state.items.filter(item => item.document_id !== detail.document_id)
      : this.state.items.map(item => item.document_id === detail.document_id ? detail : item);
    this.publish({ ...this.state, status: "ready", error: null, items,
      nextOffset: Math.max(0, this.state.nextOffset - (remove && existed ? 1 : 0)),
      detail, detailStatus: "ready", detailError: null });
  };
  dispose() {
    this.listAbort?.abort();
    this.detailAbort?.abort();
  }
}
