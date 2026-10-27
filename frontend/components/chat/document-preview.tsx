"use client"

import { useEffect, useState } from "react"
import { readTextPreview } from "@/lib/documents/text-preview"

type PreviewState = { phase: "loading" } | { phase: "ready"; text: string; truncated: boolean } | { phase: "error"; error: string }

function TextPreview({ file }: { file: File }) {
  const [state, setState] = useState<PreviewState>({ phase: "loading" })
  useEffect(() => {
    let active = true
    void readTextPreview(file).then(result => {
      if (active) setState({ phase: "ready", ...result })
    }, error => {
      if (active) setState({ phase: "error", error: error instanceof Error ? error.message : "Không thể đọc file." })
    })
    return () => { active = false }
  }, [file])
  if (state.phase === "loading") return <p role="status">Đang đọc bản xem trước…</p>
  if (state.phase === "error") return <p role="alert" className="text-destructive">{state.error}</p>
  return <>
    {state.truncated && <p role="status" className="mb-3 text-muted-foreground">Chỉ hiển thị tối đa 256 KiB đầu tiên. File gốc dùng để upload không bị cắt.</p>}
    <pre aria-label="Nội dung tài liệu" tabIndex={0} className="whitespace-pre-wrap break-words rounded-lg border bg-muted/40 p-3 font-mono text-xs leading-6 focus-visible:outline-2 focus-visible:outline-ring">{state.text}</pre>
  </>
}

export function DocumentPreview({ file }: { file: File }) {
  if (!file.name.toLowerCase().endsWith(".txt")) return <p role="status">Chưa hỗ trợ xem trước định dạng này. Hiện chỉ hỗ trợ TXT trên thiết bị; không có nội dung giả lập.</p>
  return <TextPreview file={file} />
}
