"use client"

import Link from "next/link"
import { useEffect } from "react"
import { BookOpen, Database, Files, MessageSquareText } from "lucide-react"

import { DepartmentChart } from "@/components/hr/dashboard/department-chart"
import { EmployeeStatusChart } from "@/components/hr/dashboard/employee-status-chart"
import { HrKpiCards } from "@/components/hr/dashboard/hr-kpi-cards"
import { useHrChatbot } from "@/components/hr/layout/hr-chatbot-provider"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { HR_ANALYTICS_FIXTURE } from "@/fixtures/hr-analytics"
import { useDocuments } from "@/hooks/use-documents"
import { summarizeKnowledgeBaseDocuments } from "@/lib/hr/analytics"

function LiveKnowledgeBaseCard({ apiBaseUrl }: { apiBaseUrl: string }) {
  const { state } = useDocuments(apiBaseUrl)
  const summary = summarizeKnowledgeBaseDocuments(state.items)

  return (
    <Card>
      <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Database className="size-4 text-primary" aria-hidden="true" />
            <CardTitle>Kho tri thức RAG (Dữ liệu thực từ API)</CardTitle>
          </div>
          <CardDescription>
            Thống kê trực tiếp từ GET /documents đang phục vụ HR Chatbot &amp; RAG Workspace.
          </CardDescription>
        </div>
        <Badge variant="secondary">Live API</Badge>
      </CardHeader>
      <CardContent>
        {state.status === "error" ? (
          <p role="alert" className="text-sm text-destructive">
            {state.error ?? "Chưa thể kết nối Backend để đọc thống kê tài liệu."}
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-4">
            <div className="rounded-lg border p-3">
              <p className="text-xs text-muted-foreground">Tổng tài liệu</p>
              <p className="mt-1 text-xl font-semibold">
                {state.status === "loading" && state.items.length === 0 ? "…" : summary.totalDocuments}
              </p>
            </div>
            <div className="rounded-lg border p-3">
              <p className="text-xs text-muted-foreground">Sẵn sàng (INDEXED)</p>
              <p className="mt-1 text-xl font-semibold text-primary">
                {state.status === "loading" && state.items.length === 0 ? "…" : summary.indexedDocuments}
              </p>
            </div>
            <div className="rounded-lg border p-3">
              <p className="text-xs text-muted-foreground">Đang xử lý</p>
              <p className="mt-1 text-xl font-semibold">
                {state.status === "loading" && state.items.length === 0 ? "…" : summary.processingDocuments}
              </p>
            </div>
            <div className="rounded-lg border p-3">
              <p className="text-xs text-muted-foreground">Tổng Vector Chunks</p>
              <p className="mt-1 text-xl font-semibold">
                {state.status === "loading" && state.items.length === 0 ? "…" : summary.totalChunks}
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function HrDashboardView({ apiBaseUrl }: { apiBaseUrl: string | null }) {
  const { openWidget, setPageContext } = useHrChatbot()

  useEffect(() => {
    setPageContext({
      route: "/hr",
      title: "Tổng quan nhân sự",
    })
  }, [setPageContext])

  return (
    <section aria-labelledby="hr-dashboard-title" className="mx-auto w-full max-w-6xl space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-medium text-muted-foreground">Cổng nhân sự nội bộ</p>
          <h1 id="hr-dashboard-title" className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
            Dashboard &amp; Analytics nhân sự
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            Theo dõi nhanh chỉ số nhân sự (dữ liệu mô phỏng demo) và tình trạng kho tài liệu chính sách đang kết nối với Trợ lý RAG.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            className="gap-1.5"
            onClick={() =>
              openWidget({
                pageContext: { route: "/hr", title: "Tổng quan nhân sự" },
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
        </div>
      </div>

      <HrKpiCards
        kpis={HR_ANALYTICS_FIXTURE.kpis}
        asOfLabel={HR_ANALYTICS_FIXTURE.asOfLabel}
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <DepartmentChart departments={HR_ANALYTICS_FIXTURE.departments} />
        <EmployeeStatusChart statuses={HR_ANALYTICS_FIXTURE.contractStatuses} />
      </div>

      {apiBaseUrl ? (
        <LiveKnowledgeBaseCard apiBaseUrl={apiBaseUrl} />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Kho tri thức RAG</CardTitle>
            <CardDescription>
              Chưa cấu hình NEXT_PUBLIC_API_BASE_URL nên chỉ hiển thị dữ liệu nhân sự mô phỏng.
            </CardDescription>
          </CardHeader>
        </Card>
      )}
    </section>
  )
}
