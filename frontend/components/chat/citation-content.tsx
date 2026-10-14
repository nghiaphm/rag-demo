"use client"

import { useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { Button } from "@/components/ui/button"
import { Sheet, SheetClose, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet"
import type { ChatViewMessage } from "@/lib/chat/controller"
import { buildCitationPanel, prioritizeSourceGroups, sourceKey, type CitationSource, type SourceGroup } from "@/lib/chat/citation-panel"
import { rehypeCitationMarkers } from "@/lib/chat/citation-markdown"
import { resolveCitationOrdinal } from "@/lib/chat/source-mapper"
import { cn } from "@/lib/utils"

export function CitationMarker({ message, ordinal, marker, onSelect }: {
  message: ChatViewMessage
  ordinal: number
  marker: string
  onSelect: (source: CitationSource) => void
}) {
  const resolution = resolveCitationOrdinal(message, ordinal)
  if (resolution.status === "unavailable") {
    const explanation = resolution.reason === "missing_metadata"
      ? "Thiếu thông tin nguồn cho trích dẫn này"
      : "Không xác định được nguồn cho trích dẫn này"
    return <span title={explanation} aria-label={`${marker}: ${explanation}`} className="text-muted-foreground">{marker}</span>
  }
  const source = { ...resolution.source, key: sourceKey(resolution.source) }
  return (
    <SheetTrigger
      type="button"
      aria-label={`Xem nguồn ${marker}: ${source.file_name ?? "Tài liệu chưa có tên"}`}
      className="inline rounded px-0.5 font-medium text-primary underline decoration-primary/40 underline-offset-4 hover:bg-primary/10 focus-visible:outline-2 focus-visible:outline-ring"
      onClick={() => onSelect(source)}
    >{marker}</SheetTrigger>
  )
}

export function SourceGroups({ groups, selectedKey }: { groups: SourceGroup[]; selectedKey: string | null }) {
  return (
    <div className="space-y-5">
      {groups.map(group => (
        <section key={group.key} className="rounded-lg border p-3">
          <h3 className="break-words font-semibold">{group.fileName}</h3>
          {group.pages.map(page => (
            <div key={page.key} className="mt-3">
              <h4 className="text-xs font-medium text-muted-foreground">{page.label}</h4>
              <ul className="mt-2 space-y-2">
                {page.sources.map(source => (
                  <li key={source.key} data-source-key={source.key} data-selected={source.key === selectedKey || undefined}
                    className={cn("rounded-md border p-3", source.key === selectedKey && "border-primary bg-primary/5")}>
                    <p className="text-sm font-medium">
                      {source.ordinal === null ? "Trích dẫn đã lưu" : `Nguồn [${source.ordinal}]`}
                      {source.key === selectedKey && <span className="ml-2 text-primary">Đang xem</span>}
                    </p>
                    <details className="mt-2 text-xs text-muted-foreground">
                      <summary className="cursor-pointer focus-visible:outline-2 focus-visible:outline-ring">Định danh nguồn</summary>
                      <dl className="mt-2 space-y-2 break-all">
                        <div><dt>Document</dt><dd>{source.document_id}</dd></div>
                        <div><dt>Version</dt><dd>{source.version_id}</dd></div>
                        <div><dt>Chunk</dt><dd>{source.chunk_id}</dd></div>
                      </dl>
                    </details>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      ))}
    </div>
  )
}

export function CitationContent({ message }: { message: ChatViewMessage }) {
  const [selected, setSelected] = useState<CitationSource | null>(null)
  const panel = buildCitationPanel(message)
  // Selected identity is message-local. If metadata disappears, don't keep a stale target.
  const active = selected && panel.sources.find(source => source.key === selected.key)
  const groups = prioritizeSourceGroups(panel.groups, active?.key ?? null)
  return (
    <Sheet>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeCitationMarkers]}
        components={{
          button: ({ node, children }) => <CitationMarker message={message}
            ordinal={Number(node?.properties.dataCitationOrdinal)} marker={String(children)} onSelect={setSelected} />,
          p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
          ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
          ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
          blockquote: ({ children }) => <blockquote className="mt-3 border-l-2 border-primary/40 pl-3 text-muted-foreground">{children}</blockquote>,
          code: ({ children, className, ...props }) => <code className={cn("rounded bg-muted px-1 py-0.5 font-mono text-[0.9em]", className)} {...props}>{children}</code>,
          pre: ({ children }) => <pre className="my-3 overflow-x-auto rounded-lg bg-muted p-3 text-xs">{children}</pre>,
          a: ({ children, href }) => <a href={href} className="font-medium underline underline-offset-4" target="_blank" rel="noreferrer">{children}</a>,
        }}
      >{message.content}</ReactMarkdown>
      {panel.missingMetadata && (
        <p className="mt-3 text-xs text-muted-foreground">Chưa có thông tin để nối số trích dẫn với nguồn trong câu trả lời này.</p>
      )}
      {(panel.sources.length > 0 || panel.mapping.references.length > 0) && (
        <div className="mt-3 border-t pt-3">
          <SheetTrigger render={<Button type="button" variant="outline" size="sm" />} onClick={() => setSelected(null)}>
            Nguồn của câu trả lời ({panel.sources.length})
          </SheetTrigger>
        </div>
      )}
      <SheetContent className="w-full sm:w-[28rem] sm:max-w-[28rem]" showCloseButton={false}>
        <SheetHeader className="pr-16">
          <SheetTitle>Nguồn của câu trả lời</SheetTitle>
          <SheetDescription>
            {active ? `${active.file_name ?? "Tài liệu chưa có tên"}${active.pdf_page_number !== null ? ` — Trang ${active.pdf_page_number}` : ""}`
              : "Các nguồn trích dẫn thuộc câu trả lời này, nhóm theo tài liệu và trang."}
          </SheetDescription>
        </SheetHeader>
        <SheetClose render={<Button variant="ghost" size="sm" className="absolute right-3 top-3" />}>Đóng</SheetClose>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-6">
          {panel.missingMetadata && <p className="mb-4 text-sm text-muted-foreground">Lịch sử có thể lưu trích dẫn nhưng chưa đủ thông tin để xác định số [n]. Các trích dẫn đã lưu được hiển thị bên dưới.</p>}
          {groups.length > 0 ? <SourceGroups groups={groups} selectedKey={active?.key ?? null} />
            : <p className="text-sm text-muted-foreground">Chưa có thông tin nguồn cho các trích dẫn trong câu trả lời này.</p>}
          <p className="mt-4 text-xs text-muted-foreground">Chưa có bản xem trước hoặc đường dẫn mở tài liệu.</p>
        </div>
      </SheetContent>
    </Sheet>
  )
}
