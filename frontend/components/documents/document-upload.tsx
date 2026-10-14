"use client"

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react"
import { LoaderCircle, Upload } from "lucide-react"
import { DocumentStatusBadge } from "@/components/documents/document-status-badge"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { createApiClient } from "@/lib/api/client"
import { uploadDocument } from "@/lib/api/documents"
import { UploadController, type UploadState } from "@/lib/documents/upload-controller"
import { DOCUMENT_UPLOAD_ACCEPT } from "@/lib/documents/upload-validation"
import type { DocumentIndexInfo } from "@/types/document"

export function UploadFeedback({ state }: { state: UploadState }) {
  if (state.phase === "submitting") return <p role="status" className="flex items-start gap-2 text-sm text-muted-foreground">
    <LoaderCircle className="size-4 shrink-0 animate-spin" aria-hidden="true" />
    Đang gửi file và chờ xử lý. Chưa có kết quả xác nhận từ dịch vụ.
  </p>
  if (state.error) return <p role="alert" className="text-sm text-destructive">{state.error}</p>
  if (state.result) return <div role="status" className="space-y-2 text-sm">
    <p>Đã nhận phản hồi upload cho {state.result.file_name}.</p>
    {state.result.status ? <DocumentStatusBadge status={state.result.status} /> : <p>Phản hồi chưa cung cấp trạng thái tài liệu.</p>}
    {state.result.status === "INDEXED" && state.result.activated
      ? <p>Phiên bản đã được index và kích hoạt theo phản hồi dịch vụ.</p>
      : <p>Kiểm tra tài liệu trong danh sách để xem trạng thái và phiên bản hoạt động.</p>}
    <p className="break-all text-xs text-muted-foreground">Document: {state.result.document_id}<br />Version: {state.result.version_id}</p>
  </div>
  return null
}

function ConfiguredUpload({ apiBaseUrl, onUploaded, onRefresh }: {
  apiBaseUrl: string
  onUploaded: (result: DocumentIndexInfo) => void | Promise<void>
  onRefresh: () => void | Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const mounted = useRef(false)
  const controller = useMemo(() => {
    const api = createApiClient({ baseUrl: apiBaseUrl })
    return new UploadController({ upload: (file, signal) => uploadDocument(api, file, signal) })
  }, [apiBaseUrl])
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot)
  const submitting = state.phase === "submitting"
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; controller.dispose() }
  }, [controller])
  async function submit() {
    const result = await controller.submit()
    if (result && mounted.current) await onUploaded(result)
  }
  return <Dialog open={open} onOpenChange={next => { if (!submitting) setOpen(next) }}>
    <DialogTrigger render={<Button type="button" />}><Upload aria-hidden="true" />Thêm tài liệu</DialogTrigger>
    <DialogContent>
      <DialogHeader>
        <DialogTitle>Thêm tài liệu</DialogTitle>
        <DialogDescription>Chọn PDF, Markdown, TXT hoặc XLSX. Chờ dịch vụ xử lý và xác nhận kết quả trước khi gửi thêm.</DialogDescription>
      </DialogHeader>
      <form className="space-y-4" onSubmit={event => { event.preventDefault(); void submit() }} aria-busy={submitting}>
        <div className="space-y-2">
          <label htmlFor="document-upload-file" className="text-sm font-medium">File tài liệu</label>
          <Input id="document-upload-file" type="file" accept={DOCUMENT_UPLOAD_ACCEPT} disabled={submitting}
            aria-describedby="document-upload-help" onChange={event => controller.choose(event.target.files?.[0] ?? null)} />
          <p id="document-upload-help" className="text-xs text-muted-foreground">File phải không rỗng. Dịch vụ chưa công bố giới hạn dung lượng tối đa. Không có phần trăm tiến trình xử lý.</p>
          {state.file && <p className="break-words text-xs text-muted-foreground">{state.file.name} · {state.file.size.toLocaleString("vi-VN")} bytes</p>}
        </div>
        <UploadFeedback state={state} />
        <DialogFooter>
          {submitting && <Button type="button" variant="outline" onClick={() => controller.dispose()}>Dừng chờ phản hồi</Button>}
          <Button type="button" variant="outline" disabled={submitting} onClick={() => setOpen(false)}>Đóng</Button>
          {(state.phase === "uncertain" || state.phase === "error" || state.phase === "received") &&
            <Button type="button" variant="outline" onClick={() => void onRefresh()}>Làm mới danh sách</Button>}
          <Button type="submit" disabled={state.phase !== "ready"}>Tải lên</Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
}

export function DocumentUpload({ apiBaseUrl, onUploaded, onRefresh }: {
  apiBaseUrl: string | null
  onUploaded: (result: DocumentIndexInfo) => void | Promise<void>
  onRefresh: () => void | Promise<void>
}) {
  if (!apiBaseUrl) return <Button disabled><Upload aria-hidden="true" />Thêm tài liệu</Button>
  return <ConfiguredUpload key={apiBaseUrl} apiBaseUrl={apiBaseUrl} onUploaded={onUploaded} onRefresh={onRefresh} />
}
