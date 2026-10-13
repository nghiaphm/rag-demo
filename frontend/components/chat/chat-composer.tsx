"use client"

import { SendHorizontal } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"

export function ChatComposer({ disabled = false }: { disabled?: boolean }) {
  return (
    <form
      className="border-t bg-background p-3 sm:p-4"
      onSubmit={(event) => event.preventDefault()}
    >
      <div className="rounded-xl border bg-background p-2 shadow-xs focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/20">
        <label htmlFor="fixture-chat-question" className="sr-only">
          Câu hỏi
        </label>
        <Textarea
          id="fixture-chat-question"
          aria-describedby="fixture-composer-help"
          className="max-h-40 min-h-20 resize-none border-0 px-2 shadow-none focus-visible:border-transparent focus-visible:ring-0"
          placeholder="Nhập câu hỏi về tài liệu…"
          disabled={disabled}
        />
        <div className="flex items-end justify-between gap-3 px-1 pt-2">
          <p id="fixture-composer-help" className="text-xs leading-5 text-muted-foreground">
            Bản xem trước — chưa kết nối API.
          </p>
          <Button type="submit" size="icon" disabled aria-label="Gửi câu hỏi">
            <SendHorizontal aria-hidden="true" />
          </Button>
        </div>
      </div>
    </form>
  )
}
