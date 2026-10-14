"use client"

import { useRouter } from "next/navigation"
import Link from "next/link"
import { useEffect, useRef, useState, useSyncExternalStore } from "react"
import { AlertCircle, MessageSquareText } from "lucide-react"

import { ChatComposer } from "@/components/chat/chat-composer"
import { ChatMessage } from "@/components/chat/chat-message"
import { Badge } from "@/components/ui/badge"
import { createChatStreamClient } from "@/lib/api/chat"
import { createApiClient } from "@/lib/api/client"
import { createSession, listSessionMessages } from "@/lib/api/sessions"
import { historyMessageToViewMessage, loadMessageHistory } from "@/lib/sessions/history"
import { ChatController, type ChatViewMessage } from "@/lib/chat/controller"

function EmptyChat() {
  return (
    <div className="flex min-h-72 flex-col items-center justify-center px-4 text-center">
      <span className="flex size-12 items-center justify-center rounded-2xl bg-muted">
        <MessageSquareText className="size-5 text-muted-foreground" aria-hidden="true" />
      </span>
      <h2 className="mt-4 text-base font-semibold">Bắt đầu một cuộc trò chuyện</h2>
      <p className="mt-2 max-w-sm text-sm leading-6 text-muted-foreground">
        Đặt câu hỏi về tài liệu của bạn. Một session sẽ được tạo trước lần gửi đầu tiên.
      </p>
    </div>
  )
}

function ChatWorkspace({
  apiBaseUrl,
  initialSessionId,
  initialMessages,
}: {
  apiBaseUrl: string
  initialSessionId: string | null
  initialMessages: readonly ChatViewMessage[]
}) {
  const router = useRouter()
  const mounted = useRef(false)
  const [question, setQuestion] = useState("")
  const [controller] = useState(() => {
    const api = createApiClient({ baseUrl: apiBaseUrl })
    const streamClient = createChatStreamClient({ baseUrl: apiBaseUrl })
    return new ChatController({
      createSession: (signal) => createSession(api, {}, signal),
      stream: (payload, options) => streamClient.stream(payload, options),
      loadHistory: async (id, signal) => (await loadMessageHistory(id, {
        list: (sessionId, query, pageSignal) => listSessionMessages(api, sessionId, query, pageSignal),
      }, signal)).map(historyMessageToViewMessage),
    }, initialSessionId, initialMessages)
  })
  const state = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot
  )
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      controller.dispose()
    }
  }, [controller])

  function submit() {
    if (!question.trim()) return
    const hadSession = controller.getSnapshot().sessionId !== null
    void controller.submit(question).then((accepted) => {
      const sessionId = controller.getSnapshot().sessionId
      if (mounted.current && accepted && !hadSession && sessionId && !controller.getSnapshot().persistenceError) {
        router.replace(`/chat/${encodeURIComponent(sessionId)}`)
      }
    })
    setQuestion("")
  }

  return (
    <section aria-labelledby="chat-title" className="mx-auto flex w-full max-w-5xl flex-1 flex-col">
      <div className="mb-5">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium text-muted-foreground">Không gian hỏi đáp</p>
          <Badge variant="outline">{state.sessionId ? "Session bền vững" : "Session mới"}</Badge>
        </div>
        <h1 id="chat-title" className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          Chat
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
          Câu trả lời được cập nhật trực tiếp khi backend phát các SSE delta.
        </p>
      </div>

      <div className="flex min-h-[34rem] flex-1 flex-col overflow-hidden rounded-xl border bg-background shadow-sm">
        <div
          className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4 sm:p-6"
          aria-live="polite"
          aria-busy={state.isGenerating}
        >
          {state.messages.length === 0 ? (
            <EmptyChat />
          ) : (
            <div className="space-y-5" aria-label="Hội thoại hiện tại">
              {state.messages.map((message) => (
                <ChatMessage key={message.key} message={message} />
              ))}
            </div>
          )}
        </div>
        <ChatComposer
          value={question}
          onChange={setQuestion}
          onSubmit={submit}
          onStop={() => controller.stop()}
          disabled={state.isGenerating}
          isGenerating={state.isGenerating && !state.isVerifyingHistory}
        />
        {state.isVerifyingHistory && (
          <p role="status" className="border-t p-4 text-sm text-muted-foreground">Đang xác minh lịch sử đã lưu…</p>
        )}
        {state.persistenceError && (
          <div role="alert" className="border-t p-4 text-sm text-destructive">
            <p>{state.persistenceError}</p>
            {state.sessionId && (
              <Link className="mt-2 inline-block underline" href={`/chat/${encodeURIComponent(state.sessionId)}`}>
                Mở lịch sử đã lưu
              </Link>
            )}
          </div>
        )}
      </div>
    </section>
  )
}

export function ChatPreview({
  apiBaseUrl,
  initialSessionId = null,
  initialMessages = [],
}: {
  apiBaseUrl: string | null
  initialSessionId?: string | null
  initialMessages?: readonly ChatViewMessage[]
}) {
  if (!apiBaseUrl) {
    return (
      <section aria-labelledby="chat-title" className="mx-auto w-full max-w-5xl">
        <h1 id="chat-title" className="text-2xl font-semibold tracking-tight sm:text-3xl">Chat</h1>
        <div role="alert" className="mt-5 rounded-xl border border-destructive/30 bg-destructive/5 p-5">
          <AlertCircle className="size-5 text-destructive" aria-hidden="true" />
          <h2 className="mt-3 font-semibold">Chưa cấu hình API</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Cần cấu hình NEXT_PUBLIC_API_BASE_URL để tạo session và mở luồng chat.
          </p>
        </div>
      </section>
    )
  }
  return (
    <ChatWorkspace
      key={`${apiBaseUrl}:${initialSessionId ?? "new"}`}
      apiBaseUrl={apiBaseUrl}
      initialSessionId={initialSessionId}
      initialMessages={initialMessages}
    />
  )
}
