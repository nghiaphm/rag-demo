"use client"

import { useCallback, useEffect, useId, useRef, useState, type ComponentProps } from "react"
import { SheetContent } from "@/components/ui/sheet"

// Tab-only UI preference; memory fallback when browser storage is unavailable.
let rememberedWidth: number | null = null
const storageKey = "rag:document-preview-width"
const defaultWidth = 576 // Existing sm:max-w-xl.

function bounds(viewport: number) {
  return { min: 320, max: Math.min(960, Math.max(defaultWidth, viewport * 0.75), viewport - 32) }
}

export function DocumentPreviewSheetContent({ open, children, ...props }: ComponentProps<typeof SheetContent> & { open: boolean }) {
  const instructionsId = useId()
  const panel = useRef<HTMLDivElement | null>(null)
  const drag = useRef<{ pointerId: number; x: number; width: number } | null>(null)
  const [preferredWidth, setPreferredWidth] = useState<number | null>(null)
  const [viewport, setViewport] = useState(0)
  const attach = useCallback((node: HTMLDivElement | null) => {
    panel.current = node
    if (node) {
      try {
        const saved = Number(window.sessionStorage.getItem(storageKey))
        if (Number.isFinite(saved) && saved >= 320 && saved <= 960) rememberedWidth = saved
      } catch { /* Keep the in-memory preference when storage is blocked. */ }
      setPreferredWidth(rememberedWidth)
      setViewport(window.innerWidth)
    }
  }, [])
  useEffect(() => {
    if (!open) return
    const resize = () => {
      drag.current = null
      setViewport(window.innerWidth)
    }
    window.addEventListener("resize", resize)
    return () => { window.removeEventListener("resize", resize); drag.current = null }
  }, [open])

  const desktop = viewport >= 640
  const { min, max } = bounds(viewport)
  const width = Math.min(max, Math.max(min, preferredWidth ?? defaultWidth))
  function changeWidth(value: number) {
    const limits = bounds(window.innerWidth)
    rememberedWidth = Math.round(Math.min(limits.max, Math.max(limits.min, value)))
    try { window.sessionStorage.setItem(storageKey, String(rememberedWidth)) }
    catch { /* Resizing still works when browser storage is blocked. */ }
    setPreferredWidth(rememberedWidth)
  }

  return <SheetContent {...props} ref={attach} style={desktop ? { width, maxWidth: max } : undefined}>
    {desktop && <div
      role="separator"
      aria-label="Điều chỉnh chiều rộng xem trước tài liệu"
      aria-orientation="vertical"
      aria-describedby={instructionsId}
      aria-valuemin={min}
      aria-valuemax={Math.round(max)}
      aria-valuenow={Math.round(width)}
      aria-valuetext={`${Math.round(width)} pixel`}
      tabIndex={0}
      className="absolute inset-y-0 -left-1 z-10 w-2 touch-none cursor-col-resize select-none rounded focus-visible:bg-primary/20 focus-visible:outline-2 focus-visible:outline-ring hover:bg-primary/15"
      onPointerDown={event => {
        if (event.button !== 0 || !panel.current) return
        event.preventDefault()
        event.currentTarget.focus()
        event.currentTarget.setPointerCapture(event.pointerId)
        drag.current = { pointerId: event.pointerId, x: event.clientX, width: panel.current.getBoundingClientRect().width }
      }}
      onPointerMove={event => {
        if (drag.current?.pointerId !== event.pointerId) return
        changeWidth(drag.current.width + drag.current.x - event.clientX)
      }}
      onPointerUp={event => {
        drag.current = null
        if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
      }}
      onLostPointerCapture={() => { drag.current = null }}
      onPointerCancel={() => { drag.current = null }}
      onKeyDown={event => {
        const step = event.shiftKey ? 64 : 16
        const next = event.key === "ArrowLeft" ? width + step : event.key === "ArrowRight" ? width - step
          : event.key === "Home" ? min : event.key === "End" ? max : null
        if (next !== null) { event.preventDefault(); changeWidth(next) }
      }}
    />}
    <span id={instructionsId} className="sr-only">Mũi tên trái để mở rộng, mũi tên phải để thu hẹp; Home về nhỏ nhất, End về lớn nhất.</span>
    {children}
  </SheetContent>
}
