import type { DocumentIndexInfo } from "@/types/document";
import { validateUploadFile } from "@/lib/documents/upload-validation";

export interface UploadState {
  phase: "idle" | "ready" | "submitting" | "received" | "error" | "uncertain";
  file: File | null;
  result: DocumentIndexInfo | null;
  error: string | null;
}
export interface UploadServices {
  upload: (file: File, signal: AbortSignal) => Promise<DocumentIndexInfo>;
}

export class UploadController {
  private state: UploadState = { phase: "idle", file: null, result: null, error: null };
  private readonly listeners = new Set<() => void>();
  private abort: AbortController | null = null;
  constructor(private readonly services: UploadServices) {}
  readonly getSnapshot = () => this.state;
  readonly subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };
  private publish(state: UploadState) {
    this.state = state;
    for (const listener of this.listeners) listener();
  }
  readonly choose = (file: File | null) => {
    if (this.abort) return;
    const error = file ? validateUploadFile(file) : null;
    this.publish({ phase: error ? "error" : file ? "ready" : "idle", file, result: null, error });
  };
  readonly submit = async (): Promise<DocumentIndexInfo | null> => {
    if (this.abort || this.state.phase !== "ready" || !this.state.file) return null;
    const file = this.state.file;
    const error = validateUploadFile(file);
    if (error) { this.publish({ ...this.state, phase: "error", error }); return null; }
    const abort = new AbortController();
    this.abort = abort;
    this.publish({ ...this.state, phase: "submitting", error: null, result: null });
    try {
      const result = await this.services.upload(file, abort.signal);
      if (abort.signal.aborted || this.abort !== abort) return null;
      this.publish({ ...this.state, phase: "received", result, error: null });
      return result;
    } catch (error) {
      if (this.abort !== abort) return null;
      const kind = typeof error === "object" && error !== null && "kind" in error ? error.kind : null;
      const status = typeof error === "object" && error !== null && "status" in error ? error.status : null;
      const uncertain = abort.signal.aborted || kind === "network" || kind === "timeout" || kind === "invalid_response"
        || kind === null || (typeof status === "number" && status >= 500);
      this.publish({ ...this.state, phase: uncertain ? "uncertain" : "error", error: uncertain
        ? "Chưa xác định được kết quả upload. Tài liệu có thể vẫn đang xử lý; hãy làm mới danh sách trước khi gửi lại."
        : "Upload không hoàn tất. Hãy kiểm tra file và làm mới danh sách trước khi gửi lại." });
      return null;
    } finally {
      if (this.abort === abort) this.abort = null;
    }
  };
  dispose() {
    if (!this.abort || this.abort.signal.aborted) return;
    this.abort.abort();
    this.publish({ ...this.state, phase: "uncertain", result: null,
      error: "Đã dừng chờ phản hồi. Xử lý trên dịch vụ có thể vẫn tiếp tục; hãy làm mới danh sách trước khi gửi lại." });
  }
}
