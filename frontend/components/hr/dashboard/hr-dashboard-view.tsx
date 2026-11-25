"use client"

import Link from "next/link"
import { BarChart3, BookOpen, Compass, Database, Files, MessageSquareText } from "lucide-react"

import { DepartmentChart } from "@/components/hr/dashboard/department-chart"
import { EmployeeStatusChart } from "@/components/hr/dashboard/employee-status-chart"
import { HrKpiCards } from "@/components/hr/dashboard/hr-kpi-cards"
import {
  useHrChatbot,
  useHrPageContext,
} from "@/components/hr/layout/hr-chatbot-provider"
import { useOptionalHrTour } from "@/components/hr/tour/hr-tour-provider"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { HR_ANALYTICS_FIXTURE } from "@/fixtures/hr-analytics"
import { useDocuments } from "@/hooks/use-documents"
import { summarizeKnowledgeBaseDocuments } from "@/lib/hr/analytics"
import { buildHrDashboardSnapshot } from "@/lib/hr/page-context"

function LiveKnowledgeBaseStrip({ apiBaseUrl }: { apiBaseUrl: string }) {
  const { state } = useDocuments(apiBaseUrl)
  const summary = summarizeKnowledgeBaseDocuments(state.items)
  const loading = state.status === "loading" && state.items.length === 0

  useHrPageContext({
    route: "/hr",
    liveFeatures:
      state.status === "ready"
        ? [
            `Trạng thái Kho tri thức RAG thực tế đang hiển thị: ${summary.totalDocuments} tài liệu (${summary.indexedDocuments} INDEXED, ${summary.processingDocuments} đang xử lý, ${summary.totalChunks} vector chunks).`,
          ]
        : [],
    dashboardSnapshot: buildHrDashboardSnapshot(
      HR_ANALYTICS_FIXTURE,
      state.status === "ready" ? summary : null,
    ),
  })

  return (
    <section
      aria-labelledby="live-kb-title"
      data-tour="hr-live-kb"
      data-hr-feature="Xem thống kê Kho tri thức RAG theo thời gian thực từ API và mở nhanh Kho tài liệu nhân sự."
      className="rounded-xl border bg-card p-6"
    >
      <div className="flex flex-col gap-3 border-b pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Database className="size-4 text-primary" aria-hidden="true" />
            <h2 id="live-kb-title" className="text-base font-semibold tracking-tight">
              Kho tri thức RAG (Dữ liệu thực từ API)
            </h2>
            <Badge variant="secondary" className="bg-accent text-accent-foreground">
              Live API
            </Badge>
          </div>
          <p className="text-xs leading-5 text-muted-foreground">
            Số liệu đọc trực tiếp từ GET /documents phục vụ Trợ lý HR và RAG Workspace.
          </p>
        </div>

        <Button nativeButton={false} variant="outline" size="sm" render={<Link href="/hr/documents" />}>
          <Files className="size-3.5" aria-hidden="true" />
          <span>Mở kho tài liệu</span>
        </Button>
      </div>

      {state.status === "error" ? (
        <p role="alert" className="pt-4 text-sm text-destructive">
          {state.error ?? "Chưa thể kết nối Backend để đọc thống kê tài liệu."}
        </p>
      ) : (
        <dl className="grid divide-y divide-border pt-4 sm:grid-cols-2 sm:divide-x sm:divide-y-0 lg:grid-cols-4">
          <div className="py-2 sm:px-4 first:sm:pl-0">
            <dt className="text-xs text-muted-foreground">Tổng tài liệu</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">
              {loading ? "…" : summary.totalDocuments}
            </dd>
          </div>
          <div className="py-2 sm:px-4">
            <dt className="text-xs text-muted-foreground">Sẵn sàng (INDEXED)</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums text-primary">
              {loading ? "…" : summary.indexedDocuments}
            </dd>
          </div>
          <div className="py-2 sm:px-4">
            <dt className="text-xs text-muted-foreground">Đang xử lý</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">
              {loading ? "…" : summary.processingDocuments}
            </dd>
          </div>
          <div className="py-2 sm:px-4 last:sm:pr-0">
            <dt className="text-xs text-muted-foreground">Tổng Vector Chunks</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">
              {loading ? "…" : summary.totalChunks}
            </dd>
          </div>
        </dl>
      )}
    </section>
  )
}

