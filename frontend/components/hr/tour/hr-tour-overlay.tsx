"use client"

import { usePathname } from "next/navigation"
import { useEffect, useId, useRef, useState } from "react"
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Compass,
  MessageSquareText,
  X,
} from "lucide-react"

import { useOptionalHrTour } from "@/components/hr/tour/hr-tour-provider"
import { Button } from "@/components/ui/button"
import {
  computePopoverPosition,
  computeSpotlightFrame,
  getTourProgressLabel,
  type TourRect,
} from "@/lib/hr/tour"
import { cn } from "@/lib/utils"
import type { HrTourTargetId } from "@/types/hr"

const POPOVER_ESTIMATE = { width: 368, height: 268 }

function measureTarget(targetId: HrTourTargetId): {
  element: HTMLElement | null
  rect: TourRect | null
} {
  if (typeof document === "undefined") return { element: null, rect: null }
  const element = document.querySelector<HTMLElement>(`[data-tour="${targetId}"]`)
  if (!element) return { element: null, rect: null }
  const box = element.getBoundingClientRect()
  if (box.width <= 0 || box.height <= 0) return { element, rect: null }
  return {
    element,
    rect: {
      top: box.top,
      left: box.left,
      width: box.width,
      height: box.height,
    },
  }
}

export function HrTourOverlay() {
  const tour = useOptionalHrTour()
  const pathname = usePathname()
  const titleId = useId()
  const descriptionId = useId()
  const popoverRef = useRef<HTMLDivElement>(null)
  const scrolledStepRef = useRef<string | null>(null)

  const [targetRect, setTargetRect] = useState<TourRect | null>(null)
  const [viewport, setViewport] = useState({ width: 1280, height: 800 })
  const [popoverSize, setPopoverSize] = useState(POPOVER_ESTIMATE)

  const isActive = Boolean(tour?.isActive && tour.currentStep)
  const showWelcomePrompt = Boolean(tour?.showWelcomePrompt)
  const currentStep = tour?.currentStep ?? null

  useEffect(() => {
    if (!isActive || !currentStep) {
      scrolledStepRef.current = null
      return
    }

    let cancelled = false
    let rafId = 0
    let attempts = 0
    let resizeObserver: ResizeObserver | null = null

    const syncViewport = () => {
      setViewport({
        width: window.innerWidth,
        height: window.innerHeight,
      })
      if (popoverRef.current) {
        const box = popoverRef.current.getBoundingClientRect()
        if (box.width > 0 && box.height > 0) {
          setPopoverSize({ width: box.width, height: box.height })
        }
      }
    }

    const updateMeasurement = () => {
      if (cancelled) return
      syncViewport()

      if (currentStep.route && pathname !== currentStep.route) {
        setTargetRect(null)
        return
      }

      const { element, rect } = measureTarget(currentStep.targetId)
      if (!element || !rect) {
        setTargetRect(null)
        if (attempts < 24) {
          attempts += 1
          rafId = window.setTimeout(updateMeasurement, 80)
        }
        return
      }

      if (scrolledStepRef.current !== currentStep.id) {
        scrolledStepRef.current = currentStep.id
        element.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" })
        // Đo lại vị trí sau khi scrollIntoView và transition hoàn tất
        rafId = window.setTimeout(() => {
          if (cancelled) return
          const settled = measureTarget(currentStep.targetId)
          setTargetRect(settled.rect)
        }, 220)
      }

      setTargetRect(rect)

      if (!resizeObserver && typeof ResizeObserver !== "undefined") {
        resizeObserver = new ResizeObserver(() => {
          if (cancelled) return
          const latest = measureTarget(currentStep.targetId)
          setTargetRect(latest.rect)
        })
        resizeObserver.observe(element)
      }
    }

    const initialTimer = window.setTimeout(updateMeasurement, currentStep.opensChatbot ? 240 : 40)
    window.addEventListener("resize", updateMeasurement)
    window.addEventListener("scroll", updateMeasurement, true)

    return () => {
      cancelled = true
      window.clearTimeout(initialTimer)
      window.clearTimeout(rafId)
      resizeObserver?.disconnect()
      window.removeEventListener("resize", updateMeasurement)
      window.removeEventListener("scroll", updateMeasurement, true)
    }
  }, [isActive, currentStep, pathname])

  useEffect(() => {
    if (!isActive || !tour) return

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault()
        tour.skipTour()
      } else if (event.key === "ArrowRight") {
        event.preventDefault()
        tour.nextStep()
      } else if (event.key === "ArrowLeft") {
        event.preventDefault()
        tour.prevStep()
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [isActive, tour])

  if (!tour) return null

  if (showWelcomePrompt) {
    return (
      <aside
        aria-label="Gợi ý tham quan nhanh HR Portal"
        className="fixed inset-x-4 bottom-20 z-40 sm:inset-x-auto sm:bottom-5 sm:left-5 sm:w-[22.5rem]"
      >
        <div className="rounded-xl border border-primary/25 bg-card p-4 shadow-lg">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-start gap-3">
              <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
                <Compass className="size-4" aria-hidden="true" />
              </span>
              <div className="space-y-1">
                <p className="font-heading text-sm font-semibold tracking-tight text-foreground">
                  Khám phá nhanh HR Portal
                </p>
                <p className="text-xs leading-5 text-muted-foreground">
                  Đi qua {tour.steps.length} bước tương tác từ Dashboard nhân sự, Kho tài liệu đến Trợ lý RAG có trích dẫn.
                </p>
              </div>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              aria-label="Đóng gợi ý tham quan"
              onClick={tour.dismissWelcomePrompt}
            >
              <X className="size-3.5" aria-hidden="true" />
            </Button>
          </div>
          <div className="mt-3.5 flex items-center justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-8 text-xs text-muted-foreground"
              onClick={tour.dismissWelcomePrompt}
            >
              Để sau
            </Button>
            <Button
              type="button"
              size="sm"
              className="h-8 gap-1.5 text-xs"
              onClick={() => tour.startTour(0)}
            >
              <Compass className="size-3.5" aria-hidden="true" />
              <span>Bắt đầu Tour</span>
            </Button>
          </div>
        </div>
      </aside>
    )
  }

  if (!isActive || !currentStep) return null

  const spotlight = computeSpotlightFrame(targetRect, viewport, 8)
  const popoverPos = computePopoverPosition(
    targetRect,
    viewport,
    popoverSize,
    currentStep.placement,
  )
  const isFirstStep = tour.currentStepIndex === 0
  const isLastStep = tour.currentStepIndex >= tour.steps.length - 1
  const progressLabel = getTourProgressLabel(tour.currentStepIndex, tour.steps)

  return (
    <div className="pointer-events-none fixed inset-0 z-[55]">
      {/* Lớp phủ mờ nền nhưng giữ tương tác với vùng đang highlight */}
      <div
        aria-hidden="true"
        className={cn(
          "pointer-events-none fixed inset-0 transition-opacity duration-200",
          spotlight ? "bg-transparent" : "bg-[#10201c]/55",
        )}
      />

      {/* Khung spotlight đục sáng phần tử mục tiêu */}
      {spotlight && (
        <div
          aria-hidden="true"
          className="pointer-events-none fixed rounded-xl ring-2 ring-primary ring-offset-2 ring-offset-background transition-all duration-200 ease-out"
          style={{
            top: spotlight.top,
            left: spotlight.left,
            width: spotlight.width,
            height: spotlight.height,
            boxShadow: "0 0 0 9999px rgba(16, 32, 28, 0.56)",
          }}
        />
      )}

      {/* Thẻ hướng dẫn bước hiện tại */}
      <div
        ref={popoverRef}
        role="dialog"
        aria-modal="false"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        className="pointer-events-auto fixed z-[60] w-[min(23rem,calc(100vw-2rem))] rounded-xl border border-border bg-card p-5 text-card-foreground shadow-xl transition-all duration-200 ease-out"
        style={{
          top: popoverPos.top,
          left: popoverPos.left,
        }}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-xs font-medium text-primary">
              <span>{progressLabel}</span>
              <span aria-hidden="true" className="text-border">
                /
              </span>
              <span className="text-muted-foreground">{currentStep.eyebrow}</span>
            </div>
            <h2
              id={titleId}
              className="font-heading text-base font-semibold tracking-tight text-foreground"
            >
              {currentStep.title}
            </h2>
          </div>

          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label="Thoát Product Tour"
            onClick={tour.skipTour}
          >
            <X className="size-3.5" aria-hidden="true" />
          </Button>
        </div>

        <p
          id={descriptionId}
          className="mt-2.5 text-sm leading-6 text-muted-foreground"
        >
          {currentStep.description}
        </p>

        {currentStep.actionHint && (
          <p className="mt-3 rounded-lg border border-primary/15 bg-accent/55 px-3 py-2 text-xs leading-5 text-accent-foreground">
            {currentStep.actionHint}
          </p>
        )}

        {currentStep.suggestedPrompt && (
          <div className="mt-3">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full justify-center gap-1.5 border-primary/30 bg-accent/40 text-xs font-medium text-accent-foreground hover:bg-accent"
              onClick={tour.trySuggestedPrompt}
            >
              <MessageSquareText className="size-3.5 text-primary" aria-hidden="true" />
              <span>Điền câu hỏi mẫu vào khung chat</span>
            </Button>
          </div>
        )}

        {/* Thanh tiến trình các bước */}
        <div className="mt-4 flex items-center gap-1.5" aria-hidden="true">
          {tour.steps.map((step, index) => {
            const active = index === tour.currentStepIndex
            const passed = index < tour.currentStepIndex
            return (
              <button
                key={step.id}
                type="button"
                tabIndex={-1}
                onClick={() => tour.goToStep(index)}
                className={cn(
                  "h-1.5 flex-1 rounded-full transition-all",
                  active
                    ? "bg-primary"
                    : passed
                      ? "bg-primary/45 hover:bg-primary/65"
                      : "bg-muted hover:bg-muted-foreground/25",
                )}
              />
            )
          })}
        </div>

        <div className="mt-4 flex items-center justify-between gap-2 border-t pt-3.5">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 px-2 text-xs text-muted-foreground"
            onClick={tour.skipTour}
          >
            Bỏ qua
          </Button>

          <div className="flex items-center gap-1.5">
            {!isFirstStep && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8 gap-1 text-xs"
                onClick={tour.prevStep}
              >
                <ArrowLeft className="size-3.5" aria-hidden="true" />
                <span>Quay lại</span>
              </Button>
            )}
            <Button
              type="button"
              size="sm"
              className="h-8 gap-1 text-xs"
              onClick={isLastStep ? tour.completeTour : tour.nextStep}
            >
              {isLastStep ? (
                <>
                  <Check className="size-3.5" aria-hidden="true" />
                  <span>Hoàn tất</span>
                </>
              ) : (
                <>
                  <span>Tiếp theo</span>
                  <ArrowRight className="size-3.5" aria-hidden="true" />
                </>
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
