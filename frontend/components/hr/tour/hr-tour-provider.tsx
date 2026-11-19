"use client"

import { usePathname, useRouter } from "next/navigation"
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"

import { useHrChatbot } from "@/components/hr/layout/hr-chatbot-provider"
import { getHrTourSteps, HR_PRODUCT_TOUR_STEPS } from "@/fixtures/hr-tour"
import {
  getNextTourStepIndex,
  getPrevTourStepIndex,
  readTourCompletionState,
  shouldAutoPromptHrTour,
  writeTourCompletionState,
} from "@/lib/hr/tour"
import type { HrTourScope, HrTourStep } from "@/types/hr"

export type HrTourStatus = "idle" | "prompt" | "active"

export interface HrTourContextValue {
  status: HrTourStatus
  scope: HrTourScope
  isActive: boolean
  showWelcomePrompt: boolean
  steps: readonly HrTourStep[]
  currentStepIndex: number
  currentStep: HrTourStep | null
  startTour: (startIndex?: number, scope?: HrTourScope) => void
  nextStep: () => void
  prevStep: () => void
  goToStep: (index: number) => void
  skipTour: () => void
  completeTour: () => void
  dismissWelcomePrompt: () => void
  trySuggestedPrompt: () => void
}

const HrTourContext = createContext<HrTourContextValue | null>(null)

export function HrTourProvider({
  children,
  steps: customSteps,
}: {
  children: ReactNode
  steps?: readonly HrTourStep[]
}) {
  const pathname = usePathname()
  const router = useRouter()
  const { openWidget, closeWidget } = useHrChatbot()

  const [status, setStatus] = useState<HrTourStatus>("idle")
  const [scope, setScope] = useState<HrTourScope>("all")
  const [currentStepIndex, setCurrentStepIndex] = useState(0)
  const openedWidgetByTourRef = useRef(false)
  const autoPromptCheckedRef = useRef(false)

  const activeSteps = useMemo(
    () => (customSteps ? customSteps : getHrTourSteps(scope)),
    [customSteps, scope],
  )
  const currentStep = status === "active" ? (activeSteps[currentStepIndex] ?? null) : null

  const syncStepSideEffects = useCallback(
    (targetStep: HrTourStep) => {
      if (targetStep.route && pathname !== targetStep.route) {
        router.push(targetStep.route)
      }
      if (targetStep.opensChatbot) {
        openedWidgetByTourRef.current = true
        // Mở ngăn kéo Trợ lý HR mà không ghi đè pageContext đang có.
        openWidget()
      } else if (openedWidgetByTourRef.current) {
        openedWidgetByTourRef.current = false
        closeWidget()
      }
    },
    [pathname, router, openWidget, closeWidget],
  )

  useEffect(() => {
    if (autoPromptCheckedRef.current) return
    if (typeof window === "undefined") return

    autoPromptCheckedRef.current = true
    const persisted = readTourCompletionState(window.localStorage)
    if (!shouldAutoPromptHrTour(pathname, persisted)) return

    const timer = window.setTimeout(() => {
      setStatus((prev) => (prev === "idle" ? "prompt" : prev))
    }, 350)
    return () => window.clearTimeout(timer)
  }, [pathname])

  const startTour = useCallback(
    (startIndex = 0, nextScope: HrTourScope = "all") => {
      const nextSteps = customSteps ?? getHrTourSteps(nextScope)
      if (nextSteps.length === 0) return
      const bounded = Math.min(Math.max(startIndex, 0), nextSteps.length - 1)
      const targetStep = nextSteps[bounded]
      setScope(nextScope)
      setCurrentStepIndex(bounded)
      setStatus("active")
      syncStepSideEffects(targetStep)
    },
    [customSteps, syncStepSideEffects],
  )

  const goToStep = useCallback(
    (index: number) => {
      if (activeSteps.length === 0) return
      const bounded = Math.min(Math.max(index, 0), activeSteps.length - 1)
      const targetStep = activeSteps[bounded]
      setCurrentStepIndex(bounded)
      setStatus("active")
      syncStepSideEffects(targetStep)
    },
    [activeSteps, syncStepSideEffects],
  )

  const completeTour = useCallback(() => {
    setStatus("idle")
    if (openedWidgetByTourRef.current) {
      openedWidgetByTourRef.current = false
      closeWidget()
    }
    if (typeof window !== "undefined") {
      writeTourCompletionState(window.localStorage, "completed")
    }
  }, [closeWidget])

  const skipTour = useCallback(() => {
    setStatus("idle")
    if (openedWidgetByTourRef.current) {
      openedWidgetByTourRef.current = false
      closeWidget()
    }
    if (typeof window !== "undefined") {
      writeTourCompletionState(window.localStorage, "dismissed")
    }
  }, [closeWidget])

  const dismissWelcomePrompt = useCallback(() => {
    setStatus((prev) => (prev === "prompt" ? "idle" : prev))
    if (typeof window !== "undefined") {
      writeTourCompletionState(window.localStorage, "dismissed")
    }
  }, [])

  const nextStep = useCallback(() => {
    const nextIndex = getNextTourStepIndex(currentStepIndex, activeSteps.length)
    if (nextIndex === null) {
      completeTour()
      return
    }
    goToStep(nextIndex)
  }, [currentStepIndex, activeSteps.length, completeTour, goToStep])

  const prevStep = useCallback(() => {
    const prevIndex = getPrevTourStepIndex(currentStepIndex)
    if (prevIndex === null) return
    goToStep(prevIndex)
  }, [currentStepIndex, goToStep])

  const trySuggestedPrompt = useCallback(() => {
    const prompt = currentStep?.suggestedPrompt
    openedWidgetByTourRef.current = false
    setStatus("idle")
    if (typeof window !== "undefined") {
      writeTourCompletionState(window.localStorage, "completed")
    }
    openWidget(prompt ? { prompt } : undefined)
  }, [currentStep, openWidget])

  const value = useMemo<HrTourContextValue>(
    () => ({
      status,
      scope,
      isActive: status === "active",
      showWelcomePrompt: status === "prompt",
      steps: activeSteps.length > 0 ? activeSteps : HR_PRODUCT_TOUR_STEPS,
      currentStepIndex,
      currentStep,
      startTour,
      nextStep,
      prevStep,
      goToStep,
      skipTour,
      completeTour,
      dismissWelcomePrompt,
      trySuggestedPrompt,
    }),
    [
      status,
      scope,
      activeSteps,
      currentStepIndex,
      currentStep,
      startTour,
      nextStep,
      prevStep,
      goToStep,
      skipTour,
      completeTour,
      dismissWelcomePrompt,
      trySuggestedPrompt,
    ],
  )

  return <HrTourContext.Provider value={value}>{children}</HrTourContext.Provider>
}

export function useHrTour(): HrTourContextValue {
  const context = useContext(HrTourContext)
  if (!context) {
    throw new Error("useHrTour phải được gọi bên trong HrTourProvider")
  }
  return context
}

export function useOptionalHrTour(): HrTourContextValue | null {
  return useContext(HrTourContext)
}
