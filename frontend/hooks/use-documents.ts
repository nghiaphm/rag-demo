"use client"

import { useEffect, useMemo, useSyncExternalStore } from "react"
import { createApiClient } from "@/lib/api/client"
import { getDocument, listDocuments } from "@/lib/api/documents"
import { DocumentsController } from "@/lib/documents/controller"

export function useDocuments(apiBaseUrl: string) {
  const controller = useMemo(() => {
    const api = createApiClient({ baseUrl: apiBaseUrl })
    return new DocumentsController({
      list: (query, signal) => listDocuments(api, query, signal),
      get: (id, signal) => getDocument(api, id, signal),
    })
  }, [apiBaseUrl])
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot)
  useEffect(() => {
    void controller.reload()
    return () => controller.dispose()
  }, [controller])
  return { state, controller }
}
