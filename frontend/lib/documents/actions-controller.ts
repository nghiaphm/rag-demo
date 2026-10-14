import type { DocumentDeleteResult } from "@/lib/api/documents";
import type { DocumentDetail, DocumentIndexInfo } from "@/types/document";
import { validateUploadFile } from "@/lib/documents/upload-validation";

export type DocumentAction = "version" | "reindex" | "delete";
export type ActionReceipt = { action: "version" | "reindex"; result: DocumentIndexInfo }
  | { action: "delete"; result: DocumentDeleteResult };
export interface ActionState {
  phase: "idle" | "checking" | "submitting" | "reconciling" | "done" | "error" | "uncertain";
  receipt: ActionReceipt | null;
  message: string | null;
  refreshError: boolean;
}
export interface ActionServices {
  get: (id: string, signal: AbortSignal) => Promise<DocumentDetail>;
  update: (id: string, file: File, signal: AbortSignal) => Promise<DocumentIndexInfo>;
  reindex: (id: string, signal: AbortSignal) => Promise<DocumentIndexInfo>;
  remove: (id: string, signal: AbortSignal) => Promise<DocumentDeleteResult>;
  reconcile: (document: DocumentDetail) => void;
}

export function sameDocumentSnapshot(a: DocumentDetail, b: DocumentDetail) {
  return a.document_id === b.document_id && a.updated_at === b.updated_at && a.status === b.status
    && a.active_version_id === b.active_version_id && a.version_count === b.version_count && a.file_name === b.file_name;
}

export class DocumentActionsController {
  private state: ActionState = { phase: "idle", receipt: null, message: null, refreshError: false };
  private readonly listeners = new Set<() => void>();
  private abort: AbortController | null = null;
  constructor(private readonly services: ActionServices) {}
  readonly getSnapshot = () => this.state;
  readonly subscribe = (listener: () => void) => { this.listeners.add(listener); return () => this.listeners.delete(listener); };
  private publish(state: ActionState) { this.state = state; for (const listener of this.listeners) listener(); }
  readonly reset = () => {
    if (!this.abort) this.publish({ phase: "idle", receipt: null, message: null, refreshError: false });
  };
  readonly run = async (action: DocumentAction, snapshot: DocumentDetail, confirmed: boolean, file?: File): Promise<boolean> => {
    if (!confirmed || this.abort || this.state.phase !== "idle") return false;
    const validation = action === "version" ? validateUploadFile(file ?? null) : null;
    if (validation) { this.publish({ ...this.state, phase: "error", message: validation }); return false; }
    const abort = new AbortController();
    this.abort = abort;
    let sent = false;
    let phase: ActionState["phase"] = "done";
    let message: string | null = null;
    let receipt: ActionReceipt | null = null;
    this.publish({ phase: "checking", receipt: null, message: null, refreshError: false });
    try {
      const current = await this.services.get(snapshot.document_id, abort.signal);
      abort.signal.throwIfAborted();
      if (!sameDocumentSnapshot(snapshot, current)) {
        this.services.reconcile(current);
        throw new Error("STALE_DOCUMENT");
      }
      if (action !== "delete" && (current.status === "DELETED" || current.status === "PROCESSING")) throw new Error("PROTECTED_DOCUMENT");
      if (action === "reindex" && !current.active_version_id) throw new Error("PROTECTED_DOCUMENT");
      this.publish({ ...this.state, phase: "submitting" });
      sent = true;
      if (action === "version") receipt = { action, result: await this.services.update(current.document_id, file!, abort.signal) };
      else if (action === "reindex") receipt = { action, result: await this.services.reindex(current.document_id, abort.signal) };
      else receipt = { action, result: await this.services.remove(current.document_id, abort.signal) };
      abort.signal.throwIfAborted();
    } catch (error) {
      if (abort.signal.aborted) return false;
      phase = sent ? "uncertain" : "error";
      message = sent ? "Thao tác không hoàn tất hoặc chưa xác định kết quả. Không tự gửi lại; kiểm tra trạng thái đã lưu bên dưới."
        : error instanceof Error && error.message === "STALE_DOCUMENT"
          ? "Tài liệu đã thay đổi. Chi tiết được cập nhật; hãy xem lại và xác nhận một thao tác mới."
          : "Không thể thực hiện thao tác với trạng thái hiện tại. Hãy kiểm tra hoặc tải lại tài liệu.";
    } finally {
      let refreshError = false;
      if (sent && !abort.signal.aborted) {
        this.publish({ ...this.state, phase: "reconciling", receipt, message });
        try {
          const current = await this.services.get(snapshot.document_id, abort.signal);
          if (!abort.signal.aborted) this.services.reconcile(current);
        } catch { refreshError = !abort.signal.aborted; }
      }
      if (this.abort === abort) this.abort = null;
      if (!abort.signal.aborted) this.publish({ phase, receipt, message, refreshError });
    }
    return receipt !== null && !abort.signal.aborted;
  };
  dispose() {
    if (!this.abort) return;
    this.abort.abort();
    this.publish({ ...this.state, phase: "uncertain", message: "Đã dừng chờ. Dịch vụ có thể vẫn xử lý; kiểm tra lại trước khi gửi thao tác mới." });
  }
}
