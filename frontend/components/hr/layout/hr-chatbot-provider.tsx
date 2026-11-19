"use client"

import { usePathname } from "next/navigation"
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
import {
  getHrRouteDisplayTitle,
  resolveHrRouteFromPathname,
} from "@/lib/hr/page-context"
import type { HrPageContext, HrPageRoute } from "@/types/hr"

export interface OpenHrChatbotOptions {
  prompt?: string
  pageContext?: HrPageContext
}

export type HrRuntimePageContextInput = Omit<HrPageContext, "route" | "title"> & {
  route?: HrPageRoute
  title?: string
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
  const pathname = usePathname()
  const activeRoute = resolveHrRouteFromPathname(pathname)
  const [isOpen, setIsOpen] = useState(false)
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [customPageContext, setPageContext] = useState<HrPageContext | null>(null)
  const [draftPrompt, setDraftPrompt] = useState<string | null>(null)

  const pageContext = useMemo<HrPageContext>(() => {
    const defaultTitle = getHrRouteDisplayTitle(activeRoute)
    if (customPageContext && customPageContext.route === activeRoute) {
      return {
        ...customPageContext,
        route: activeRoute,
        title: customPageContext.title?.trim() || defaultTitle,
      }
    }
    return {
      route: activeRoute,
      title: defaultTitle,
    }
  }, [activeRoute, customPageContext])

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

/**
 * Declarative hook để từng trang HR đăng ký trạng thái thực thi sống (live runtime state)
 * mà không cần hardcode lại `route` hay `title` từ `HR_ROUTE_MANIFEST`.
 */
export function useHrPageContext(input?: HrRuntimePageContextInput | null): void {
  const pathname = usePathname()
  const { setPageContext } = useHrChatbot()
  const resolvedRoute = input?.route ?? resolveHrRouteFromPathname(pathname)
  const resolvedTitle = input?.title?.trim() || getHrRouteDisplayTitle(resolvedRoute)

  const normalized = useMemo<HrPageContext>(() => {
    return {
      route: resolvedRoute,
      title: resolvedTitle,
      ...(input?.purpose ? { purpose: input.purpose } : {}),
      ...(input?.selectedDocumentId ? { selectedDocumentId: input.selectedDocumentId } : {}),
      ...(input?.selectedDocumentName ? { selectedDocumentName: input.selectedDocumentName } : {}),
      ...(input?.selectedCategory ? { selectedCategory: input.selectedCategory } : {}),
      ...(input?.searchQuery ? { searchQuery: input.searchQuery } : {}),
      ...(input?.liveFeatures && input.liveFeatures.length > 0
        ? { liveFeatures: [...input.liveFeatures] }
        : {}),
    }
  }, [input, resolvedRoute, resolvedTitle])

  const serializedKey = JSON.stringify(normalized)
  const lastKeyRef = useRef<string | null>(null)

  useEffect(() => {
    if (lastKeyRef.current === serializedKey) return
    lastKeyRef.current = serializedKey
    setPageContext(normalized)
  }, [normalized, serializedKey, setPageContext])
}
