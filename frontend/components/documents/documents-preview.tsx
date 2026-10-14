"use client"

import {
  AlertCircle,
  CheckCircle2,
  FileText,
  LoaderCircle,
  RefreshCw,
} from "lucide-react"

import { DocumentActions } from "@/components/documents/document-actions"
import { DocumentStatusBadge } from "@/components/documents/document-status-badge"
import { DocumentUpload } from "@/components/documents/document-upload"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { useDocuments } from "@/hooks/use-documents"
import type { DocumentsController, DocumentsState } from "@/lib/documents/controller"
import { cn } from "@/lib/utils"
import type { DocumentDetail, DocumentInfo, DocumentVersionInfo } from "@/types/document"

const dateFormatter = new Intl.DateTimeFormat("vi-VN", {
  dateStyle: "medium",
  timeStyle: "short",
})

function formatDate(value: string | null | undefined) {
  return value ? dateFormatter.format(new Date(value)) : "Chưa có"
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

function DocumentList({
  documents,
  selectedId,
  onSelect,
}: {
  documents: readonly DocumentInfo[]
  selectedId: string | null
  onSelect: (document: DocumentInfo) => void
}) {
  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b py-4">
        <div className="flex items-center justify-between gap-3">
          <CardTitle>Tài liệu</CardTitle>
          <Badge variant="secondary">{documents.length} đã tải</Badge>
        </div>
      </CardHeader>
      <CardContent className="p-2">
        <div className="space-y-1" role="list" aria-label="Danh sách tài liệu">
          {documents.map((document) => {
            const isSelected = document.document_id === selectedId

            return (
              <div key={document.document_id} role="listitem">
                <button
                  type="button"
                  aria-pressed={isSelected}
                  onClick={() => onSelect(document)}
                  className={cn(
                    "flex w-full items-start gap-3 rounded-lg p-3 text-left outline-none transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring",
                    isSelected && "bg-muted"
                  )}
                >
                  <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg border bg-background">
                    <FileText className="size-4 text-muted-foreground" aria-hidden="true" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{document.file_name}</span>
                    <span className="mt-1 block text-xs text-muted-foreground">
                      {document.chunk_count} chunks · {document.version_count} phiên bản
                    </span>
                    <span className="mt-1 block truncate text-xs text-muted-foreground" title={document.active_version_id ?? undefined}>
                      Active version: {document.active_version_id ?? "Chưa có"}
                    </span>
                  </span>
                  <DocumentStatusBadge status={document.status} />
                </button>
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

function VersionRow({ version, isActive }: { version: DocumentVersionInfo; isActive: boolean }) {
  return (
    <li className="flex flex-col gap-3 rounded-lg border p-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">Phiên bản {version.version}</span>
          {isActive && <Badge variant="secondary">Đang hoạt động</Badge>}
          <DocumentStatusBadge status={version.status} />
        </div>
        <p className="mt-1 truncate text-xs text-muted-foreground">
          {formatBytes(version.size_bytes)} · {version.chunk_count} chunks · {formatDate(version.indexed_at)}
        </p>
      </div>
      <code className="max-w-full truncate rounded bg-muted px-2 py-1 text-xs text-muted-foreground sm:max-w-40">
        {version.version_id}
      </code>
    </li>
  )
}

function DocumentStateNotice({ document }: { document: DocumentDetail }) {
  if (document.status === "PROCESSING") {
    return (
      <div className="flex gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
        <LoaderCircle className="mt-0.5 size-4 shrink-0 animate-spin" aria-hidden="true" />
        <p>Tài liệu đang xử lý. Phiên bản hoạt động hiện tại được hiển thị riêng bên dưới; dùng Làm mới để kiểm tra lại.</p>
      </div>
    )
  }

  if (document.status === "FAILED") {
    return (
      <div role="status" className="flex gap-3 rounded-lg border border-destructive/25 bg-destructive/5 p-3 text-sm">
        <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
        <p className="text-muted-foreground">
          Trạng thái tài liệu là FAILED. Kiểm tra phiên bản hoạt động và lịch sử bên dưới; trạng thái này không thay thế active version ID.
        </p>
      </div>
    )
  }

  if (document.status === "DELETED") {
    return <p role="status" className="rounded-lg border p-3 text-sm text-muted-foreground">
      Tài liệu đã bị xóa khỏi nguồn truy xuất. {document.cleanup_pending ? "Đang chờ dọn dữ liệu truy xuất." : "Lịch sử phiên bản vẫn được giữ."}
    </p>
  }

  if (document.status === "INDEXED" && document.versions.some(version => version.version_id === document.active_version_id && version.status === "INDEXED")) {
    return (
      <div className="flex gap-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">
        <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <p>Tài liệu INDEXED và có phiên bản hoạt động đã được index.</p>
      </div>
    )
  }

  return null
}

export function DocumentDetailPanel({ document, apiBaseUrl = null, reconcile }: {
  document: DocumentDetail; apiBaseUrl?: string | null; reconcile?: (document: DocumentDetail) => void
}) {
  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b py-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle className="truncate">{document.file_name}</CardTitle>
              <DocumentStatusBadge status={document.status} />
            </div>
            <p className="mt-1 text-xs text-muted-foreground">Cập nhật {formatDate(document.updated_at)}</p>
          </div>
          <DocumentActions document={document} apiBaseUrl={apiBaseUrl} reconcile={reconcile} />
        </div>
      </CardHeader>

      <CardContent className="space-y-5 p-4 sm:p-5">
        <DocumentStateNotice document={document} />

        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-lg bg-muted/60 p-3">
            <dt className="text-xs text-muted-foreground">Chunks</dt>
            <dd className="mt-1 text-lg font-semibold">{document.chunk_count}</dd>
          </div>
          <div className="rounded-lg bg-muted/60 p-3">
            <dt className="text-xs text-muted-foreground">Phiên bản</dt>
            <dd className="mt-1 text-lg font-semibold">{document.version_count}</dd>
          </div>
          <div className="col-span-2 rounded-lg bg-muted/60 p-3">
            <dt className="text-xs text-muted-foreground">Active version ID</dt>
            <dd className="mt-1 truncate font-mono text-xs" title={document.active_version_id ?? undefined}>
              {document.active_version_id ?? "Chưa có phiên bản hoạt động"}
            </dd>
          </div>
          <div className="col-span-2 rounded-lg bg-muted/60 p-3">
            <dt className="text-xs text-muted-foreground">Trạng thái tài liệu</dt>
            <dd className="mt-1"><DocumentStatusBadge status={document.status} /></dd>
          </div>
        </dl>

        <Separator />

        <div>
          <h3 className="text-sm font-semibold">Lịch sử phiên bản</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Phiên bản mới chỉ trở thành active sau khi ingestion thành công.
          </p>
          <ul className="mt-3 space-y-2">
            {document.versions.map((version) => (
              <VersionRow
                key={version.version_id}
                version={version}
                isActive={version.version_id === document.active_version_id}
              />
            ))}
          </ul>
        </div>
      </CardContent>
    </Card>
  )
}

export function DocumentsDataView({ state, controller, apiBaseUrl = null }: {
  state: DocumentsState
  apiBaseUrl?: string | null
  controller: Pick<DocumentsController, "reload" | "loadMore" | "retry" | "select" | "setIncludeDeleted" | "reconcile">
}) {
  return (
    <section aria-labelledby="documents-title" className="mx-auto flex w-full max-w-6xl flex-1 flex-col">
      <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium text-muted-foreground">Nguồn tri thức</p>
            <Badge variant="outline">API</Badge>
          </div>
          <h1 id="documents-title" className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
            Tài liệu
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            Danh sách tài liệu, phiên bản hoạt động và trạng thái từ backend.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" onClick={() => void controller.reload()} disabled={state.status === "loading"}>
            <RefreshCw aria-hidden="true" />Làm mới
          </Button>
          <DocumentUpload apiBaseUrl={apiBaseUrl} onRefresh={controller.reload} onUploaded={controller.reload} />
        </div>
      </div>

      <label className="mb-4 flex items-center gap-2 text-sm">
        <input type="checkbox" checked={state.includeDeleted} onChange={event => void controller.setIncludeDeleted(event.target.checked)}
          className="size-4 accent-primary focus-visible:outline-2 focus-visible:outline-ring" />
        Bao gồm tài liệu đã xóa
      </label>
      <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(18rem,0.8fr)_minmax(0,1.5fr)]">
        <div className="min-w-0 space-y-3" aria-busy={state.status === "loading"}>
          <DocumentList documents={state.items} selectedId={state.selectedId} onSelect={document => void controller.select(document.document_id)} />
          {(state.status === "idle" || state.status === "loading") && <p role="status" className="text-sm text-muted-foreground">Đang tải danh sách tài liệu…</p>}
          {state.status === "ready" && state.items.length === 0 && <p role="status" className="rounded-lg border p-4 text-sm text-muted-foreground">Chưa có tài liệu trong danh sách này.</p>}
          {state.status === "error" && <div role="alert" className="rounded-lg border border-destructive/25 p-4 text-sm">
            <p>{state.error}</p><Button className="mt-3" type="button" variant="outline" onClick={() => void controller.retry()}>Thử lại danh sách</Button>
          </div>}
          {state.hasMore && state.status !== "error" && <Button type="button" variant="outline" disabled={state.status === "loading"} onClick={() => void controller.loadMore()}>Tải thêm tài liệu</Button>}
          {state.status === "ready" && !state.hasMore && state.items.length > 0 && <p className="text-xs text-muted-foreground">Đã tải hết danh sách hiện tại.</p>}
        </div>
        <div className="min-w-0" aria-busy={state.detailStatus === "loading"}>
          {state.detailStatus === "ready" && state.detail ? <DocumentDetailPanel document={state.detail} apiBaseUrl={apiBaseUrl} reconcile={controller.reconcile} />
            : <DocumentDetailState state={state} onRetry={() => state.selectedId && void controller.select(state.selectedId)} />}
        </div>
      </div>
    </section>
  )
}

function DocumentDetailState({ state, onRetry }: { state: DocumentsState; onRetry: () => void }) {
  const messages = { idle: "Chọn tài liệu để xem chi tiết.", loading: "Đang tải chi tiết tài liệu…",
    missing: "Tài liệu này không còn tồn tại. Hãy làm mới danh sách.", error: "Không thể tải chi tiết tài liệu. Bạn có thể thử lại.", ready: "Chưa có chi tiết tài liệu." }
  return <div role={state.detailStatus === "error" || state.detailStatus === "missing" ? "alert" : "status"} className="rounded-xl border bg-background p-5 text-sm text-muted-foreground">
    <p>{messages[state.detailStatus]}</p>
    {state.detailStatus === "error" && <Button className="mt-3" type="button" variant="outline" onClick={onRetry}>Thử lại chi tiết</Button>}
  </div>
}

function ConfiguredDocuments({ apiBaseUrl }: { apiBaseUrl: string }) {
  const { state, controller } = useDocuments(apiBaseUrl)
  return <DocumentsDataView state={state} controller={controller} apiBaseUrl={apiBaseUrl} />
}

export function DocumentsPreview({ apiBaseUrl }: { apiBaseUrl: string | null }) {
  if (!apiBaseUrl) return <section aria-labelledby="documents-title" className="mx-auto w-full max-w-6xl">
    <h1 id="documents-title" className="text-2xl font-semibold">Tài liệu</h1>
    <p role="alert" className="mt-4 rounded-lg border p-4 text-sm">Chưa cấu hình NEXT_PUBLIC_API_BASE_URL để tải tài liệu.</p>
  </section>
  return <ConfiguredDocuments key={apiBaseUrl} apiBaseUrl={apiBaseUrl} />
}
