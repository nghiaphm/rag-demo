"use client"

import { useEffect, useMemo, useSyncExternalStore } from "react"

import { createApiClient } from "@/lib/api/client"
import {
  createSession,
  getSession,
  isSessionId,
  listSessionMessages,
  listSessions,
} from "@/lib/api/sessions"
import { HistoryController } from "@/lib/sessions/history"
import { SessionLookupController, SessionsController } from "@/lib/sessions/controller"

export function useSessions(apiBaseUrl: string) {
  const controller = useMemo(() => {
    const api = createApiClient({ baseUrl: apiBaseUrl })
    return new SessionsController({
      list: (signal) => listSessions(api, { offset: 0, limit: 50 }, signal),
      create: (signal) => createSession(api, {}, signal),
    })
  }, [apiBaseUrl])
  const state = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot
  )

  useEffect(() => {
    void controller.load()
    return () => controller.dispose()
  }, [controller])

  return { ...state, reload: controller.load, createNew: controller.createNew }
}

export function useSession(apiBaseUrl: string, sessionId: string) {
  const controller = useMemo(() => {
    const api = createApiClient({ baseUrl: apiBaseUrl })
    return new SessionLookupController(sessionId, {
      isValidId: isSessionId,
      get: (id, signal) => getSession(api, id, signal),
    })
  }, [apiBaseUrl, sessionId])
  const state = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot
  )

  useEffect(() => {
    void controller.load()
    return () => controller.dispose()
  }, [controller])

  return { ...state, reload: controller.load }
}

export function useSessionHistory(apiBaseUrl: string, sessionId: string) {
  const controller = useMemo(() => {
    const api = createApiClient({ baseUrl: apiBaseUrl })
    return new HistoryController(sessionId, {
      list: (id, query, signal) => listSessionMessages(api, id, query, signal),
    })
  }, [apiBaseUrl, sessionId])
  const state = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot
  )

  useEffect(() => {
    void controller.load()
    return () => controller.dispose()
  }, [controller])

  return { ...state, reload: controller.load }
}
