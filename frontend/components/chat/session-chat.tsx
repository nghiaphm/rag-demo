"use client"

import Link from "next/link"
import { AlertCircle, LoaderCircle } from "lucide-react"

import { ChatPreview } from "@/components/chat/chat-preview"
import { Button } from "@/components/ui/button"
import { LoadingSkeleton } from "@/components/layout/loading-skeleton"
import { useSession, useSessionHistory } from "@/hooks/use-sessions"
import { isSessionId } from "@/lib/api/sessions"
import { historyMessageToViewMessage } from "@/lib/sessions/history"

function SessionState({
  title,
  description,
  loading = false,
  onRetry,
}: {
  title: string
  description: string
  loading?: boolean
  onRetry?: () => void
}) {
  return (
    <section aria-labelledby="session-state-title" className="mx-auto w-full max-w-3xl">
      <div
        role={loading ? "status" : "alert"}
        aria-busy={loading || undefined}
        className="rounded-xl border bg-background p-6 shadow-sm"
      >
        {loading ? (
          <LoaderCircle className="size-5 animate-spin text-muted-foreground" aria-hidden="true" />
        ) : (
          <AlertCircle className="size-5 text-destructive" aria-hidden="true" />
        )}
        <h1 id="session-state-title" className="mt-3 text-lg font-semibold">{title}</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p>
        {loading && <div className="mt-4"><LoadingSkeleton /></div>}
        {!loading && (
          <div className="mt-4 flex flex-wrap gap-2">
            {onRetry && (
              <Button type="button" variant="outline" onClick={onRetry}>Thử lại</Button>
            )}
            <Button nativeButton={false} role="link" render={<Link href="/chat" />}>Về trang Chat</Button>
          </div>
        )}
      </div>
    </section>
  )
}

function ConfiguredSessionChat({ apiBaseUrl, sessionId }: { apiBaseUrl: string; sessionId: string }) {
  const { status, session, error, reload } = useSession(apiBaseUrl, sessionId)

  if (status === "ready" && session) {
    return <SessionHistoryChat apiBaseUrl={apiBaseUrl} sessionId={session.session_id} />
  }
  if (status === "missing") {
    return (
      <SessionState
        title="Không tìm thấy phiên trò chuyện"
        description="Phiên này không tồn tại hoặc đã bị xóa. Hãy chọn một phiên khác trong thanh bên hoặc bắt đầu phiên mới."
      />
    )
  }
  if (status === "error") {
    return (
      <SessionState
        title="Không thể mở phiên trò chuyện"
        description={error ?? "Không thể xác minh phiên với API. Bạn có thể thử tải lại."}
        onRetry={() => void reload()}
      />
    )
  }
  return (
    <SessionState
      title="Đang mở phiên trò chuyện"
      description="Đang xác minh phiên với API…"
      loading
    />
  )
}

function SessionHistoryChat({ apiBaseUrl, sessionId }: { apiBaseUrl: string; sessionId: string }) {
  const { status, messages, error, reload } = useSessionHistory(apiBaseUrl, sessionId)

  if (status === "ready") {
    return (
      <ChatPreview
        apiBaseUrl={apiBaseUrl}
        initialSessionId={sessionId}
        initialMessages={messages.map(historyMessageToViewMessage)}
      />
    )
  }
  if (status === "error") {
    return (
      <SessionState
        title="Không thể tải lịch sử trò chuyện"
        description={error ?? "Lịch sử chưa được tải đầy đủ. Bạn có thể thử tải lại."}
        onRetry={() => void reload()}
      />
    )
  }
  return (
    <SessionState
      title="Đang tải lịch sử trò chuyện"
      description="Đang tải các message theo thứ tự từ API…"
      loading
    />
  )
}

export function SessionChat({ apiBaseUrl, sessionId }: { apiBaseUrl: string | null; sessionId: string }) {
  if (!isSessionId(sessionId)) {
    return (
      <SessionState
        title="Session ID không hợp lệ"
        description="Đường dẫn phiên trò chuyện không đúng định dạng. Bạn không cần nhập UUID thủ công; hãy chọn phiên từ thanh bên."
      />
    )
  }
  if (!apiBaseUrl) {
    return (
      <SessionState
        title="Chưa cấu hình API"
        description="Cần cấu hình NEXT_PUBLIC_API_BASE_URL trước khi mở phiên trò chuyện."
      />
    )
  }
  return <ConfiguredSessionChat key={`${apiBaseUrl}:${sessionId}`} apiBaseUrl={apiBaseUrl} sessionId={sessionId} />
}
