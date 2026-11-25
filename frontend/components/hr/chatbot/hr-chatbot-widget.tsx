"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useId, useRef, useState, useSyncExternalStore, type ReactNode } from "react"
import {
  ArrowLeft,
  ArrowUpRight,
  Bot,
  Compass,
  ExternalLink,
  History,
  LoaderCircle,
  MessageSquareText,
  RotateCcw,
} from "lucide-react"

import { ChatComposer } from "@/components/chat/chat-composer"
import { ChatMessage } from "@/components/chat/chat-message"
import { HrChatbotHistory } from "@/components/hr/chatbot/hr-chatbot-history"
import { useHrChatbot } from "@/components/hr/layout/hr-chatbot-provider"
import { useOptionalHrTour } from "@/components/hr/tour/hr-tour-provider"
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
import { createApiClient } from "@/lib/api/client"
import { safeApiErrorMessage } from "@/lib/api/error-ux"
import { listSessionMessages } from "@/lib/api/sessions"
import { ChatController, type ChatViewMessage } from "@/lib/chat/controller"
import { ChatScrollController } from "@/lib/chat/scroll"
import { createChatServices } from "@/lib/chat/services"
import {
  buildHrUiContext,
  extractHrNavigationSuggestions,
  getHrRouteDisplayTitle,
  isSafeHrRoute,
  rehypeHrRouteLinks,
  resolveHrRouteFromPathname,
} from "@/lib/hr/page-context"
import { historyMessageToViewMessage, loadMessageHistory } from "@/lib/sessions/history"
import type { MessageAttachment } from "@/types/chat"
import type { SessionResponse } from "@/types/sessions"

const HR_REHYPE_PLUGINS = [rehypeHrRouteLinks]

function formatInlineLinkLabel(href: string, children: ReactNode): ReactNode {
  if (!isSafeHrRoute(href)) return children
  if (typeof children === "string") {
    const trimmed = children.trim()
    if (isSafeHrRoute(trimmed) || trimmed === `[${href}]`) {
      return getHrRouteDisplayTitle(href)
    }
  }
  return children
}

function renderHrInternalLink(href: string, children: ReactNode) {
  if (!isSafeHrRoute(href)) return null
  const label = formatInlineLinkLabel(href, children)
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-0.5 rounded bg-accent/65 px-1.5 py-0.5 font-medium text-primary underline decoration-primary/45 underline-offset-4 transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
    >
      <span>{label}</span>
      <ArrowUpRight className="inline size-3 shrink-0" aria-hidden="true" />
    </Link>
  )
}

