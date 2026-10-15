"use client"

import { useEffect, useMemo, useSyncExternalStore } from "react"
import { Button } from "@/components/ui/button"
import { createApiClient } from "@/lib/api/client"
import { checkHealth } from "@/lib/api/health"
import { HealthController, type HealthState } from "@/lib/health/controller"

export function ServiceHealthView({ state, onCheck }: { state: HealthState; onCheck: () => void }) {
  return <div className="space-y-3" aria-busy={state.status === "loading"}>
    {state.status === "idle" && <p>Chưa kiểm tra kết nối dịch vụ.</p>}
    {state.status === "loading" && <p role="status">Đang kiểm tra API, MongoDB và Qdrant…</p>}
    {state.error && <p role="alert" className="text-destructive">{state.error}</p>}
    {state.report && <div role="status" className="space-y-2">
      <p>API: phản hồi bình thường.</p>
      <p className={state.report.status === "degraded" ? "text-destructive" : "text-muted-foreground"}>
        {state.report.status === "degraded" ? "Kết nối phụ thuộc chưa sẵn sàng (HTTP 503)." : "MongoDB và Qdrant sẵn sàng."}
      </p>
      <p>MongoDB: {state.report.mongodb.message}</p>
      <p>Qdrant: {state.report.qdrant.message}</p>
    </div>}
    <p className="text-xs text-muted-foreground">Groq: chưa được kiểm tra bởi health này. Kết quả health không đảm bảo tạo câu trả lời thành công.</p>
    <Button type="button" variant="outline" size="sm" disabled={state.status === "loading"} onClick={onCheck}>Kiểm tra dịch vụ</Button>
  </div>
}

function ConfiguredHealth({ apiBaseUrl }: { apiBaseUrl: string }) {
  const controller = useMemo(() => {
    const api = createApiClient({ baseUrl: apiBaseUrl })
    return new HealthController(signal => checkHealth(api, signal))
  }, [apiBaseUrl])
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot)
  useEffect(() => () => controller.dispose(), [controller])
  return <ServiceHealthView state={state} onCheck={() => void controller.check()} />
}

export function ServiceHealth({ apiBaseUrl }: { apiBaseUrl: string | null }) {
  return <details className="relative ml-auto text-sm">
    <summary className="cursor-pointer rounded px-2 py-1 focus-visible:outline-2 focus-visible:outline-ring">Trạng thái dịch vụ</summary>
    <div className="absolute right-0 top-full z-30 mt-3 max-h-[70vh] w-[min(22rem,90vw)] overflow-auto rounded-xl border bg-popover p-4 text-popover-foreground shadow-lg">
      {apiBaseUrl ? <ConfiguredHealth key={apiBaseUrl} apiBaseUrl={apiBaseUrl} />
        : <p>Chưa cấu hình API để kiểm tra kết nối.</p>}
    </div>
  </details>
}
