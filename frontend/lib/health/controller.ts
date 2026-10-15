import type { HealthReport } from "@/lib/api/health";
import { safeApiErrorMessage } from "@/lib/api/error-ux";

export interface HealthState {
  status: "idle" | "loading" | "ready" | "error";
  report: HealthReport | null;
  error: string | null;
}
export class HealthController {
  private state: HealthState = { status: "idle", report: null, error: null };
  private abort: AbortController | null = null;
  private readonly listeners = new Set<() => void>();
  constructor(private readonly checkService: (signal: AbortSignal) => Promise<HealthReport>) {}
  readonly getSnapshot = () => this.state;
  readonly subscribe = (listener: () => void) => { this.listeners.add(listener); return () => this.listeners.delete(listener); };
  private publish(state: HealthState) { this.state = state; for (const listener of this.listeners) listener(); }
  readonly check = async () => {
    if (this.abort) return;
    const abort = new AbortController();
    this.abort = abort;
    this.publish({ status: "loading", report: null, error: null });
    try {
      const report = await this.checkService(abort.signal);
      if (abort.signal.aborted || this.abort !== abort) return;
      this.publish({ status: "ready", report, error: null });
    } catch (error) {
      if (abort.signal.aborted || this.abort !== abort) return;
      this.publish({ status: "error", report: null, error: safeApiErrorMessage(error, "Không thể kiểm tra dịch vụ. Bạn có thể kiểm tra lại chủ động.") });
    } finally { if (this.abort === abort) this.abort = null; }
  };
  dispose() {
    this.abort?.abort();
    this.publish({ status: "idle", report: null, error: null });
  }
}
