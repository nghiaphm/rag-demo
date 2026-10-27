# Message attachments and Excel support

## Audit findings

- Composer uploads previously ended in local React state. Chat payloads, Mongo message records, history DTOs and user-message rendering had no attachment field. A local `File` preview could not survive refresh.
- The old `.xlsx` loader parsed the existing sample offline in the audited environment. The prior missing optional packages were already installed, so a new upload failure was not reproduced. Its `page_name` metadata was discarded by vector mapping; structured preview, MIME/content checks and bounded workbook parsing were missing.

## Contract and lifecycle

`POST /chat` and `POST /chat/stream` accept an optional `attachments` array:

```json
{"question":"Explain these vehicles","session_id":"<session UUID>","attachments":[{"document_id":"<document UUID>","version_id":"<version UUID>"}]}
```

Attachments require a persistent session, are limited to 20 unique references, and must identify an indexed version belonging to a non-deleted document. The server supplies the canonical filename. The existing Mongo repository serializes references with the user message; no raw file, preview text, or caller-provided filename is stored in messages. Legacy records default to an empty array without migration or content changes.

Attachments do **not** set session scope or restrict RAG retrieval. Inactive indexed versions remain valid historical references. Removing/resetting Composer only clears local state. Explicit document deletion leaves the message reference visible but its preview returns 410.

Existing indexed versions are not automatically migrated/re-indexed. New sheet/row vector metadata is produced on subsequent upload/re-index; old messages and document versions remain unchanged.

`GET /documents/{document_id}/versions/{version_id}/preview` returns the exact version's bounded plain text or read-only sheet tables. It validates the document/version association and reads the existing raw storage adapter without calling providers or Qdrant. PDF preview remains explicitly unsupported. TXT still previews locally before send; persisted messages read the stored version.

Retrieved source metadata adds optional `sheet_name` and one-based `row_index`; retrieval ranking, query rewriting and session scope are unchanged.

## XLSX policy

The existing `POST /documents/upload` validates `.xlsx` MIME (including empty/octet-stream/ZIP fallbacks) and the actual OOXML package. A shared read-only `openpyxl` parser feeds the existing splitter, embedding and Qdrant adapters. Each row repeats its column labels and sheet name; `sheet_name` and one-based `row_index` survive vector storage, retrieval and source metadata.

- Limits: 10 MiB file; 64 MiB ZIP expansion; 5,000 ZIP entries; 50 sheets; 20,000 rows and 200 columns per sheet; 250,000 cells total; 32,767 characters per cell; 65,536 parsed characters per row and 16,777,216 total parsed characters.
- First nonempty row is the header. Blank rows are omitted while original row numbers are retained. Dates become ISO text. Formulas remain literal strings and are never calculated. Macros are rejected and external workbook links are not resolved.
- Preview caps: 50 rows/30 columns per sheet, 200 rows total, 262,144 preview text characters, with explicit truncation. Spreadsheet styling/merged-cell layout is not reproduced.
- `.xls` is not enabled: the bounded OOXML validation/parser policy applies only to `.xlsx`. Convert legacy workbooks to `.xlsx`.

## Verification and limits

Backend regression exercises the real upload route, parser, immutable previews, JSON/SSE persistence and Qdrant in-memory retrieval with deterministic embeddings. Frontend tests cover payload references, legacy messages and preview contracts. Chromium fixtures verify TXT and Excel message chips before/after refresh and session switching, unavailable versions, Ready gating and existing Send/Stop behavior.

Browser API fixtures model table responses; the backend tests verify actual workbook parsing and indexing independently. No live Groq/Gemini, production MongoDB/Qdrant mutation, full workbook styling, screen-reader session, or real-device touch QA is claimed.

Final checks on 2026-10-27:

| Check | Result |
| --- | --- |
| Backend `unittest discover -s tests -v` | 207 passed |
| Frontend Node tests, sequential | 210 passed |
| REST/SSE/preview schema contract | 49 schemas passed, network blocked |
| Chromium full suite | 63 passed across three fresh-browser shards: 25 + 22 + 16; zero skipped/flaky/unexpected/errors |
| TypeScript / ESLint | Passed |
| Standard production build | Passed with one static worker and process-local Node memory limits; existing API configuration restored |

The initial long Chromium run hit `ERR_INSUFFICIENT_RESOURCES`; the final three shards cover the entire same suite without dropping tests. Individual JSON evidence and the aggregate summary are under ignored `frontend/.playwright-tmp/e2e-shard*.json` and `e2e-combined-summary.json`. Next.js still reports its existing version security advisory; framework upgrade is outside this feature.

## Files changed

| Area | Files |
| --- | --- |
| Attachment contracts/persistence | `backend/app/attachment_models.py`, `attachments.py`, `conversation_models.py`, `conversation_schemas.py`, `conversation_service.py`, `schemas.py`, `api/chat.py`, `api/sessions.py` |
| Excel/upload/preview | `backend/app/excel.py`, `api/documents.py`, `rag/loader.py`, `ingestion.py`, `vector_index.py`, `qdrant_ingestion.py`, `rag/retriever.py`, `rag/pipeline.py`, `backend/requirements.txt` |
| Composer/message/preview UI | `frontend/components/chat/chat-composer.tsx`, `chat-preview.tsx`, `chat-message.tsx`, `attachment-chip.tsx`, `message-attachment.tsx`, `document-preview.tsx`, `frontend/hooks/use-chat-attachments.ts` |
| Frontend data flow | `frontend/types/chat.ts`, `sessions.ts`, `document.ts`; `frontend/lib/api/documents.ts`, `sessions.ts`; `frontend/lib/chat/controller.ts`, `lib/sessions/history.ts`, `lib/documents/upload-validation.ts`, `lib/sse/parser.ts` |
| Verification | `backend/tests/test_message_attachments_excel.py`; `frontend/tests/message-attachments.test.mjs`, `chat-attachments.test.mjs`, `ui-polish.test.mjs`; `frontend/e2e/message-attachments.spec.mts`, `chat-attachments.spec.mts`; `frontend/scripts/qa-mock-api.mjs`, `qa-document-lifecycle.mjs` |