function ConfiguredWidgetChat({ apiBaseUrl }: { apiBaseUrl: string }) {
  const inputId = useId()
  const pathname = usePathname()
  const {
    activeSessionId,
    draftPrompt,
    pageContext,
    setActiveSessionId,
    clearDraftPrompt,
  } = useHrChatbot()

  const activeRoute = resolveHrRouteFromPathname(pageContext?.route ?? pathname)
  const uiContext = buildHrUiContext(pageContext, pathname)

  const [viewMode, setViewMode] = useState<"chat" | "history">("chat")
  const [question, setQuestion] = useState("")
  const [restoringSessionId, setRestoringSessionId] = useState<string | null>(null)
  const [restoreError, setRestoreError] = useState<string | null>(null)
  const [controller, setController] = useState(
    () => new ChatController(createChatServices(apiBaseUrl, "hr"), activeSessionId),
  )
  const state = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot,
  )
  const [scroll] = useState(() => new ChatScrollController())
  const unread = useSyncExternalStore(
    scroll.subscribe,
    scroll.getSnapshot,
    scroll.getSnapshot,
  )
  const viewport = useRef<HTMLDivElement>(null)
  const content = useRef<HTMLDivElement>(null)
  const hydratedSessionRef = useRef<string | null>(null)
  const restoreAbortRef = useRef<AbortController | null>(null)
  const questionDraftRef = useRef(question)
  useEffect(() => {
    questionDraftRef.current = question
  }, [question])

  useEffect(() => {
    if (state.sessionId && state.sessionId !== activeSessionId) {
      hydratedSessionRef.current = state.sessionId
      setActiveSessionId(state.sessionId)
    }
  }, [state.sessionId, activeSessionId, setActiveSessionId])

  useEffect(() => {
    if (!activeSessionId) {
      hydratedSessionRef.current = null
      return
    }
    if (hydratedSessionRef.current === activeSessionId) return
    const snapshot = controller.getSnapshot()
    if (snapshot.sessionId === activeSessionId && snapshot.messages.length > 0) {
      hydratedSessionRef.current = activeSessionId
      return
    }

    const abort = new AbortController()
    restoreAbortRef.current?.abort()
    restoreAbortRef.current = abort
    const api = createApiClient({ baseUrl: apiBaseUrl })

    queueMicrotask(() => {
      if (abort.signal.aborted) return
      setRestoringSessionId(activeSessionId)
      setRestoreError(null)
    })

    loadMessageHistory(
      activeSessionId,
      {
        list: (id, query, signal) => listSessionMessages(api, id, query, signal),
      },
      abort.signal,
    )
      .then((records) => {
        if (abort.signal.aborted) return
        const restored = records.map(historyMessageToViewMessage)
        hydratedSessionRef.current = activeSessionId
        setRestoringSessionId(null)
        setController((prev) => {
          prev.dispose()
          return new ChatController(
            createChatServices(apiBaseUrl, "hr"),
            activeSessionId,
            restored,
          )
        })
      })
      .catch((error) => {
        if (abort.signal.aborted) return
        setRestoringSessionId(null)
        setRestoreError(
          safeApiErrorMessage(error, "Không thể khôi phục lịch sử hội thoại HR."),
        )
      })

    return () => abort.abort()
  }, [activeSessionId, apiBaseUrl, controller])

  useEffect(() => {
    if (viewMode !== "chat" || !viewport.current || !content.current) return
    const detach = scroll.attach(viewport.current)
    const observer = new ResizeObserver(scroll.contentChanged)
    observer.observe(content.current)
    observer.observe(viewport.current)
    return () => {
      observer.disconnect()
      detach()
    }
  }, [scroll, controller, viewMode])

  useEffect(() => {
    scroll.contentChanged()
  }, [scroll, state.messages])

  useEffect(() => {
    return () => {
      restoreAbortRef.current?.abort()
      controller.dispose()
    }
  }, [controller])

  const effectiveQuestion = draftPrompt ?? question

  async function handleSubmit(
    attachments: readonly MessageAttachment[] = [],
  ): Promise<boolean> {
    const trimmed = effectiveQuestion.trim()
    if (!trimmed || controller.getSnapshot().isGenerating || restoringSessionId) {
      return false
    }
    const previousDraft = trimmed
    clearDraftPrompt()
    setQuestion("")
    const accepted = await controller.submit(trimmed, attachments, { uiContext })
    if (!accepted) {
      if (!questionDraftRef.current) setQuestion(previousDraft)
      return false
    }
    const last = controller.getSnapshot().messages.at(-1)
    const completed =
      last?.role === "assistant" && last.status === "COMPLETED" && !last.error
    if (!completed && !questionDraftRef.current) {
      setQuestion(previousDraft)
    }
    return completed
  }

  function handleResetSession() {
    restoreAbortRef.current?.abort()
    setRestoringSessionId(null)
    setRestoreError(null)
    hydratedSessionRef.current = null
    if (state.isGenerating) controller.stop()
    controller.dispose()
    setActiveSessionId(null)
    clearDraftPrompt()
    setQuestion("")
    setViewMode("chat")
    setController(new ChatController(createChatServices(apiBaseUrl, "hr"), null))
  }

  function handleSelectSession(session: SessionResponse) {
    if (state.isGenerating) return
    setRestoreError(null)
    if (session.session_id === state.sessionId && state.messages.length > 0) {
      setViewMode("chat")
      return
    }
    hydratedSessionRef.current = null
    controller.dispose()
    setActiveSessionId(session.session_id)
    setController(
      new ChatController(createChatServices(apiBaseUrl, "hr"), session.session_id),
    )
    setViewMode("chat")
  }

  function renderNavigationActions(message: ChatViewMessage) {
    if (message.status === "PENDING" || message.status === "STREAMING" || !message.content) {
      return null
    }
    const suggestions = extractHrNavigationSuggestions(message.content, activeRoute)
    if (suggestions.length === 0) return null

    return (
      <div aria-label="Đề xuất điều hướng HR" className="mt-3 space-y-2 border-t pt-3">
        <p className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
          <Compass className="size-3.5 text-primary" aria-hidden="true" />
          <span>Đi tới trang liên quan</span>
        </p>
        <div className="flex flex-wrap gap-1.5">
          {suggestions.map((item) => (
            <Button
              key={item.route}
              nativeButton={false}
              variant="outline"
              size="sm"
              className="h-7 gap-1 border-primary/25 bg-accent/40 px-2.5 text-xs text-accent-foreground hover:bg-accent"
              render={<Link href={item.route} />}
            >
              <span>{item.title}</span>
              <ArrowUpRight className="size-3" aria-hidden="true" />
            </Button>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2 text-xs">
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          <Badge variant={state.sessionId ? "secondary" : "outline"} className="text-[11px]">
            {state.sessionId ? "Phiên HR bền vững" : "Phiên HR mới"}
          </Badge>
          <Badge
            variant="outline"
            className="border-primary/25 bg-accent/50 text-[11px] text-accent-foreground"
          >
            Trang: {uiContext.page_title}
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
            variant={viewMode === "history" ? "secondary" : "ghost"}
            size="sm"
            className="h-7 gap-1 px-2 text-xs"
            disabled={state.isGenerating}
            onClick={() => setViewMode((prev) => (prev === "history" ? "chat" : "history"))}
          >
            {viewMode === "history" ? (
              <>
                <ArrowLeft className="size-3" aria-hidden="true" />
                <span>Quay lại chat</span>
              </>
            ) : (
              <>
                <History className="size-3" aria-hidden="true" />
                <span>Lịch sử</span>
              </>
            )}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 gap-1 px-2 text-xs"
            onClick={handleResetSession}
            disabled={
              state.messages.length === 0 && !state.sessionId && !state.isGenerating
            }
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

      {viewMode === "history" ? (
        <HrChatbotHistory
          apiBaseUrl={apiBaseUrl}
          activeSessionId={state.sessionId}
          disabled={state.isGenerating}
          onNewChat={handleResetSession}
          onSelectSession={handleSelectSession}
          onActiveSessionDeleted={handleResetSession}
        />
      ) : (
        <>
          <div
            ref={viewport}
            onScroll={scroll.onScroll}
            tabIndex={0}
            role="region"
            aria-label="Lịch sử hỏi đáp Trợ lý HR"
            className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4"
            aria-busy={state.isGenerating || Boolean(restoringSessionId)}
          >
            <div ref={content}>
              {restoringSessionId ? (
                <div className="flex items-center justify-center gap-2 py-12 text-xs text-muted-foreground">
                  <LoaderCircle className="size-4 animate-spin text-primary" aria-hidden="true" />
                  <span>Đang khôi phục lịch sử hội thoại…</span>
                </div>
              ) : restoreError ? (
                <div className="space-y-3 rounded-xl border border-destructive/30 bg-card p-4 text-xs">
                  <p role="alert" className="text-destructive">
                    {restoreError}
                  </p>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        hydratedSessionRef.current = null
                        setRestoreError(null)
                        setController((prev) => {
                          prev.dispose()
                          return new ChatController(
                            createChatServices(apiBaseUrl, "hr"),
                            activeSessionId,
                          )
                        })
                      }}
                    >
                      Thử khôi phục lại
                    </Button>
                    <Button type="button" size="sm" variant="ghost" onClick={handleResetSession}>
                      Tạo phiên mới
                    </Button>
                  </div>
                </div>
              ) : state.messages.length === 0 ? (
                <div className="space-y-4 py-4">
                  <div className="flex items-center gap-2.5 text-sm font-medium">
                    <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      <Bot className="size-4" aria-hidden="true" />
                    </span>
                    <span>
                      Xin chào! Hãy hỏi về chính sách HR hoặc thao tác trên trang{" "}
                      {uiContext.page_title}.
                    </span>
                  </div>
                  <div className="space-y-2">
                    <p className="text-xs text-muted-foreground">Gợi ý câu hỏi nhanh:</p>
                    <div className="grid gap-1.5">
                      <button
                        type="button"
                        className="rounded-lg border border-primary/20 bg-accent/40 px-3 py-2 text-left text-xs leading-5 text-accent-foreground transition-colors hover:bg-accent"
                        onClick={() => {
                          clearDraftPrompt()
                          setQuestion(
                            "Hãy phân tích và thống kê nhân sự trên trang Dashboard hiện tại",
                          )
                        }}
                      >
                        Hãy phân tích và thống kê nhân sự trên trang Dashboard hiện tại
                      </button>
                      <button
                        type="button"
                        className="rounded-lg border border-primary/20 bg-accent/40 px-3 py-2 text-left text-xs leading-5 text-accent-foreground transition-colors hover:bg-accent"
                        onClick={() => {
                          clearDraftPrompt()
                          setQuestion(
                            `Hướng dẫn thao tác chức năng trang ${uiContext.page_title} hiện tại`,
                          )
                        }}
                      >
                        Hướng dẫn thao tác chức năng trang {uiContext.page_title} hiện tại
                      </button>
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
                    <ChatMessage
                      key={message.key}
                      message={message}
                      apiBaseUrl={apiBaseUrl}
                      renderAssistantActions={renderNavigationActions}
                      extraRehypePlugins={HR_REHYPE_PLUGINS}
                      renderInternalLink={renderHrInternalLink}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>

          {unread && (
            <div className="border-t px-4 py-1.5">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 text-xs"
                onClick={scroll.jump}
              >
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
            showAttachments={true}
            documentsHref="/hr/documents"
            disabled={state.isGenerating || Boolean(restoringSessionId)}
            isGenerating={state.isGenerating && !state.isVerifyingHistory}
            onChange={(nextValue) => {
              if (draftPrompt !== null) clearDraftPrompt()
              setQuestion(nextValue)
            }}
            onSubmit={handleSubmit}
            onStop={() => controller.stop()}
          />
        </>
      )}
    </div>
  )
}

export function HrChatbotWidget({ apiBaseUrl }: { apiBaseUrl: string | null }) {
  const { isOpen, openWidget, closeWidget } = useHrChatbot()
  const tour = useOptionalHrTour()
  const isTourChatbotStep = Boolean(tour?.isActive && tour.currentStep?.opensChatbot)

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

      <Sheet
        open={isOpen}
        modal={!isTourChatbotStep}
        disablePointerDismissal={isTourChatbotStep}
        onOpenChange={(nextOpen) => (nextOpen ? openWidget() : closeWidget())}
      >
        <SheetContent
          side="right"
          data-tour="hr-chatbot-drawer"
          className="hr-theme flex w-full flex-col gap-0 p-0 font-sans sm:max-w-lg"
        >
          <SheetHeader className="border-b pr-12">
            <SheetTitle className="flex items-center gap-2 text-base">
              <Bot className="size-4 text-primary" aria-hidden="true" />
              <span>Trợ lý chính sách HR</span>
            </SheetTitle>
            <SheetDescription className="text-xs">
              Quản lý hội thoại HR riêng biệt, đính kèm tài liệu và hỏi đáp kèm trích dẫn nguồn.
            </SheetDescription>
          </SheetHeader>

          {apiBaseUrl ? (
            <ConfiguredWidgetChat apiBaseUrl={apiBaseUrl} />
          ) : (
            <div className="p-6 text-sm text-muted-foreground">
              <p className="font-medium text-foreground">Chưa cấu hình API Backend</p>
              <p className="mt-2 leading-6">
                Thiết lập <code>NEXT_PUBLIC_API_BASE_URL</code> để Trợ lý HR kết nối tới RAG
                Backend hoặc Mock Server.
              </p>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </>
  )
}
