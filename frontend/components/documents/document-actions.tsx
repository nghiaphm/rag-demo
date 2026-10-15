"use client"

import { useEffect, useMemo, useState, useSyncExternalStore } from "react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { createApiClient } from "@/lib/api/client"
import { deleteDocument, getDocument, reindexDocument, updateDocument } from "@/lib/api/documents"
import { DocumentActionsController, type ActionState, type DocumentAction } from "@/lib/documents/actions-controller"
import { DOCUMENT_UPLOAD_ACCEPT, validateUploadFile } from "@/lib/documents/upload-validation"
import type { DocumentDetail } from "@/types/document"
import { DocumentStatusBadge } from "@/components/documents/document-status-badge"

const titles: Record<DocumentAction, string> = { version: "Tạo phiên bản mới", reindex: "Xác nhận re-index", delete: "Xác nhận soft-delete / cleanup" }

export function DocumentActionFeedback({ state }: { state: ActionState }) {
  const pending = { checking: "Đang kiểm tra trạng thái mới nhất…", submitting: "Đang chờ dịch vụ thực hiện thao tác…", reconciling: "Đang tải lại trạng thái đã lưu…" }
  return <div className="space-y-2 text-sm">
    {state.phase in pending && <p role="status">{pending[state.phase as keyof typeof pending]}</p>}
    {state.message && <p role="alert" className="text-destructive">{state.message}</p>}
    {state.refreshError && <p role="alert">Chưa tải lại được chi tiết. Dữ liệu bên dưới là lần tải trước; hãy Làm mới danh sách để kiểm tra.</p>}
    {state.receipt?.action === "delete" ? <div role="status" className="space-y-2">
      <p>Tài liệu đã được unpublish theo phản hồi dịch vụ.</p>
      <p>{state.receipt.result.response.cleanup_pending ? "Cleanup vector còn pending (HTTP 202). Bạn có thể xác nhận DELETE lại để thử dọn dữ liệu." : "Cleanup vector đã hoàn tất (HTTP 200)."}</p>
      <p>Raw files được giữ theo chính sách soft-delete: {state.receipt.result.response.retained_files} file. Lịch sử vẫn được giữ.</p>
    </div> : state.receipt && <div role="status" className="space-y-2">
      {state.receipt.result.status && <DocumentStatusBadge status={state.receipt.result.status} />}
      <p>{state.receipt.result.activated && state.receipt.result.status === "INDEXED"
        ? "Dịch vụ đã xác nhận phiên bản mới INDEXED và được kích hoạt."
        : "Đã nhận phản hồi; xem active version và trạng thái đã lưu để xác minh."}</p>
      <p className="break-all text-xs">Version: {state.receipt.result.version_id}</p>
    </div>}
  </div>
}

