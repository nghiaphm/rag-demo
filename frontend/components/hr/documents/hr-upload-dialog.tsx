"use client"

import { Info } from "lucide-react"

import { DocumentUpload } from "@/components/documents/document-upload"
import type { DocumentIndexInfo } from "@/types/document"

export function HrUploadDialog({
  apiBaseUrl,
  onUploaded,
  onRefresh,
}: {
  apiBaseUrl: string | null
  onUploaded: (result: DocumentIndexInfo) => void | Promise<void>
  onRefresh: () => void | Promise<void>
}) {
  return (
    <div className="flex flex-col items-start gap-2 sm:items-end">
      <DocumentUpload
        apiBaseUrl={apiBaseUrl}
        onUploaded={onUploaded}
        onRefresh={onRefresh}
      />
      <p className="flex max-w-md items-start gap-1.5 text-xs leading-5 text-muted-foreground sm:text-right">
        <Info className="mt-0.5 size-3.5 shrink-0 text-primary" aria-hidden="true" />
        <span>
          Tài liệu upload đi thẳng vào RAG Knowledge Base dùng chung với /documents. Đặt tên có từ khóa{" "}
          <code>chinh-sach</code>, <code>quy-dinh</code> hoặc <code>quy-trinh</code> để tự động phân nhóm hiển thị.
        </span>
      </p>
    </div>
  )
}
