import { Bot, LoaderCircle, UserRound } from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { ChatViewMessage } from "@/lib/chat/controller"

const statusLabels = {
  PENDING: "Đang gửi",
  STREAMING: "Đang trả lời",
  COMPLETED: "Hoàn tất",
  PARTIAL: "Chưa hoàn tất",
  FAILED: "Thất bại",
} as const

export function ChatMessage({ message }: { message: ChatViewMessage }) {
  const isUser = message.role === "user"

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
          "max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-6 sm:max-w-[75%]",
          isUser
            ? "rounded-tr-sm bg-primary text-primary-foreground"
            : "rounded-tl-sm border bg-card text-card-foreground shadow-xs"
        )}
      >
        {!isUser && (
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge variant={message.status === "FAILED" ? "destructive" : "secondary"}>
              {(message.status === "PENDING" || message.status === "STREAMING") && (
                <LoaderCircle className="animate-spin" aria-hidden="true" />
              )}
              {statusLabels[message.status]}
            </Badge>
            {message.model && <span className="text-xs text-muted-foreground">{message.model}</span>}
          </div>
        )}
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : message.content ? (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
              ol: ({ children }) => (
                <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>
              ),
              ul: ({ children }) => (
                <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>
              ),
              blockquote: ({ children }) => (
                <blockquote className="mt-3 border-l-2 border-primary/40 pl-3 text-muted-foreground">
                  {children}
                </blockquote>
              ),
              code: ({ children, className, ...props }) => (
                <code
                  className={cn("rounded bg-muted px-1 py-0.5 font-mono text-[0.9em]", className)}
                  {...props}
                >
                  {children}
                </code>
              ),
              pre: ({ children }) => (
                <pre className="my-3 overflow-x-auto rounded-lg bg-muted p-3 text-xs">{children}</pre>
              ),
              a: ({ children, href }) => (
                <a
                  href={href}
                  className="font-medium underline underline-offset-4"
                  target="_blank"
                  rel="noreferrer"
                >
                  {children}
                </a>
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>
        ) : (
          <p className="text-muted-foreground">
            {message.status === "FAILED" ? "Không có nội dung trả lời." : "Đang chuẩn bị câu trả lời…"}
          </p>
        )}
        {!isUser && message.error && (
          <p role="alert" className="mt-3 border-t pt-3 text-sm text-destructive">
            {message.error.message}
          </p>
        )}
      </div>
    </article>
  )
}
