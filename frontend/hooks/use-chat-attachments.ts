"use client"

import { useEffect, useRef, useState, useSyncExternalStore } from "react"
import { createApiClient } from "@/lib/api/client"
import { uploadDocument } from "@/lib/api/documents"
import { UploadController } from "@/lib/documents/upload-controller"

export interface ChatAttachment {
  id: string
  fingerprint: string
  file: File
  controller: UploadController
}

/** Local files stay in the composer; only indexed immutable references can be sent. */
export function useChatAttachments(apiBaseUrl: string | null) {
  const [attachments, setAttachments] = useState<ChatAttachment[]>([])
  const entries = useRef(new Map<string, ChatAttachment>())
  const allReady = useSyncExternalStore(listener => {
    const unsubscribers = attachments.map(entry => entry.controller.subscribe(listener))
    return () => unsubscribers.forEach(unsubscribe => unsubscribe())
  }, () => attachments.every(entry => {
    const result = entry.controller.getSnapshot().result
    return result?.status === "INDEXED" && result.activated
  }), () => true)

  useEffect(() => {
    const active = entries.current
    return () => {
      for (const entry of active.values()) entry.controller.dispose()
    }
  }, [])

  function choose(files: File[]) {
    if (!apiBaseUrl) return
    const api = createApiClient({ baseUrl: apiBaseUrl })
    for (const file of files) {
      const fingerprint = JSON.stringify([file.name, file.size, file.lastModified])
      if ([...entries.current.values()].some(entry => entry.fingerprint === fingerprint)) continue
      const id = crypto.randomUUID()
      const controller = new UploadController({ upload: (selected, signal) => uploadDocument(api, selected, signal) })
      controller.choose(file)
      entries.current.set(id, { id, fingerprint, file, controller })
      void controller.submit()
    }
    setAttachments([...entries.current.values()])
  }

  function remove(id: string) {
    const entry = entries.current.get(id)
    entries.current.delete(id)
    // Abort only the client wait. Never delete a server document or reattach a late result.
    entry?.controller.dispose()
    setAttachments([...entries.current.values()])
  }

  function clearSubmitted(submitted: readonly ChatAttachment[]) {
    for (const entry of submitted) {
      if (entries.current.get(entry.id) === entry) {
        entries.current.delete(entry.id)
        entry.controller.dispose()
      }
    }
    setAttachments([...entries.current.values()])
    return entries.current.size === 0
  }

  return { attachments, allReady, choose, remove, capture: () => [...entries.current.values()], clearSubmitted }
}
