"use client"

import { useState } from "react"
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  LoaderCircle,
  RefreshCw,
} from "lucide-react"

import {
  DeleteDocumentDialog,
  UploadDocumentDialog,
} from "@/components/documents/document-dialogs"
import { DocumentStatusBadge } from "@/components/documents/document-status-badge"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { documentFixtures } from "@/fixtures/documents"
import { cn } from "@/lib/utils"
import type { DocumentDetail, DocumentVersionInfo } from "@/types/document"

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
  selectedId,
  onSelect,
}: {
  selectedId: string
  onSelect: (document: DocumentDetail) => void
}) {
  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b py-4">
        <div className="flex items-center justify-between gap-3">
          <CardTitle>Tài liệu</CardTitle>
          <Badge variant="secondary">{documentFixtures.length} fixture</Badge>
        </div>
      </CardHeader>
      <CardContent className="p-2">
        <div className="space-y-1" role="list" aria-label="Danh sách tài liệu mẫu">
          {documentFixtures.map((document) => {
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
        <p>Backend đang xử lý đồng bộ. Contract hiện không có endpoint polling tiến trình.</p>
      </div>
    )
  }

  if (document.status === "FAILED") {
    return (
      <div role="status" className="flex gap-3 rounded-lg border border-destructive/25 bg-destructive/5 p-3 text-sm">
        <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
        <p className="text-muted-foreground">
          Lần ingestion này thất bại. Chi tiết lỗi an toàn sẽ được hiển thị khi kết nối API.
        </p>
      </div>
    )
  }

  if (document.status === "INDEXED") {
    return (
      <div className="flex gap-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">
        <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <p>Phiên bản hoạt động đã sẵn sàng cho retrieval.</p>
      </div>
    )
  }

  return null
}

function DocumentDetailPanel({ document }: { document: DocumentDetail }) {
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
          <div className="flex flex-wrap gap-2">
            <UploadDocumentDialog mode="version" />
            <Button variant="outline" size="sm" disabled>
              <RefreshCw aria-hidden="true" />
              Re-index
            </Button>
            <DeleteDocumentDialog fileName={document.file_name} />
          </div>
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

export function DocumentsPreview() {
  const [selectedDocument, setSelectedDocument] = useState<DocumentDetail>(documentFixtures[0])

  return (
    <section aria-labelledby="documents-title" className="mx-auto flex w-full max-w-6xl flex-1 flex-col">
      <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium text-muted-foreground">Nguồn tri thức</p>
            <Badge variant="outline">Fixture UI</Badge>
          </div>
          <h1 id="documents-title" className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
            Tài liệu
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            Xem trước danh sách, phiên bản và trạng thái ingestion trước khi kết nối backend.
          </p>
        </div>
        <UploadDocumentDialog />
      </div>

      <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(18rem,0.8fr)_minmax(0,1.5fr)]">
        <DocumentList selectedId={selectedDocument.document_id} onSelect={setSelectedDocument} />
        <DocumentDetailPanel document={selectedDocument} />
      </div>
    </section>
  )
}
