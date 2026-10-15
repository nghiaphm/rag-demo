"use client"

import { useEffect, useRef, useState } from "react"
import { Copy } from "lucide-react"
import { Button } from "@/components/ui/button"
import { copyText } from "@/lib/chat/clipboard"

export function CopyButton({ text, label, disabled = false }: { text: string; label: string; disabled?: boolean }) {
  const [status, setStatus] = useState<"idle" | "copying" | "copied" | "error">("idle")
  const mounted = useRef(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; if (timer.current) clearTimeout(timer.current) }
  }, [])
  async function copy() {
    if (timer.current) clearTimeout(timer.current)
    setStatus("copying")
    try {
      await copyText(text, navigator.clipboard)
      if (mounted.current) setStatus("copied")
    } catch {
      if (mounted.current) setStatus("error")
    }
    if (mounted.current) timer.current = setTimeout(() => setStatus(current => current === "error" ? current : "idle"), 3000)
  }
  return <div className="flex flex-wrap items-center gap-2">
    <Button type="button" variant="ghost" size="sm" aria-label={label} disabled={disabled || status === "copying"} onClick={() => void copy()}>
      <Copy aria-hidden="true" />Sao chép
    </Button>
    <span role="status" className="text-xs">
      {status === "copied" ? "Đã sao chép" : status === "error" ? "Không thể sao chép. Hãy chọn nội dung và sao chép thủ công." : ""}
    </span>
  </div>
}
