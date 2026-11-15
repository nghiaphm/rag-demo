"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { Files, Filter, LoaderCircle, RotateCcw, Search } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { createApiClient } from "@/lib/api/client"
import { listDocuments } from "@/lib/api/documents"
import { safeApiErrorMessage } from "@/lib/api/error-ux"
import { updateSessionScope } from "@/lib/api/sessions"
import type { DocumentInfo } from "@/types/document"
import type { SessionScopeMode, SessionScopeResponse } from "@/types/sessions"

interface DocumentScopeSelectorProps {
  apiBaseUrl: string
  sessionId: string | null
  scope: SessionScopeResponse
  disabled?: boolean
  onScopeChange: (scope: SessionScopeResponse) => void
}

export function DocumentScopeSelector({
  apiBaseUrl,
  sessionId,
  scope,
  disabled = false,
  onScopeChange,
}: DocumentScopeSelectorProps) {
  const [open, setOpen] = useState(false)
  const [documents, setDocuments] = useState<readonly DocumentInfo[]>([])
  const [loadStatus, setLoadStatus] = useState<"idle" | "loading" | "ready" | "error">("idle")
  const [loadError, setLoadError] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [draftMode, setDraftMode] = useState<SessionScopeMode>(scope.mode)
  const [draftIds, setDraftIds] = useState<Set<string>>(() => new Set(scope.document_ids))
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const mutationAbort = useRef<AbortController | null>(null)

  useEffect(() => () => { mutationAbort.current?.abort() }, [])

  useEffect(() => {
    if (!open) return
    const abort = new AbortController()
    const api = createApiClient({ baseUrl: apiBaseUrl })
    void listDocuments(api, { offset: 0, limit: 500, include_deleted: false }, abort.signal)
      .then((items) => {
        if (abort.signal.aborted) return
        setDocuments(items.filter(item => item.status === "INDEXED" && item.active_version_id !== null))
        setLoadStatus("ready")
      })
      .catch((error) => {
        if (abort.signal.aborted) return
        setLoadError(safeApiErrorMessage(error, "Không thể tải danh sách tài liệu."))
        setLoadStatus("error")
      })
    return () => abort.abort()
  }, [open, apiBaseUrl])

  const filteredDocuments = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return documents
    return documents.filter(doc =>
      doc.file_name.toLowerCase().includes(query) || doc.document_id.toLowerCase().includes(query)
    )
  }, [documents, search])

  function openDialog() {
    setDraftMode(scope.mode)
    setDraftIds(new Set(scope.document_ids))
    setSearch("")
    setSaveError(null)
    setLoadStatus("loading")
    setLoadError(null)
    setOpen(true)
  }

  function toggleDocument(documentId: string) {
    setDraftMode("SELECTED_DOCUMENTS")
    setDraftIds((previous) => {
      const next = new Set(previous)
      if (next.has(documentId)) next.delete(documentId)
      else next.add(documentId)
      return next
    })
  }

  function selectAllFiltered() {
    setDraftMode("SELECTED_DOCUMENTS")
    setDraftIds((previous) => {
      const next = new Set(previous)
      for (const doc of filteredDocuments) next.add(doc.document_id)
      return next
    })
  }

  function clearSelection() {
    setDraftIds(new Set())
  }

  async function persistScope(nextScope: SessionScopeResponse, closeDialogOnSuccess: boolean) {
    if (saving || disabled) return
    if (!sessionId) {
      onScopeChange(nextScope)
      if (closeDialogOnSuccess) setOpen(false)
      return
    }
    mutationAbort.current?.abort()
    const abort = new AbortController()
    mutationAbort.current = abort
    setSaving(true)
    setSaveError(null)
    try {
      const api = createApiClient({ baseUrl: apiBaseUrl })
      const updated = await updateSessionScope(api, sessionId, nextScope, abort.signal)
      if (abort.signal.aborted) return
      onScopeChange(updated.scope)
      if (closeDialogOnSuccess) setOpen(false)
    } catch (error) {
      if (abort.signal.aborted) return
      setSaveError(safeApiErrorMessage(error, "Không thể cập nhật phạm vi tài liệu."))
    } finally {
      if (mutationAbort.current === abort) mutationAbort.current = null
      setSaving(false)
    }
  }

  async function applySelection() {
    const nextScope: SessionScopeResponse = draftMode === "ALL_ACTIVE"
      ? { mode: "ALL_ACTIVE", document_ids: [] }
      : { mode: "SELECTED_DOCUMENTS", document_ids: Array.from(draftIds) }
    if (nextScope.mode === "SELECTED_DOCUMENTS" && nextScope.document_ids.length === 0) return
    await persistScope(nextScope, true)
  }

  const isSelectedMode = scope.mode === "SELECTED_DOCUMENTS" && scope.document_ids.length > 0
  const canApply = !saving && (draftMode === "ALL_ACTIVE" || draftIds.size > 0)

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge variant={isSelectedMode ? "default" : "secondary"} className="gap-1.5 font-normal">
        {isSelectedMode ? <Filter className="size-3" aria-hidden="true" /> : <Files className="size-3" aria-hidden="true" />}
        <span>
          {isSelectedMode
            ? `Phạm vi: ${scope.document_ids.length} tài liệu đã chọn`
            : "Phạm vi: Tất cả tài liệu"}
        </span>
      </Badge>

      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-7 px-2.5 text-xs"
        disabled={disabled || saving}
        onClick={openDialog}
      >
        {isSelectedMode ? "Điều chỉnh phạm vi" : "Chọn tài liệu"}
      </Button>

      {isSelectedMode && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 gap-1 px-2 text-xs text-muted-foreground"
          disabled={disabled || saving}
          aria-label="Đặt lại phạm vi về tất cả tài liệu"
          onClick={() => void persistScope({ mode: "ALL_ACTIVE", document_ids: [] }, false)}
        >
          <RotateCcw className="size-3" aria-hidden="true" />
          <span>Tất cả</span>
        </Button>
      )}

      {saveError && !open && (
        <p role="alert" className="w-full text-xs text-destructive">{saveError}</p>
      )}

      <Dialog open={open} onOpenChange={(nextOpen) => { if (!saving) setOpen(nextOpen) }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Phạm vi tài liệu truy vấn</DialogTitle>
            <DialogDescription>
              Chọn tìm kiếm trên toàn bộ thư viện hoặc giới hạn theo danh sách tài liệu cụ thể cho phiên trò chuyện này.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2" role="radiogroup" aria-label="Chế độ phạm vi tài liệu">
              <button
                type="button"
                role="radio"
                aria-checked={draftMode === "ALL_ACTIVE"}
                onClick={() => setDraftMode("ALL_ACTIVE")}
                className={`rounded-lg border p-3 text-left transition-colors ${
                  draftMode === "ALL_ACTIVE"
                    ? "border-primary bg-primary/5 ring-1 ring-primary"
                    : "border-border hover:bg-muted/50"
                }`}
              >
                <p className="text-sm font-medium">Tất cả tài liệu (ALL_ACTIVE)</p>
                <p className="mt-1 text-xs text-muted-foreground">Truy vấn toàn bộ tài liệu đang ở trạng thái INDEXED.</p>
              </button>

              <button
                type="button"
                role="radio"
                aria-checked={draftMode === "SELECTED_DOCUMENTS"}
                onClick={() => setDraftMode("SELECTED_DOCUMENTS")}
                className={`rounded-lg border p-3 text-left transition-colors ${
                  draftMode === "SELECTED_DOCUMENTS"
                    ? "border-primary bg-primary/5 ring-1 ring-primary"
                    : "border-border hover:bg-muted/50"
                }`}
              >
                <p className="text-sm font-medium">Chọn tài liệu (SELECTED)</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Chỉ truy vấn trong các tài liệu được đánh dấu ({draftIds.size} đã chọn).
                </p>
              </button>
            </div>

            {draftMode === "SELECTED_DOCUMENTS" && (
              <div className="space-y-2.5 rounded-lg border p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="relative min-w-44 flex-1">
                    <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
                    <Input
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                      placeholder="Tìm tên tài liệu…"
                      aria-label="Tìm tên tài liệu"
                      className="h-8 pl-8 text-xs"
                    />
                  </div>
                  <Button type="button" variant="ghost" size="sm" className="h-8 px-2 text-xs" onClick={selectAllFiltered} disabled={filteredDocuments.length === 0}>
                    Chọn tất cả
                  </Button>
                  <Button type="button" variant="ghost" size="sm" className="h-8 px-2 text-xs" onClick={clearSelection} disabled={draftIds.size === 0}>
                    Bỏ chọn
                  </Button>
                </div>

                {loadStatus === "loading" && (
                  <div className="flex items-center gap-2 py-6 text-xs text-muted-foreground" role="status">
                    <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                    <span>Đang tải danh sách tài liệu…</span>
                  </div>
                )}

                {loadStatus === "error" && (
                  <p role="alert" className="py-3 text-xs text-destructive">
                    {loadError ?? "Không thể tải danh sách tài liệu."}
                  </p>
                )}

                {loadStatus === "ready" && filteredDocuments.length === 0 && (
                  <p className="py-4 text-center text-xs text-muted-foreground">
                    {documents.length === 0
                      ? "Chưa có tài liệu nào ở trạng thái INDEXED."
                      : "Không tìm thấy tài liệu khớp từ khóa."}
                  </p>
                )}

                {loadStatus === "ready" && filteredDocuments.length > 0 && (
                  <ul className="max-h-56 space-y-1 overflow-y-auto pr-1" aria-label="Danh sách tài liệu có thể chọn">
                    {filteredDocuments.map((doc) => {
                      const checked = draftIds.has(doc.document_id)
                      return (
                        <li key={doc.document_id}>
                          <label className="flex cursor-pointer items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted/60">
                            <span className="flex min-w-0 items-center gap-2.5">
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleDocument(doc.document_id)}
                                className="size-4 rounded border-input accent-primary"
                              />
                              <span className="truncate font-medium">{doc.file_name}</span>
                            </span>
                            <span className="shrink-0 text-xs text-muted-foreground">
                              {doc.chunk_count} chunks
                            </span>
                          </label>
                        </li>
                      )
                    })}
                  </ul>
                )}

                {draftIds.size === 0 && (
                  <p className="text-xs text-muted-foreground">
                    Hãy chọn ít nhất 1 tài liệu để áp dụng chế độ này.
                  </p>
                )}
              </div>
            )}

            {saveError && (
              <p role="alert" className="text-xs text-destructive">{saveError}</p>
            )}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)} disabled={saving}>
              Hủy
            </Button>
            <Button type="button" onClick={() => void applySelection()} disabled={!canApply}>
              {saving ? "Đang lưu…" : "Áp dụng phạm vi"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
