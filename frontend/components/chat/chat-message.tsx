import { Bot, LoaderCircle, UserRound } from "lucide-react"
import { CitationContent } from "@/components/chat/citation-content"
import { CopyButton } from "@/components/chat/copy-button"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { ChatViewMessage } from "@/lib/chat/controller"
import { isHistoricalNonterminal } from "@/lib/chat/recovery"

const statusLabels = {
  PENDING: "Đang gửi",
  STREAMING: "Đang trả lời",
  COMPLETED: "Hoàn tất",
  PARTIAL: "Chưa hoàn tất",
  FAILED: "Thất bại",
} as const

export function ChatMessage({ message }: { message: ChatViewMessage }) {
  const isUser = message.role === "user"
  const historicalNonterminal = isHistoricalNonterminal(message)

  return (
    <article
      aria-label={isUser ? "Tin nhắn của bạn" : "Câu trả lời của trợ lý"}
      className={cn("flex items-start gap-3", isUser && "flex-row-reverse")}
    >
      <Avatar className={cn(isUser && "bg-primary text-primary-foreground")}>
        <AvatarFallback className={cn(isUser && "bg-primary text-primary-foreground")}>
          {isUser ? (
            <UserRound className="size-4" aria-hidden="true" />
          ) : (
            <Bot className="size-4" aria-hidden="true" />
          )}
        </AvatarFallback>
      </Avatar>

      <div
        className={cn(
          "min-w-0 max-w-[85%] break-words rounded-2xl px-4 py-3 text-sm leading-6 sm:max-w-[75%]",
          isUser
            ? "rounded-tr-sm bg-primary text-primary-foreground"
            : "rounded-tl-sm border bg-card text-card-foreground shadow-xs"
        )}
      >
        {!isUser && (
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge variant={message.status === "FAILED" ? "destructive" : "secondary"}>
              {!historicalNonterminal && (message.status === "PENDING" || message.status === "STREAMING") && (
                <LoaderCircle className="animate-spin" aria-hidden="true" />
              )}
              {historicalNonterminal ? `${message.status} · Lịch sử` : statusLabels[message.status]}
            </Badge>
            {message.model && <span className="text-xs text-muted-foreground">{message.model}</span>}
          </div>
        )}
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : message.content ? (
          <CitationContent key={message.key} message={message} />
        ) : (
          <p className="text-muted-foreground">
            {historicalNonterminal ? "Chưa có nội dung được lưu." : message.status === "PENDING" || message.status === "STREAMING" ? "Đang chuẩn bị câu trả lời…" : "Không có nội dung trả lời."}
          </p>
        )}
        {historicalNonterminal && <p className="mt-2 text-xs text-muted-foreground">Trạng thái backend: {message.status}. Không có luồng trực tiếp cho tin nhắn này.</p>}
        {!isUser && message.error && (
          <p role="alert" className="mt-3 border-t pt-3 text-sm text-destructive">
            {message.error.message}
          </p>
        )}
        {isUser && message.status === "FAILED" && (
          <p className="mt-2 text-xs">Chưa xác nhận câu hỏi này đã được xử lý.</p>
        )}
        {message.content && <div className="mt-2"><CopyButton text={message.content}
          label={isUser ? "Sao chép câu hỏi" : "Sao chép câu trả lời"}
          disabled={message.status === "PENDING" || message.status === "STREAMING"} /></div>}
      </div>
    </article>
  )
}
