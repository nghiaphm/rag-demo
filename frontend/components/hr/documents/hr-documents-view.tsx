"use client"

import { useEffect, useState } from "react"
import {
  AlertCircle,
  FileText,
  Info,
  LoaderCircle,
  MessageSquareText,
  RefreshCw,
  Search,
} from "lucide-react"

import { DocumentPreview } from "@/components/chat/document-preview"
import { DocumentStatusBadge } from "@/components/documents/document-status-badge"
import { HrUploadDialog } from "@/components/hr/documents/hr-upload-dialog"
import { useHrChatbot } from "@/components/hr/layout/hr-chatbot-provider"
import { LoadingSkeleton } from "@/components/layout/loading-skeleton"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"
import { useDocuments } from "@/hooks/use-documents"
import { hasPendingIngestion } from "@/lib/documents/controller"
import {
  classifyHrDocument,
  countDocumentsByCategory,
  filterHrDocuments,
  getHrCategoryLabel,
  HR_DOCUMENT_CATEGORIES,
} from "@/lib/hr/document-categories"
import { cn } from "@/lib/utils"
import type { DocumentInfo } from "@/types/document"
import type { HrDocumentCategory } from "@/types/hr"

const dateFormatter = new Intl.DateTimeFormat("vi-VN", {
  dateStyle: "medium",
  timeStyle: "short",
})

function formatDate(value: string | null | undefined): string {
  return value ? dateFormatter.format(new Date(value)) : "Chưa có"
}