function ConfiguredActions({ document, apiBaseUrl, reconcile }: {
  document: DocumentDetail; apiBaseUrl: string; reconcile: (document: DocumentDetail) => void
}) {
  const [proposal, setProposal] = useState<{ action: DocumentAction; snapshot: DocumentDetail } | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const controller = useMemo(() => {
    const api = createApiClient({ baseUrl: apiBaseUrl })
    return new DocumentActionsController({ get: (id, signal) => getDocument(api, id, signal),
      update: (id, file, signal) => updateDocument(api, id, file, signal),
      reindex: (id, signal) => reindexDocument(api, id, signal),
      remove: (id, signal) => deleteDocument(api, id, signal), reconcile })
  }, [apiBaseUrl, reconcile])
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot)
  useEffect(() => () => controller.dispose(), [controller])
  const busy = ["checking", "submitting", "reconciling"].includes(state.phase)
  function propose(action: DocumentAction) {
    if (busy) return
    controller.reset()
    setFile(null)
    setProposal({ action, snapshot: document })
  }
  const protectedDocument = document.status === "DELETED" || document.status === "PROCESSING"
  return <Dialog open={proposal !== null} onOpenChange={next => { if (!next && !busy) setProposal(null) }}>
    <div className="flex flex-wrap gap-2">
      <DialogTrigger render={<Button type="button" variant="outline" size="sm" />} disabled={busy || protectedDocument} onClick={() => propose("version")}>Phiên bản mới</DialogTrigger>
      <DialogTrigger render={<Button type="button" variant="outline" size="sm" />} disabled={busy || protectedDocument || !document.active_version_id} onClick={() => propose("reindex")}>Re-index</DialogTrigger>
      <DialogTrigger render={<Button type="button" variant="destructive" size="sm" />} disabled={busy || (document.status === "DELETED" && !document.cleanup_pending)} onClick={() => propose("delete")}>
        {document.status === "DELETED" ? document.cleanup_pending ? "Thử cleanup lại" : "Đã soft-delete" : "Xóa tài liệu"}
      </DialogTrigger>
    </div>
    <DialogContent showCloseButton={false} className="max-h-[calc(100dvh-2rem)] overflow-y-auto">
      <DialogHeader>
        <DialogTitle>{proposal ? titles[proposal.action] : "Thao tác tài liệu"}</DialogTitle>
        <DialogDescription>
          {proposal?.action === "delete" ? "Thao tác unpublish tài liệu, dọn vector và giữ raw files/lịch sử. Nếu cleanup còn pending, DELETE lại chỉ thử dọn dữ liệu; không phải xóa raw files."
            : proposal?.action === "reindex" ? "Tạo phiên bản mới từ raw file của active version. Phiên bản cũ chỉ được thay khi ingestion mới thành công."
              : "Tải file mới để tạo immutable version. Ingestion thất bại không kích hoạt phiên bản mới."}
        </DialogDescription>
      </DialogHeader>
      <p className="break-words text-sm font-medium">{proposal?.snapshot.file_name}</p>
      <p className="break-all text-xs text-muted-foreground">Document: {proposal?.snapshot.document_id}<br />Active version: {proposal?.snapshot.active_version_id ?? "Chưa có"}</p>
      {proposal?.action === "version" && <div className="space-y-2">
        <label htmlFor="document-version-file" className="text-sm font-medium">File phiên bản mới</label>
        <Input id="document-version-file" type="file" accept={DOCUMENT_UPLOAD_ACCEPT} disabled={busy}
          onChange={event => { setFile(event.target.files?.[0] ?? null); controller.reset() }} />
        <p className="text-xs text-muted-foreground">File không rỗng; chưa có giới hạn dung lượng tối đa do dịch vụ công bố.</p>
        {file && validateUploadFile(file) && <p role="alert" className="text-sm text-destructive">{validateUploadFile(file)}</p>}
      </div>}
      <DocumentActionFeedback state={state} />
      <DialogFooter>
        {busy && <Button type="button" variant="outline" onClick={() => controller.dispose()}>Dừng chờ phản hồi</Button>}
        <Button type="button" variant="outline" disabled={busy} onClick={() => setProposal(null)}>Đóng</Button>
        <Button type="button" variant={proposal?.action === "delete" ? "destructive" : "default"}
          disabled={busy || state.phase !== "idle" || !proposal || (proposal.action === "version" && !!validateUploadFile(file))}
          onClick={() => proposal && void controller.run(proposal.action, proposal.snapshot, true, file ?? undefined)}>
          Xác nhận thao tác
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
}

export function DocumentActions({ document, apiBaseUrl, reconcile }: {
  document: DocumentDetail; apiBaseUrl: string | null; reconcile?: (document: DocumentDetail) => void
}) {
  if (!apiBaseUrl || !reconcile) return <div className="flex flex-wrap gap-2">
    <Button size="sm" disabled>Phiên bản mới</Button><Button size="sm" disabled>Re-index</Button><Button size="sm" disabled>Xóa tài liệu</Button>
  </div>
  return <ConfiguredActions key={`${apiBaseUrl}:${document.document_id}`} document={document} apiBaseUrl={apiBaseUrl} reconcile={reconcile} />
}
