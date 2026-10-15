"use client"

import { type FormEvent, type KeyboardEvent } from "react"
import { SendHorizontal, Square } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"

interface ChatComposerProps {
  value: string
  disabled?: boolean
  isGenerating?: boolean
  onChange: (value: string) => void
  onSubmit: () => void
  onStop: () => void
}

export function ChatComposer({
  value,
  disabled = false,
  isGenerating = false,
  onChange,
  onSubmit,
  onStop,
}: ChatComposerProps) {
  const canSubmit = !disabled && !isGenerating && value.trim().length > 0

  function submit(event?: FormEvent) {
    event?.preventDefault()
    if (canSubmit) onSubmit()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form
      className="border-t bg-background p-3 sm:p-4"
      onSubmit={submit}
    >
      <div className="rounded-xl border bg-background p-2 shadow-xs focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/20">
        <label htmlFor="chat-question" className="sr-only">
          Câu hỏi
        </label>
        <Textarea
          id="chat-question"
          aria-describedby="composer-help"
          className="max-h-40 min-h-20 resize-none border-0 px-2 shadow-none focus-visible:border-transparent focus-visible:ring-0"
          placeholder="Nhập câu hỏi về tài liệu…"
          value={value}
          onChange={(event) => { if (!disabled) onChange(event.target.value) }}
          onKeyDown={handleKeyDown}
          readOnly={disabled}
          aria-readonly={disabled}
        />
        <div className="flex items-end justify-between gap-3 px-1 pt-2">
          <p id="composer-help" className="text-xs leading-5 text-muted-foreground">
            {isGenerating ? "Đang tạo câu trả lời…" : "Enter để gửi, Shift+Enter để xuống dòng."}
          </p>
          <Button
            type={isGenerating ? "button" : "submit"}
            size="icon"
            disabled={isGenerating ? false : !canSubmit}
            aria-label={isGenerating ? "Dừng tạo câu trả lời" : "Gửi câu hỏi"}
            onClick={isGenerating ? onStop : undefined}
          >
            {isGenerating ? (
              <Square className="fill-current" aria-hidden="true" />
            ) : (
              <SendHorizontal aria-hidden="true" />
            )}
          </Button>
        </div>
      </div>
    </form>
  )
}
