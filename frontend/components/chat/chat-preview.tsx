"use client"

import { useRouter } from "next/navigation"
import { useEffect, useId, useRef, useState, useSyncExternalStore } from "react"
import { AlertCircle, MessageSquareText } from "lucide-react"

import { ChatComposer } from "@/components/chat/chat-composer"
import { ChatMessage } from "@/components/chat/chat-message"
import { ChatRecovery } from "@/components/chat/chat-recovery"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ChatScrollController } from "@/lib/chat/scroll"
import { createChatServices } from "@/lib/chat/services"
import { canonicalChatPath, isHistoricalNonterminal } from "@/lib/chat/recovery"
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
  const composerId = useId()
  const mounted = useRef(false)
  const [question, setQuestion] = useState("")
  const viewport = useRef<HTMLDivElement>(null)
  const content = useRef<HTMLDivElement>(null)
  const [scroll] = useState(() => new ChatScrollController())
  const unread = useSyncExternalStore(scroll.subscribe, scroll.getSnapshot, scroll.getSnapshot)
  useEffect(() => {
    if (!viewport.current || !content.current) return
    const detach = scroll.attach(viewport.current)
    const observer = new ResizeObserver(scroll.contentChanged)
    observer.observe(content.current)
    observer.observe(viewport.current)
    return () => { observer.disconnect(); detach() }
  }, [scroll])
  const [controller] = useState(() => new ChatController(createChatServices(apiBaseUrl), initialSessionId, initialMessages))
  const state = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot
  )
  useEffect(() => { scroll.contentChanged() }, [scroll, state.messages])
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      controller.dispose()
    }
  }, [controller])

  function submit() {
    if (!question.trim()) return
    void controller.submit(question).then((accepted) => {
      const path = canonicalChatPath(initialSessionId, controller.getSnapshot())
      if (mounted.current && accepted && path) router.replace(path)
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

      <ChatRecovery state={state} initialSessionId={initialSessionId} />
      <div className="flex h-[70dvh] min-h-80 max-h-[56rem] flex-col overflow-hidden rounded-xl border bg-background shadow-sm">
        <div
          ref={viewport}
          onScroll={scroll.onScroll}
          tabIndex={0}
          role="region"
          aria-label="Lịch sử trò chuyện"
          className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4 sm:p-6"
          aria-busy={state.isGenerating}
        >
          <div ref={content}>
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
        </div>
        {unread && <div className="border-t px-4 py-2"><Button type="button" variant="outline" size="sm" onClick={scroll.jump}>Nội dung mới — Về cuối</Button></div>}
        <p role="status" className="sr-only">{state.isGenerating ? "Đang xử lý câu hỏi" : state.messages.some(isHistoricalNonterminal) ? "Không có luồng trực tiếp cho tin nhắn chưa hoàn tất trong lịch sử." : state.messages.length ? "Đã kết thúc xử lý câu hỏi. Kiểm tra trạng thái câu trả lời." : "Sẵn sàng đặt câu hỏi"}</p>
        <ChatComposer
          inputId={composerId}
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
        {!state.isGenerating && state.sessionId && state.messages.some(message => message.error) && (
          <p className="border-t p-4 text-sm text-muted-foreground">
            <a className="underline focus-visible:outline-2 focus-visible:outline-ring" href={`/chat/${encodeURIComponent(state.sessionId)}`}>
              Tải lại phiên để kiểm tra lịch sử trước khi gửi lại
            </a>
          </p>
        )}
        {state.persistenceError && (
          <div role="alert" className="border-t p-4 text-sm text-destructive">
            <p>{state.persistenceError}</p>
            {state.sessionId && (
              <a className="mt-2 inline-block underline" href={`/chat/${encodeURIComponent(state.sessionId)}`}>
                Mở lịch sử đã lưu
              </a>
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
