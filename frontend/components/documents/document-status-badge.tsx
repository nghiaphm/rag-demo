import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { DocumentStatus } from "@/types/document"

const statusLabels: Record<DocumentStatus, string> = {
  UPLOADED: "Đã tải lên",
  PROCESSING: "Đang xử lý",
  INDEXED: "Đã lập chỉ mục",
  FAILED: "Thất bại",
  DELETED: "Đã xóa",
}

const statusClasses: Record<DocumentStatus, string> = {
  UPLOADED: "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-300",
  PROCESSING:
    "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300",
  INDEXED:
    "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300",
  FAILED: "border-destructive/30 bg-destructive/10 text-destructive",
  DELETED: "border-border bg-muted text-muted-foreground",
}

export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  return (
    <Badge variant="outline" className={cn("shrink-0", statusClasses[status])}>
      {statusLabels[status]}
    </Badge>
  )
}