function ConfiguredHrDocuments({ apiBaseUrl }: { apiBaseUrl: string }) {
  const { state, controller } = useDocuments(apiBaseUrl)
  const { openWidget, setPageContext } = useHrChatbot()
  const [selectedCategory, setSelectedCategory] = useState<HrDocumentCategory | "ALL">("ALL")
  const [searchQuery, setSearchQuery] = useState("")

  const categoryCounts = countDocumentsByCategory(state.items)
  const filteredDocuments = filterHrDocuments(state.items, {
    category: selectedCategory,
    query: searchQuery,
  })
  const pendingIngestion = hasPendingIngestion(state)

  useEffect(() => {
    setPageContext({
      route: "/hr/documents",
      title: "Tài liệu nhân sự",
      selectedDocumentId: state.detail?.document_id,
      selectedDocumentName: state.detail?.file_name,
      selectedCategory: selectedCategory === "ALL" ? undefined : selectedCategory,
    })
  }, [setPageContext, state.detail?.document_id, state.detail?.file_name, selectedCategory])

  function handleSelectDocument(doc: DocumentInfo) {
    void controller.select(doc.document_id)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-medium text-muted-foreground">Kho tài liệu nhân sự</p>
          <h1 id="hr-documents-title" className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
            HR Documents
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            Tra cứu chính sách, quy định, quy trình nội bộ và tải lên tài liệu mới để đồng bộ trực tiếp vào RAG Knowledge Base.
          </p>
        </div>

        <HrUploadDialog
          apiBaseUrl={apiBaseUrl}
          onUploaded={controller.reload}
          onRefresh={controller.reload}
        />
      </div>

      <div className="flex items-start gap-2.5 rounded-xl border bg-background px-4 py-3 text-xs leading-5 text-muted-foreground shadow-xs">
        <Info className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
        <p>
          <strong className="font-medium text-foreground">Phân loại hiển thị theo tên file:</strong>{" "}
          Nhãn <em>Chính sách / Quy định / Quy trình</em> được suy luận tại giao diện để dễ tra cứu và{" "}
          <strong>không</strong> phải bộ lọc bảo mật hay cô lập retrieval. Kho tri thức được dùng chung với{" "}
          <code>/documents</code>.
        </p>
      </div>

      <div className="flex flex-col gap-3 rounded-xl border bg-background p-3 shadow-xs lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Phân loại tài liệu nhân sự">
          <Button
            type="button"
            role="tab"
            aria-selected={selectedCategory === "ALL"}
            size="sm"
            variant={selectedCategory === "ALL" ? "default" : "outline"}
            onClick={() => setSelectedCategory("ALL")}
          >
            Tất cả ({categoryCounts.ALL})
          </Button>
          {HR_DOCUMENT_CATEGORIES.map((category) => (
            <Button
              key={category.id}
              type="button"
              role="tab"
              aria-selected={selectedCategory === category.id}
              size="sm"
              variant={selectedCategory === category.id ? "default" : "outline"}
              onClick={() => setSelectedCategory(category.id)}
              title={category.description}
            >
              {category.label} ({categoryCounts[category.id]})
            </Button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <div className="relative min-w-56 flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Tìm tên tài liệu HR…"
              aria-label="Tìm tên tài liệu HR"
              className="pl-8"
            />
          </div>
          <Button
            type="button"
            variant="outline"
            size="icon"
            aria-label="Làm mới danh sách tài liệu"
            disabled={state.status === "loading"}
            onClick={() => void controller.reload()}
          >
            <RefreshCw
              className={cn("size-4", state.status === "loading" && "animate-spin")}
              aria-hidden="true"
            />
          </Button>
        </div>
      </div>

      {pendingIngestion && (
        <p role="status" className="flex items-center gap-2 text-xs text-muted-foreground">
          <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />
          Có tài liệu đang xử lý bất đồng bộ; danh sách đang tự động cập nhật.
        </p>
      )}

      {state.status === "loading" && state.items.length === 0 ? (
        <LoadingSkeleton />
      ) : state.status === "error" ? (
        <Card>
          <CardContent className="flex flex-col items-start gap-3 py-6">
            <div className="flex items-center gap-2 text-destructive">
              <AlertCircle className="size-4" aria-hidden="true" />
              <p className="text-sm font-medium">{state.error ?? "Không tải được danh sách tài liệu."}</p>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={() => void controller.reload()}>
              Thử lại
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
          <Card className="gap-0 py-0">
            <CardHeader className="border-b py-4">
              <div className="flex items-center justify-between gap-2">
                <CardTitle className="text-base">Danh sách tài liệu</CardTitle>
                <Badge variant="secondary">{filteredDocuments.length} mục</Badge>
              </div>
            </CardHeader>
            <CardContent className="p-2">
              {filteredDocuments.length === 0 ? (
                <p className="p-6 text-center text-sm text-muted-foreground">
                  Không có tài liệu phù hợp bộ lọc hiện tại.
                </p>
              ) : (
                <div className="space-y-1" role="list" aria-label="Danh sách tài liệu nhân sự">
                  {filteredDocuments.map((doc) => {
                    const isSelected = doc.document_id === state.selectedId
                    const category = classifyHrDocument(doc.file_name)
                    return (
                      <div key={doc.document_id} role="listitem">
                        <button
                          type="button"
                          aria-pressed={isSelected}
                          onClick={() => handleSelectDocument(doc)}
                          className={cn(
                            "flex w-full items-start gap-3 rounded-lg p-3 text-left outline-none transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring",
                            isSelected && "bg-muted"
                          )}
                        >
                          <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg border bg-background">
                            <FileText className="size-4 text-muted-foreground" aria-hidden="true" />
                          </span>
                          <span className="min-w-0 flex-1 space-y-1">
                            <span className="block truncate text-sm font-medium">{doc.file_name}</span>
                            <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                              <Badge variant="outline" className="h-5 px-1.5 text-[10px]">
                                {getHrCategoryLabel(category)}
                              </Badge>
                              <span>{doc.chunk_count} chunks</span>
                            </span>
                          </span>
                          <DocumentStatusBadge status={doc.status} />
                        </button>
                      </div>
                    )
                  })}
                </div>
              )}
              {state.hasMore && (
                <div className="border-t p-2">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="w-full"
                    disabled={state.status === "loading"}
                    onClick={() => void controller.loadMore()}
                  >
                    Tải thêm tài liệu
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Thông tin &amp; Nội dung tài liệu</CardTitle>
              <CardDescription>
                Chọn một tài liệu bên trái để kiểm tra phiên bản hoạt động và đọc trước nội dung.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {!state.selectedId ? (
                <p className="py-10 text-center text-sm text-muted-foreground">
                  Chưa chọn tài liệu nào.
                </p>
              ) : state.detailStatus === "loading" ? (
                <LoadingSkeleton />
              ) : state.detailStatus === "error" || !state.detail ? (
                <p role="alert" className="text-sm text-destructive">
                  {state.detailError ?? "Không thể tải chi tiết tài liệu."}
                </p>
              ) : (
                <div className="space-y-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="truncate text-lg font-semibold">{state.detail.file_name}</h2>
                        <Badge variant="outline">
                          {getHrCategoryLabel(classifyHrDocument(state.detail.file_name))}
                        </Badge>
                        <DocumentStatusBadge status={state.detail.status} />
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {state.detail.chunk_count} chunks · {state.detail.version_count} phiên bản · Cập nhật {formatDate(state.detail.updated_at)}
                      </p>
                    </div>

                    <Button
                      type="button"
                      size="sm"
                      className="shrink-0 gap-1.5"
                      onClick={() =>
                        openWidget({
                          pageContext: {
                            route: "/hr/documents",
                            title: state.detail!.file_name,
                            selectedDocumentId: state.detail!.document_id,
                            selectedDocumentName: state.detail!.file_name,
                          },
                          prompt: `Tóm tắt các điểm quan trọng trong tài liệu "${state.detail!.file_name}".`,
                        })
                      }
                    >
                      <MessageSquareText className="size-4" aria-hidden="true" />
                      <span>Hỏi Chatbot về tài liệu này</span>
                    </Button>
                  </div>

                  <Separator />

                  {state.detail.active_version_id ? (
                    <div className="space-y-2">
                      <p className="text-xs font-medium text-muted-foreground">
                        Nội dung xem trước (Phiên bản đang hoạt động)
                      </p>
                      <DocumentPreview
                        apiBaseUrl={apiBaseUrl}
                        reference={{
                          document_id: state.detail.document_id,
                          version_id: state.detail.active_version_id,
                        }}
                      />
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      Tài liệu chưa có phiên bản INDEXED để xem trước nội dung.
                    </p>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}

export function HrDocumentsView({ apiBaseUrl }: { apiBaseUrl: string | null }) {
  return (
    <section aria-labelledby="hr-documents-title" className="mx-auto w-full max-w-6xl">
      {!apiBaseUrl ? (
        <Card>
          <CardHeader>
            <CardTitle id="hr-documents-title">HR Documents — Chưa cấu hình API</CardTitle>
            <CardDescription>
              Cần thiết lập biến môi trường NEXT_PUBLIC_API_BASE_URL để liệt kê, xem trước và tải lên tài liệu vào RAG Knowledge Base.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <ConfiguredHrDocuments apiBaseUrl={apiBaseUrl} />
      )}
    </section>
  )
}
