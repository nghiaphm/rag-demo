"use client"

import { useState } from "react"
import {
  AlertCircle,
  LoaderCircle,
  MessageSquareText,
  RotateCcw,
} from "lucide-react"

import { ChatComposer } from "@/components/chat/chat-composer"
import { ChatMessage } from "@/components/chat/chat-message"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { chatConversationFixture } from "@/fixtures/chat"

type PreviewState = "conversation" | "empty" | "loading" | "error"

const previewOptions: readonly { value: PreviewState; label: string }[] = [
  { value: "conversation", label: "Hội thoại" },
  { value: "empty", label: "Trống" },
  { value: "loading", label: "Đang tải" },
  { value: "error", label: "Lỗi" },
]

function ConversationFixture() {
  return (
    <div className="space-y-5" aria-label="Hội thoại mẫu">
      {chatConversationFixture.map((message) => (
        <ChatMessage key={message.id} message={message} />
      ))}
    </div>
  )
}

function EmptyFixture() {
  return (
    <div className="flex min-h-72 flex-col items-center justify-center px-4 text-center">
      <span className="flex size-12 items-center justify-center rounded-2xl bg-muted">
        <MessageSquareText className="size-5 text-muted-foreground" aria-hidden="true" />
      </span>
      <h2 className="mt-4 text-base font-semibold">Bắt đầu một cuộc trò chuyện</h2>
      <p className="mt-2 max-w-sm text-sm leading-6 text-muted-foreground">
        Đặt câu hỏi về tài liệu của bạn. Câu trả lời và nguồn tham chiếu sẽ xuất hiện tại đây.
      </p>
    </div>
  )
}

function LoadingFixture() {
  return (
    <div aria-busy="true" aria-label="Đang chuẩn bị câu trả lời" className="space-y-5">
      <div className="flex justify-end gap-3">
        <div className="w-[70%] space-y-2 rounded-2xl rounded-tr-sm bg-muted p-4">
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-2/3" />
        </div>
        <Skeleton className="size-8 shrink-0 rounded-full" />
      </div>
      <div className="flex gap-3">
        <Skeleton className="size-8 shrink-0 rounded-full" />
        <div className="w-[78%] space-y-3 rounded-2xl rounded-tl-sm border p-4">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />
            Đang chuẩn bị câu trả lời
          </div>
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-5/6" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      </div>
    </div>
  )
}

function ErrorFixture() {
  return (
    <div className="flex min-h-72 items-center justify-center px-4">
      <div role="alert" className="w-full max-w-md rounded-xl border border-destructive/30 bg-destructive/5 p-5">
        <AlertCircle className="size-5 text-destructive" aria-hidden="true" />
        <h2 className="mt-3 font-semibold">Không thể tạo câu trả lời</h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          Đã xảy ra lỗi tạm thời. Nội dung đã nhập sẽ được giữ lại khi luồng thật được tích hợp.
        </p>
        <Button className="mt-4" variant="outline" size="sm" disabled>
          <RotateCcw aria-hidden="true" />
          Thử lại
        </Button>
      </div>
    </div>
  )
}

function PreviewContent({ state }: { state: PreviewState }) {
  if (state === "empty") return <EmptyFixture />
  if (state === "loading") return <LoadingFixture />
  if (state === "error") return <ErrorFixture />
  return <ConversationFixture />
}

export function ChatPreview() {
  const [previewState, setPreviewState] = useState<PreviewState>("conversation")

  return (
    <section aria-labelledby="chat-title" className="mx-auto flex w-full max-w-5xl flex-1 flex-col">
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium text-muted-foreground">Không gian hỏi đáp</p>
            <Badge variant="outline">Fixture UI</Badge>
          </div>
          <h1 id="chat-title" className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
            Chat
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            Xem trước các trạng thái giao diện trước khi kết nối luồng trả lời thật.
          </p>
        </div>

        <div
          role="group"
          aria-label="Chọn trạng thái xem trước"
          className="flex max-w-full gap-1 overflow-x-auto rounded-lg border bg-background p-1"
        >
          {previewOptions.map((option) => (
            <Button
              key={option.value}
              type="button"
              size="sm"
              variant={previewState === option.value ? "secondary" : "ghost"}
              aria-pressed={previewState === option.value}
              onClick={() => setPreviewState(option.value)}
            >
              {option.label}
            </Button>
          ))}
        </div>
      </div>

      <div className="flex min-h-[34rem] flex-1 flex-col overflow-hidden rounded-xl border bg-background shadow-sm">
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4 sm:p-6" aria-live="polite">
          <PreviewContent state={previewState} />
        </div>
        <ChatComposer disabled={previewState === "loading"} />
      </div>
    </section>
  )
}
