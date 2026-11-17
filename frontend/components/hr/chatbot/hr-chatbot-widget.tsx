"use client"

import Link from "next/link"
import { useEffect, useId, useRef, useState, useSyncExternalStore } from "react"
import { Bot, ExternalLink, MessageSquareText, RotateCcw } from "lucide-react"

import { ChatComposer } from "@/components/chat/chat-composer"
import { ChatMessage } from "@/components/chat/chat-message"
import { useHrChatbot } from "@/components/hr/layout/hr-chatbot-provider"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { HR_PROMPT_TEMPLATES } from "@/fixtures/hr-guide"
import { ChatController } from "@/lib/chat/controller"
import { ChatScrollController } from "@/lib/chat/scroll"
import { createChatServices } from "@/lib/chat/services"

function ConfiguredWidgetChat({ apiBaseUrl }: { apiBaseUrl: string }) {
  const inputId = useId()
  const {
    activeSessionId,
    draftPrompt,
    pageContext,
    setActiveSessionId,
    clearDraftPrompt,
  } = useHrChatbot()

  const [question, setQuestion] = useState("")
  const [controller, setController] = useState(
    () => new ChatController(createChatServices(apiBaseUrl), activeSessionId)
  )
  const state = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot
  )
  const [scroll] = useState(() => new ChatScrollController())
  const unread = useSyncExternalStore(
    scroll.subscribe,
    scroll.getSnapshot,
    scroll.getSnapshot
  )
  const viewport = useRef<HTMLDivElement>(null)
  const content = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (state.sessionId && state.sessionId !== activeSessionId) {
      setActiveSessionId(state.sessionId)
    }
  }, [state.sessionId, activeSessionId, setActiveSessionId])

  useEffect(() => {
    if (!viewport.current || !content.current) return
    const detach = scroll.attach(viewport.current)
    const observer = new ResizeObserver(scroll.contentChanged)
    observer.observe(content.current)
    observer.observe(viewport.current)
    return () => {
      observer.disconnect()
      detach()
    }
  }, [scroll, controller])

  useEffect(() => {
    scroll.contentChanged()
  }, [scroll, state.messages])

  useEffect(() => () => controller.dispose(), [controller])

  const effectiveQuestion = draftPrompt ?? question

  async function handleSubmit(): Promise<boolean> {
    const trimmed = effectiveQuestion.trim()
    if (!trimmed || controller.getSnapshot().isGenerating) return false
    clearDraftPrompt()
    setQuestion("")
    return controller.submit(trimmed, [])
  }

  function handleResetSession() {
    if (state.isGenerating) controller.stop()
    controller.dispose()
    setActiveSessionId(null)
    clearDraftPrompt()
    setQuestion("")
    setController(new ChatController(createChatServices(apiBaseUrl), null))
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2 text-xs">
        <div className="flex min-w-0 items-center gap-2">
          <Badge variant={state.sessionId ? "secondary" : "outline"} className="text-[11px]">
            {state.sessionId ? "Phiên bền vững" : "Phiên mới"}
          </Badge>
          {pageContext?.selectedDocumentName && (
            <span className="truncate text-muted-foreground" title={pageContext.selectedDocumentName}>
              Đang xem: {pageContext.selectedDocumentName}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 gap-1 px-2 text-xs"
            onClick={handleResetSession}
            disabled={state.messages.length === 0 && !state.isGenerating}
          >
            <RotateCcw className="size-3" aria-hidden="true" />
            <span>Phiên mới</span>
          </Button>
          {state.sessionId && (
            <Button
              nativeButton={false}
              variant="ghost"
              size="sm"
              className="h-7 gap-1 px-2 text-xs"
              render={<Link href={`/chat/${encodeURIComponent(state.sessionId)}`} />}
            >
              <span>Mở toàn trang</span>
              <ExternalLink className="size-3" aria-hidden="true" />
            </Button>
          )}
        </div>
      </div>

      <div
        ref={viewport}
        onScroll={scroll.onScroll}
        tabIndex={0}
        role="region"
        aria-label="Lịch sử hỏi đáp Trợ lý HR"
        className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4"
        aria-busy={state.isGenerating}
      >
        <div ref={content}>
          {state.messages.length === 0 ? (
            <div className="space-y-4 py-4">
              <div className="flex items-center gap-2.5 text-sm font-medium">
                <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Bot className="size-4" aria-hidden="true" />
                </span>
                <span>Xin chào! Hãy hỏi về chính sách, quy định hoặc quy trình HR.</span>
              </div>
              <div className="space-y-2">
                <p className="text-xs text-muted-foreground">Gợi ý câu hỏi nhanh:</p>
                <div className="grid gap-1.5">
                  {HR_PROMPT_TEMPLATES.slice(0, 3).map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className="rounded-lg border bg-muted/30 px-3 py-2 text-left text-xs leading-5 transition-colors hover:bg-muted"
                      onClick={() => {
                        clearDraftPrompt()
                        setQuestion(item.prompt)
                      }}
                    >
                      {item.prompt}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {state.messages.map((message) => (
                <ChatMessage key={message.key} message={message} apiBaseUrl={apiBaseUrl} />
              ))}
            </div>
          )}
        </div>
      </div>

      {unread && (
        <div className="border-t px-4 py-1.5">
          <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={scroll.jump}>
            Nội dung mới — Về cuối
          </Button>
        </div>
      )}

      {state.persistenceError && (
        <p role="alert" className="border-t px-4 py-2 text-xs text-destructive">
          {state.persistenceError}
        </p>
      )}

      <ChatComposer
        apiBaseUrl={apiBaseUrl}
        inputId={inputId}
        value={effectiveQuestion}
        showAttachments={false}
        disabled={state.isGenerating}
        isGenerating={state.isGenerating && !state.isVerifyingHistory}
        onChange={(nextValue) => {
          if (draftPrompt !== null) clearDraftPrompt()
          setQuestion(nextValue)
        }}
        onSubmit={handleSubmit}
        onStop={() => controller.stop()}
      />
    </div>
  )
}

export function HrChatbotWidget({ apiBaseUrl }: { apiBaseUrl: string | null }) {
  const { isOpen, openWidget, closeWidget } = useHrChatbot()

  return (
    <>
      <div className="fixed right-5 bottom-5 z-30">
        <Button
          type="button"
          size="lg"
          className="rounded-full shadow-lg transition-transform duration-150 hover:-translate-y-0.5 active:scale-[0.98]"
          aria-expanded={isOpen}
          aria-label="Mở Trợ lý HR"
          onClick={() => (isOpen ? closeWidget() : openWidget())}
        >
          <MessageSquareText className="size-4" aria-hidden="true" />
          <span>Trợ lý HR</span>
        </Button>
      </div>

      <Sheet open={isOpen} onOpenChange={(nextOpen) => (nextOpen ? openWidget() : closeWidget())}>
        <SheetContent
          side="right"
          className="hr-theme flex w-full flex-col gap-0 p-0 font-sans sm:max-w-lg"
        >
          <SheetHeader className="border-b pr-12">
            <SheetTitle className="flex items-center gap-2 text-base">
              <Bot className="size-4 text-primary" aria-hidden="true" />
              <span>Trợ lý chính sách HR</span>
            </SheetTitle>
            <SheetDescription className="text-xs">
              Hỏi đáp nhiều lượt kết nối RAG Backend; nguồn trích dẫn mở trực tiếp để kiểm chứng.
            </SheetDescription>
          </SheetHeader>

          {apiBaseUrl ? (
            <ConfiguredWidgetChat apiBaseUrl={apiBaseUrl} />
          ) : (
            <div className="p-6 text-sm text-muted-foreground">
              <p className="font-medium text-foreground">Chưa cấu hình API Backend</p>
              <p className="mt-2 leading-6">
                Thiết lập <code>NEXT_PUBLIC_API_BASE_URL</code> để Trợ lý HR kết nối tới RAG Backend hoặc Mock Server.
              </p>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </>
  )
}
