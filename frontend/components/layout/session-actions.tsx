"use client"

import { useEffect, useRef, useState } from "react"
import { MoreHorizontal } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { validateSessionTitle } from "@/lib/api/sessions"
import type { DeleteSessionResponse, SessionResponse } from "@/types/sessions"

export type SessionProposal = { session: SessionResponse; action: "rename" | "delete"; opener: HTMLButtonElement | null }

export function SessionActionsMenu({ session, disabled, onPropose }: {
  session: SessionResponse; disabled: boolean; onPropose: (proposal: SessionProposal) => void
}) {
  const trigger = useRef<HTMLButtonElement>(null)
  return <DropdownMenu>
    <DropdownMenuTrigger render={<Button ref={trigger} type="button" variant="ghost" size="icon-sm"
      aria-label={`Thao tác với phiên ${session.title}`} disabled={disabled} className="shrink-0" />}>
      <MoreHorizontal aria-hidden="true" />
    </DropdownMenuTrigger>
    <DropdownMenuContent>
      <DropdownMenuItem onClick={() => onPropose({ session, action: "rename", opener: trigger.current })}>Đổi tên</DropdownMenuItem>
      <DropdownMenuItem variant="destructive" onClick={() => onPropose({ session, action: "delete", opener: trigger.current })}>Xóa phiên</DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
}

export function SessionActionDialog({ proposal, busy, error, fallbackFocus, rename, remove, onDeleted, onClose, onReview }: {
  proposal: SessionProposal; busy: boolean; error: string | null; fallbackFocus: React.RefObject<HTMLButtonElement | null>
  rename: (id: string, title: string) => Promise<SessionResponse | null>
  remove: (id: string, confirmed: boolean) => Promise<DeleteSessionResponse | null>
  onDeleted: (receipt: DeleteSessionResponse) => void; onClose: () => void; onReview: () => void
}) {
  const [title, setTitle] = useState(proposal.session.title)
  const [attempted, setAttempted] = useState(false)
  const mounted = useRef(false)
  const initialFocus = useRef<HTMLInputElement | HTMLButtonElement>(null)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const validation = proposal.action === "rename" ? validateSessionTitle(title) : null
  async function submit() {
    if (busy || attempted || validation) return
    setAttempted(true)
    if (proposal.action === "rename") {
      if (await rename(proposal.session.session_id, title) && mounted.current) onClose()
    } else {
      const receipt = await remove(proposal.session.session_id, true)
      if (receipt && mounted.current) { onDeleted(receipt); onClose() }
    }
  }
  return <Dialog open onOpenChange={open => { if (!open && !busy) onClose() }}>
    <DialogContent showCloseButton={false} initialFocus={initialFocus}
      finalFocus={() => proposal.opener?.isConnected ? proposal.opener
        : fallbackFocus.current && !fallbackFocus.current.disabled ? fallbackFocus.current : document.getElementById("main-content")}
      className="max-h-[calc(100dvh-2rem)] overflow-y-auto">
      <DialogHeader>
        <DialogTitle>{proposal.action === "rename" ? "Đổi tên phiên trò chuyện" : "Xác nhận xóa phiên trò chuyện"}</DialogTitle>
        <DialogDescription>{proposal.action === "rename" ? "Đặt tên để dễ tìm lại cuộc trò chuyện."
          : "Toàn bộ tin nhắn của phiên sẽ bị xóa và không thể hoàn tác; hệ thống chỉ giữ dấu ghi nhận phiên đã xóa. Không thể xóa khi câu trả lời đang được tạo. Hãy dừng tạo và kiểm tra lại trước khi xác nhận."}</DialogDescription>
      </DialogHeader>
      <p className="break-words text-sm">{proposal.session.title}</p>
      <form onSubmit={event => { event.preventDefault(); void submit() }} aria-busy={busy} className="space-y-4">
        {proposal.action === "rename" && <div className="space-y-2">
          <label htmlFor="session-title" className="text-sm font-medium">Tên phiên</label>
          <Input ref={initialFocus as React.RefObject<HTMLInputElement | null>} id="session-title" value={title} disabled={busy}
            aria-describedby="session-title-help" aria-invalid={!!validation}
            onChange={event => { setTitle(event.target.value); setAttempted(false) }} />
          <p id="session-title-help" className="text-xs text-muted-foreground">Tối đa 200 ký tự; tên không được rỗng.</p>
          {validation && <p role="alert" className="text-sm text-destructive">{validation}</p>}
        </div>}
        {busy && <p role="status" className="text-sm">Đang chờ xác nhận từ dịch vụ…</p>}
        {attempted && error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <DialogFooter>
          <Button ref={proposal.action === "delete" ? initialFocus as React.RefObject<HTMLButtonElement | null> : undefined}
            type="button" variant="outline" disabled={busy} onClick={onClose}>Hủy</Button>
          {attempted && error && <Button type="button" variant="outline" disabled={busy} onClick={onReview}>Làm mới danh sách</Button>}
          <Button type="submit" variant={proposal.action === "delete" ? "destructive" : "default"}
            disabled={busy || attempted || !!validation}>{proposal.action === "rename" ? "Lưu tên" : "Xác nhận xóa"}</Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
}
