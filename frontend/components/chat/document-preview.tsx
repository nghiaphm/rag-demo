"use client"

import { useEffect, useState } from "react"
import { readTextPreview } from "@/lib/documents/text-preview"
import { createApiClient } from "@/lib/api/client"
import { getDocumentPreview } from "@/lib/api/documents"
import { safeApiErrorMessage } from "@/lib/api/error-ux"
import type { AttachmentReference } from "@/types/chat"
import type { DocumentPreviewResponse } from "@/types/document"

type PreviewState = { phase: "loading" } | { phase: "ready"; text: string; truncated: boolean } | { phase: "error"; error: string }

function TextPreview({ file }: { file: File }) {
  const [state, setState] = useState<PreviewState>({ phase: "loading" })
  useEffect(() => {
    let active = true
    void readTextPreview(file).then(result => {
      if (active) setState({ phase: "ready", ...result })
    }, error => {
      if (active) setState({ phase: "error", error: error instanceof Error ? error.message : "Không thể đọc file." })
    })
    return () => { active = false }
  }, [file])
  if (state.phase === "loading") return <p role="status">Đang đọc bản xem trước…</p>
  if (state.phase === "error") return <p role="alert" className="text-destructive">{state.error}</p>
  return <>
    {state.truncated && <p role="status" className="mb-3 text-muted-foreground">Chỉ hiển thị tối đa 256 KiB đầu tiên. File gốc dùng để upload không bị cắt.</p>}
    <pre aria-label="Nội dung tài liệu" tabIndex={0} className="whitespace-pre-wrap break-words rounded-lg border bg-muted/40 p-3 font-mono text-xs leading-6 focus-visible:outline-2 focus-visible:outline-ring">{state.text}</pre>
  </>
}

function RemotePreview({ reference, apiBaseUrl }: { reference: AttachmentReference; apiBaseUrl: string }) {
  const [result, setResult] = useState<DocumentPreviewResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { document_id, version_id } = reference
  useEffect(() => {
    const abort = new AbortController()
    const api = createApiClient({ baseUrl: apiBaseUrl })
    void getDocumentPreview(api, document_id, version_id, abort.signal).then(result => {
      if (!abort.signal.aborted) setResult(result)
    }, error => {
      if (!abort.signal.aborted) setError(safeApiErrorMessage(error, "Không tải được bản xem trước của phiên bản này."))
    })
    return () => abort.abort()
  }, [apiBaseUrl, document_id, version_id])
  if (error) return <p role="alert" className="text-destructive">{error}</p>
  if (!result) return <p role="status">Đang tải bản xem trước…</p>
  if (result.kind === "unsupported") return <p role="status">Chưa hỗ trợ xem trước định dạng này.</p>
  return <>
    {result.truncated && <p role="status" className="mb-3">Bản xem trước được giới hạn; file gốc không thay đổi.</p>}
    {result.kind === "text" ? <pre aria-label="Nội dung tài liệu" tabIndex={0} className="whitespace-pre-wrap break-words rounded border p-3 font-mono text-xs">{result.text}</pre>
      : result.sheets?.map((sheet, index) => <section key={index} className="mb-6">
        <h3 className="mb-2 break-words font-semibold">{sheet.name}</h3>
        <p className="mb-2 text-xs text-muted-foreground">{sheet.total_rows} hàng dữ liệu{sheet.truncated ? " · hiển thị một phần" : ""}</p>
        <div role="region" aria-label={`Sheet ${sheet.name}`} tabIndex={0} className="max-w-full overflow-x-auto rounded border focus-visible:outline-2 focus-visible:outline-ring">
          <table className="w-full border-collapse text-left text-xs"><thead><tr>{sheet.columns.map((column, i) => <th scope="col" className="whitespace-pre-wrap border p-2" key={i}>{column || `Column ${i + 1}`}</th>)}</tr></thead>
            <tbody>{sheet.rows.map((row, i) => <tr key={i}>{row.map((cell, j) => <td className="min-w-24 max-w-80 whitespace-pre-wrap break-words border p-2" key={j}>{cell}</td>)}</tr>)}</tbody>
          </table>
        </div>
      </section>)}
  </>
}

export function DocumentPreview({ file, reference, apiBaseUrl }: { file?: File; reference?: AttachmentReference | null; apiBaseUrl?: string | null }) {
  if (file?.name.toLowerCase().endsWith(".txt")) return <TextPreview file={file} />
  if (reference && apiBaseUrl) return <RemotePreview key={`${reference.document_id}:${reference.version_id}`} reference={reference} apiBaseUrl={apiBaseUrl} />
  if (file?.name.toLowerCase().endsWith(".xlsx")) return <p role="status">Chờ upload và index hoàn tất để xem bảng Excel.</p>
  return <p role="status">Chưa hỗ trợ xem trước định dạng này hoặc chưa có cấu hình API.</p>
}
