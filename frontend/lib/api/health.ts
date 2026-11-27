import type { createApiClient } from "@/lib/api/client";

export interface SafeDependencyHealth { ok: boolean; code: string; message: string }
export interface HealthReport {
  api: "ok";
  status: "ok" | "degraded";
  httpStatus: 200 | 503;
  mongodb: SafeDependencyHealth;
  qdrant: SafeDependencyHealth;
}
const record = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const labels: Record<string, string> = {
  connected: "Sẵn sàng", not_checked: "Chưa kiểm tra", not_configured: "Chưa được cấu hình",
  authentication_failed: "Xác thực thất bại", invalid_configuration: "Cấu hình không hợp lệ",
  timeout: "Hết thời gian chờ", server_rejected: "Dịch vụ từ chối kết nối", connection_failed: "Không thể kết nối",
};
function dependency(name: string, value: unknown): SafeDependencyHealth {
  if (!record(value) || value.service !== name || typeof value.ok !== "boolean"
    || typeof value.code !== "string" || typeof value.message !== "string") throw new TypeError("Invalid dependency health contract.");
  // Reconstruct safe UI data; never retain arbitrary server messages/extra keys.
  const code = Object.hasOwn(labels, value.code) ? value.code : "unknown";
  return { ok: value.ok, code, message: value.ok ? "Sẵn sàng" : labels[code] ?? "Chưa sẵn sàng" };
}

/** Manual read only. Readiness 503 is a typed degraded report, not a successful 200. */
export async function checkHealth(api: ReturnType<typeof createApiClient>, signal?: AbortSignal): Promise<HealthReport> {
  const health = await api.request<unknown>("/health", { method: "GET", signal, timeoutMs: 20_000 });
  if (health.status !== 200 || !record(health.data) || health.data.status !== "ok" || typeof health.data.llm_model !== "string") {
    throw new TypeError("Invalid health contract.");
  }
  const readiness = await api.request<unknown>("/health/dependencies", { method: "GET", signal, timeoutMs: 20_000, acceptedStatuses: [503] });
  const data = readiness.data;
  if (![200, 503].includes(readiness.status) || !record(data) || !record(data.dependencies)
    || !["ok", "degraded"].includes(String(data.status))) throw new TypeError("Invalid readiness contract.");
  const deps = data.dependencies;
  const mongodb = dependency("mongodb", deps.mongodb);
  const qdrant = dependency("qdrant", deps.qdrant);
  const optionalEntries = ["redis", "s3"]
    .filter(name => deps[name] !== undefined)
    .map(name => dependency(name, deps[name]));
  const isOkStatus = data.status === "ok";
  if (isOkStatus !== (readiness.status === 200)) throw new TypeError("Inconsistent readiness contract.");
  if (isOkStatus && (!mongodb.ok || !qdrant.ok)) throw new TypeError("Inconsistent readiness contract.");
  if (!isOkStatus && mongodb.ok && qdrant.ok && optionalEntries.every(entry => entry.ok)) {
    throw new TypeError("Inconsistent readiness contract.");
  }
  return { api: "ok", status: isOkStatus ? "ok" : "degraded", httpStatus: readiness.status as 200 | 503, mongodb, qdrant };
}
