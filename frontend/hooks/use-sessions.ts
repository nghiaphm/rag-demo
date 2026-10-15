"use client"

import { useEffect, useMemo, useSyncExternalStore } from "react"

import { createApiClient } from "@/lib/api/client"
import {
  createSession,
  getSession,
  isSessionId,
  listSessionMessages,
  listSessions,
  updateSessionTitle,
  deleteSession,
} from "@/lib/api/sessions"
import { HistoryController } from "@/lib/sessions/history"
import { SessionLookupController, SessionsController } from "@/lib/sessions/controller"
import { subscribeSessionList } from "@/lib/sessions/invalidation"

export function useSessions(apiBaseUrl: string) {
  const controller = useMemo(() => {
    const api = createApiClient({ baseUrl: apiBaseUrl })
    return new SessionsController({
      list: (signal, query) => listSessions(api, query ?? { offset: 0, limit: 50 }, signal),
      create: (signal) => createSession(api, {}, signal),
      rename: (id, title, signal) => updateSessionTitle(api, id, title, signal),
      remove: (id, signal) => deleteSession(api, id, signal),
    })
  }, [apiBaseUrl])
  const state = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot
  )

  useEffect(() => {
    const unsubscribe = subscribeSessionList(apiBaseUrl, controller.invalidate)
    void controller.load()
    return () => { unsubscribe(); controller.dispose() }
  }, [controller, apiBaseUrl])

  return { ...state, reload: controller.load, loadMore: controller.loadMore, createNew: controller.createNew,
    rename: controller.rename, remove: controller.remove }
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
