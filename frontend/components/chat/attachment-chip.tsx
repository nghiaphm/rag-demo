"use client"

import { useRef, useState, useSyncExternalStore } from "react"
import { FileText, LoaderCircle, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { ChatAttachment } from "@/hooks/use-chat-attachments"
import { validateUploadFile } from "@/lib/documents/upload-validation"
import { DocumentPreview } from "@/components/chat/document-preview"
import { Sheet, SheetClose, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet"

export function AttachmentChip({ attachment, onRemove }: { attachment: ChatAttachment; onRemove: () => void }) {
  const { controller, file } = attachment
  const [open, setOpen] = useState(false)
  const closeButton = useRef<HTMLButtonElement>(null)
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot)
  const uploading = state.phase === "submitting"
  const ready = state.result?.status === "INDEXED" && state.result.activated
  const failed = state.phase === "error" || state.phase === "uncertain" || (state.phase === "received" && !ready)
  const status = ready ? "Ready" : failed ? "Failed" : "Uploading"
  const error = state.error ?? (failed ? "Dịch vụ chưa xác nhận index và kích hoạt thành công. Kiểm tra danh sách tài liệu trước khi tải lại." : null)

  function upload() {
    controller.choose(file)
    void controller.submit()
  }

  return <Sheet open={open} onOpenChange={setOpen}><li className="min-w-0 max-w-full rounded-lg border bg-muted/40 p-2 text-xs" data-document-id={state.result?.document_id}>
    <div className="flex min-w-0 items-center gap-2">
      <SheetTrigger type="button" aria-label={`Xem trước ${file.name}`} className="flex min-w-0 flex-1 items-center gap-2 rounded text-left hover:text-primary focus-visible:outline-2 focus-visible:outline-ring">
      {uploading ? <LoaderCircle className="size-4 shrink-0 animate-spin" aria-hidden="true" /> : <FileText className="size-4 shrink-0" aria-hidden="true" />}
      <span className="min-w-0 flex-1 truncate" title={file.name}>{file.name}</span>
      </SheetTrigger>
      <span role="status" className="shrink-0">{status}</span>
      <Button type="button" variant="ghost" size="icon" className="size-8 shrink-0" aria-label={`Gỡ ${file.name}`} onClick={onRemove}>
        <X aria-hidden="true" />
      </Button>
    </div>
    {error && <p role="alert" className="mt-1 break-words text-destructive">{error}</p>}
    {failed && <Button type="button" variant="outline" size="sm" className="mt-1" disabled={!!validateUploadFile(file)}
      onClick={upload}>Thử lại</Button>}
  </li>
    <SheetContent side="right" showCloseButton={false} initialFocus={closeButton} className="w-full sm:max-w-xl">
      <SheetHeader className="pr-12">
        <SheetTitle className="break-words">{file.name}</SheetTitle>
        <SheetDescription>Bản xem trước từ file trên thiết bị. Nội dung này không xác nhận kết quả index hoặc phạm vi truy xuất của chat.</SheetDescription>
      </SheetHeader>
      <SheetClose render={<Button ref={closeButton} type="button" variant="ghost" size="icon" className="absolute top-3 right-3" aria-label="Đóng xem trước" />}><X aria-hidden="true" /></SheetClose>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">{open && <DocumentPreview file={file} />}</div>
    </SheetContent>
  </Sheet>
}
