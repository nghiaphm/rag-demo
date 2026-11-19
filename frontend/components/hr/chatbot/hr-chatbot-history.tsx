"use client"

import { useRef, useState } from "react"
import { AlertCircle, LoaderCircle, MessageSquare, Plus, RotateCcw } from "lucide-react"

import {
  SessionActionDialog,
  SessionActionsMenu,
  type SessionProposal,
} from "@/components/layout/session-actions"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { useSessions } from "@/hooks/use-sessions"
import { cn } from "@/lib/utils"
import type { SessionResponse } from "@/types/sessions"

const dateFormatter = new Intl.DateTimeFormat("vi-VN", {
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
})

function formatShortDate(value: string): string {
  const parsed = Date.parse(value)
  if (!Number.isFinite(parsed)) return ""
  return dateFormatter.format(new Date(parsed))
}

export function HrChatbotHistory({
  apiBaseUrl,
  activeSessionId,
  disabled = false,
  onNewChat,
  onSelectSession,
  onActiveSessionDeleted,
}: {
  apiBaseUrl: string
  activeSessionId: string | null
  disabled?: boolean
  onNewChat: () => void
  onSelectSession: (session: SessionResponse) => void
  onActiveSessionDeleted: () => void
}) {
  const {
    sessions,
    total,
    status,
    error,
    reload,
    loadMore,
    rename,
    remove,
    isMutating,
    mutationError,
  } = useSessions(apiBaseUrl, "hr")
  const [proposal, setProposal] = useState<SessionProposal | null>(null)
  const fallbackFocus = useRef<HTMLButtonElement>(null)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-between gap-2 border-b bg-muted/25 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <h3 className="text-xs font-semibold text-foreground">Lịch sử hội thoại HR</h3>
          <Badge variant="secondary" className="h-5 px-1.5 text-[11px] tabular-nums">
            {total}
          </Badge>
        </div>
        <div className="flex items-center gap-1">
          <Button
            ref={fallbackFocus}
            type="button"
            size="sm"
            variant="outline"
            className="h-7 gap-1 px-2 text-xs"
            disabled={disabled || isMutating}
            onClick={onNewChat}
          >
            <Plus className="size-3.5" aria-hidden="true" />
            <span>Cuộc trò chuyện mới</span>
          </Button>
          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            className="size-7"
            aria-label="Làm mới lịch sử hội thoại HR"
            disabled={status === "loading" || isMutating}
            onClick={() => void reload()}
          >
            <RotateCcw
              className={cn("size-3.5", status === "loading" && "animate-spin")}
              aria-hidden="true"
            />
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {status === "loading" && sessions.length === 0 ? (
          <div className="flex items-center justify-center gap-2 py-10 text-xs text-muted-foreground">
            <LoaderCircle className="size-4 animate-spin text-primary" aria-hidden="true" />
            <span>Đang tải lịch sử hội thoại HR…</span>
          </div>
        ) : status === "error" && sessions.length === 0 ? (
          <div className="space-y-3 rounded-xl border bg-card p-4 text-xs">
            <p className="flex items-center gap-2 text-destructive">
              <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
              <span>{error ?? "Không tải được danh sách phiên HR."}</span>
            </p>
            <Button type="button" size="sm" variant="outline" onClick={() => void reload()}>
              Thử lại
            </Button>
          </div>
        ) : sessions.length === 0 ? (
          <div className="space-y-3 rounded-xl border border-dashed bg-muted/20 p-6 text-center">
            <p className="text-sm font-medium text-foreground">Chưa có lịch sử hội thoại HR</p>
            <p className="text-xs leading-5 text-muted-foreground">
              Các cuộc trò chuyện tạo từ Trợ lý HR được lưu tách biệt với lịch sử RAG Workspace.
            </p>
            <Button type="button" size="sm" onClick={onNewChat}>
              Bắt đầu trò chuyện mới
            </Button>
          </div>
        ) : (
          <ul aria-label="Danh sách phiên hội thoại HR" className="space-y-1.5">
            {sessions.map((session) => {
              const isActive = session.session_id === activeSessionId
              return (
                <li
                  key={session.session_id}
                  className={cn(
                    "flex items-center gap-1 rounded-xl border bg-card px-2 py-1.5 transition-colors",
                    isActive
                      ? "border-primary/40 bg-accent/55"
                      : "border-border hover:bg-muted/40",
                  )}
                >
                  <button
                    type="button"
                    disabled={disabled || isMutating}
                    onClick={() => onSelectSession(session)}
                    aria-current={isActive ? "true" : undefined}
                    className="flex min-w-0 flex-1 items-start gap-2.5 rounded-lg px-2 py-1 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <MessageSquare
                      className={cn(
                        "mt-0.5 size-4 shrink-0",
                        isActive ? "text-primary" : "text-muted-foreground",
                      )}
                      aria-hidden="true"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs font-medium text-foreground">
                        {session.title}
                      </span>
                      <span className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
                        <span>{formatShortDate(session.updated_at)}</span>
                        {isActive && (
                          <span className="font-medium text-primary">Đang mở</span>
                        )}
                      </span>
                    </span>
                  </button>
                  <SessionActionsMenu
                    session={session}
                    disabled={disabled || isMutating}
                    onPropose={setProposal}
                  />
                </li>
              )
            })}
          </ul>
        )}

        {sessions.length < total && (
          <div className="pt-3">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full text-xs"
              disabled={status === "loading" || isMutating}
              onClick={() => void loadMore()}
            >
              Tải thêm ({sessions.length}/{total})
            </Button>
          </div>
        )}
      </div>

      {proposal && (
        <SessionActionDialog
          key={`${proposal.action}:${proposal.session.session_id}`}
          proposal={proposal}
          busy={isMutating}
          error={mutationError}
          fallbackFocus={fallbackFocus}
          rename={rename}
          remove={remove}
          onDeleted={(receipt) => {
            if (receipt.session_id === activeSessionId) {
              onActiveSessionDeleted()
            }
          }}
          onClose={() => setProposal(null)}
          onReview={() => void reload()}
        />
      )}
    </div>
  )
}
