"use client"

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react"
import type { HrPageContext } from "@/types/hr"

export interface OpenHrChatbotOptions {
  prompt?: string
  pageContext?: HrPageContext
}

export interface HrChatbotContextValue {
  isOpen: boolean
  activeSessionId: string | null
  pageContext: HrPageContext | null
  draftPrompt: string | null
  openWidget: (options?: OpenHrChatbotOptions) => void
  closeWidget: () => void
  toggleWidget: () => void
  setActiveSessionId: (sessionId: string | null) => void
  setPageContext: (context: HrPageContext | null) => void
  clearDraftPrompt: () => void
}

const HrChatbotContext = createContext<HrChatbotContextValue | null>(null)

/**
 * UI & navigation context only for /hr/* pages.
 * Never owns ChatController, fetch calls, message arrays, or SSE parsing.
 */
export function HrChatbotProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false)
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [pageContext, setPageContext] = useState<HrPageContext | null>(null)
  const [draftPrompt, setDraftPrompt] = useState<string | null>(null)

  const openWidget = useCallback((options?: OpenHrChatbotOptions) => {
    if (options?.pageContext) setPageContext(options.pageContext)
    if (options?.prompt !== undefined) setDraftPrompt(options.prompt)
    setIsOpen(true)
  }, [])

  const closeWidget = useCallback(() => {
    setIsOpen(false)
  }, [])

  const toggleWidget = useCallback(() => {
    setIsOpen((prev) => !prev)
  }, [])

  const clearDraftPrompt = useCallback(() => {
    setDraftPrompt(null)
  }, [])

  const value = useMemo<HrChatbotContextValue>(
    () => ({
      isOpen,
      activeSessionId,
      pageContext,
      draftPrompt,
      openWidget,
      closeWidget,
      toggleWidget,
      setActiveSessionId,
      setPageContext,
      clearDraftPrompt,
    }),
    [
      isOpen,
      activeSessionId,
      pageContext,
      draftPrompt,
      openWidget,
      closeWidget,
      toggleWidget,
      clearDraftPrompt,
    ]
  )

  return (
    <HrChatbotContext.Provider value={value}>
      {children}
    </HrChatbotContext.Provider>
  )
}

export function useHrChatbot(): HrChatbotContextValue {
  const context = useContext(HrChatbotContext)
  if (!context) {
    throw new Error("useHrChatbot phải được gọi bên trong HrChatbotProvider")
  }
  return context
}
