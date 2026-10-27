"use client"

import { useEffect, useRef, type FormEvent, type KeyboardEvent } from "react"
import { Plus, SendHorizontal, Square } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { AttachmentChip } from "@/components/chat/attachment-chip"
import { useChatAttachments } from "@/hooks/use-chat-attachments"
import { DOCUMENT_UPLOAD_ACCEPT } from "@/lib/documents/upload-validation"

interface ChatComposerProps {
  apiBaseUrl?: string | null
  inputId?: string
  value: string
  disabled?: boolean
  isGenerating?: boolean
  onChange: (value: string) => void
  onSubmit: () => void | Promise<boolean>
  onSuccessfulReset?: () => void
  onStop: () => void
}

export function ChatComposer({
  apiBaseUrl = null,
  inputId = "chat-question",
  value,
  disabled = false,
  isGenerating = false,
  onChange,
  onSubmit,
  onSuccessfulReset,
  onStop,
}: ChatComposerProps) {
  const picker = useRef<HTMLInputElement>(null)
  const mounted = useRef(false)
  const submission = useRef<symbol | null>(null)
  const { attachments, choose, remove, capture, clearSubmitted } = useChatAttachments(apiBaseUrl)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; submission.current = null }
  }, [])
  const canSubmit = !disabled && !isGenerating && value.trim().length > 0

  async function submit(event?: FormEvent) {
    event?.preventDefault()
    if (!canSubmit || submission.current) return
    const identity = Symbol("composer submission")
    submission.current = identity
    const submitted = capture()
    try {
      const successful = await onSubmit()
      if (successful && mounted.current && submission.current === identity) {
        const empty = clearSubmitted(submitted)
        if (picker.current) picker.current.value = ""
        // Navigation would unmount any newly selected attachments.
        if (empty) onSuccessfulReset?.()
      }
    } catch {
      // ChatController reports request failures; retain the draft for deliberate retry.
    } finally {
      if (submission.current === identity) submission.current = null
    }
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
        {attachments.length > 0 && <div className="space-y-2 px-2 pb-2">
          <ul aria-label="Tệp đính kèm" className="grid max-h-48 gap-2 overflow-y-auto sm:grid-cols-2">
            {attachments.map(attachment => <AttachmentChip key={attachment.id} attachment={attachment} onRemove={() => remove(attachment.id)} />)}
          </ul>
          <p className="text-xs text-muted-foreground">Tệp được tải vào thư viện tài liệu; chưa giới hạn chat theo tệp đính kèm. <a href="/documents" target="_blank" rel="noreferrer" className="underline">Kiểm tra tài liệu (tab mới)</a> trước khi thử tải lại nếu chưa rõ kết quả.</p>
        </div>}
        <label htmlFor={inputId} className="sr-only">
          Câu hỏi
        </label>
        <Textarea
          id={inputId}
          aria-describedby={`${inputId}-help`}
          className="max-h-40 min-h-20 resize-none border-0 px-2 shadow-none focus-visible:border-transparent focus-visible:ring-0"
          placeholder="Nhập câu hỏi về tài liệu…"
          value={value}
          onChange={(event) => { if (!disabled) onChange(event.target.value) }}
          onKeyDown={handleKeyDown}
          readOnly={disabled}
          aria-readonly={disabled}
        />
        <div className="flex items-end justify-between gap-3 px-1 pt-2">
          <input ref={picker} type="file" multiple accept={DOCUMENT_UPLOAD_ACCEPT} className="hidden" tabIndex={-1}
            aria-label="Chọn tệp đính kèm" disabled={!apiBaseUrl}
            onChange={event => { choose(Array.from(event.target.files ?? [])); event.target.value = "" }} />
          <Button type="button" variant="ghost" size="icon" className="size-9 shrink-0" disabled={!apiBaseUrl}
            aria-label="Thêm tệp đính kèm" onClick={() => picker.current?.click()}><Plus aria-hidden="true" /></Button>
          <p id={`${inputId}-help`} className="text-xs leading-5 text-muted-foreground">
            {isGenerating ? "Đang tạo câu trả lời…" : "Enter để gửi, Shift+Enter để xuống dòng."}
          </p>
          <Button
            key={isGenerating ? "stop" : "send"}
            type={isGenerating ? "button" : "submit"}
            size="icon"
            disabled={isGenerating ? false : !canSubmit}
            aria-label={isGenerating ? "Dừng tạo câu trả lời" : "Gửi câu hỏi"}
            onClick={isGenerating ? event => { event.preventDefault(); onStop() } : undefined}
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