export function HrDashboardView({ apiBaseUrl }: { apiBaseUrl: string | null }) {
  const { openWidget } = useHrChatbot()
  const tour = useOptionalHrTour()

  useHrPageContext(
    apiBaseUrl
      ? null
      : {
          route: "/hr",
          liveFeatures: [
            "Chưa cấu hình NEXT_PUBLIC_API_BASE_URL nên hiện chỉ hiển thị số liệu nhân sự mô phỏng, chưa tải thống kê Kho tri thức RAG thực.",
          ],
          dashboardSnapshot: buildHrDashboardSnapshot(HR_ANALYTICS_FIXTURE, null),
        },
  )

  return (
    <section aria-labelledby="hr-dashboard-title" className="mx-auto w-full max-w-6xl space-y-8">
      <div className="flex flex-col gap-5 border-b pb-6 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-2xl space-y-2">
          <h1
            id="hr-dashboard-title"
            className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl"
          >
            Dashboard &amp; Analytics nhân sự
          </h1>
          <p className="text-sm leading-6 text-muted-foreground">
            Theo dõi nhanh chỉ số nhân sự mô phỏng và tình trạng kho tài liệu chính sách đang kết nối với Trợ lý RAG.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            className="gap-1.5 shadow-2xs transition-transform active:scale-[0.99]"
            onClick={() =>
              openWidget({
                prompt: "Hãy phân tích và thống kê nhân sự trên trang Dashboard hiện tại.",
              })
            }
          >
            <BarChart3 className="size-4" aria-hidden="true" />
            <span>Phân tích Dashboard</span>
          </Button>
          <Button
            type="button"
            variant="outline"
            className="gap-1.5"
            onClick={() =>
              openWidget({
                prompt: "Tóm tắt các chính sách phúc lợi và nghỉ phép nổi bật hiện nay.",
              })
            }
          >
            <MessageSquareText className="size-4" aria-hidden="true" />
            <span>Hỏi Trợ lý HR</span>
          </Button>
          <Button nativeButton={false} variant="outline" render={<Link href="/hr/documents" />}>
            <Files className="size-4" aria-hidden="true" />
            <span>Tài liệu nhân sự</span>
          </Button>
          <Button nativeButton={false} variant="ghost" render={<Link href="/hr/guide" />}>
            <BookOpen className="size-4" aria-hidden="true" />
            <span>Hướng dẫn</span>
          </Button>
          <Button type="button" variant="ghost" onClick={() => tour?.startTour(0, "all")}>
            <Compass className="size-4" aria-hidden="true" />
            <span>Product Tour</span>
          </Button>
        </div>
      </div>

      <div
        data-tour="hr-kpi-strip"
        data-hr-feature="Dải thẻ KPI nhân sự tổng hợp quy mô nhân sự, tuyển mới, tỉ lệ nghỉ việc và thâm niên trung bình."
      >
        <HrKpiCards
          kpis={HR_ANALYTICS_FIXTURE.kpis}
          asOfLabel={HR_ANALYTICS_FIXTURE.asOfLabel}
        />
      </div>

      <div
        data-tour="hr-analytics-charts"
        data-hr-feature="Cặp biểu đồ phân bổ nhân sự theo phòng ban và tỉ trọng loại hợp đồng lao động."
        className="grid gap-6 lg:grid-cols-12"
      >
        <div className="lg:col-span-7">
          <DepartmentChart departments={HR_ANALYTICS_FIXTURE.departments} />
        </div>
        <div className="lg:col-span-5">
          <EmployeeStatusChart statuses={HR_ANALYTICS_FIXTURE.contractStatuses} />
        </div>
      </div>

      {apiBaseUrl ? (
        <LiveKnowledgeBaseStrip apiBaseUrl={apiBaseUrl} />
      ) : (
        <section data-tour="hr-live-kb" className="rounded-xl border bg-card p-6">
          <h2 className="text-base font-semibold tracking-tight">Kho tri thức RAG</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Chưa cấu hình NEXT_PUBLIC_API_BASE_URL nên hiện chỉ hiển thị dữ liệu nhân sự mô phỏng.
          </p>
        </section>
      )}
    </section>
  )
}
