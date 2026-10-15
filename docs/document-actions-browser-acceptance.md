# F7-03-04 — Document Actions browser acceptance (2026-10-15)

**COMPLETED.** Verification-only continuation of FRONTEND_PLAN sections31.4/34. Existing wired F6 upload/version/re-index/delete and the prior aborted-page-slot fix are retained. This task adds browser evidence, not a new implementation. No application/backend/API/schema/RAG/config/dependency changes, no live ingestion or provider calls, no Codex in-app Browser invocation/modification.

## Scope and observations

Repository Playwright Test1.64.1 / Chromium156 headless on Windows, production Next server on owned127.0.0.1:3100. Each case uses a fresh RAM-only `/lifecycle` mock on an ephemeral loopback port. Unexpected origins and uncaught browser exceptions fail teardown. Desktop1280×800; small viewports320×568/375×568, default zoom. These are actual browser observations, not inferred from SSR callbacks.

`frontend/e2e/document-actions.spec.mts` adds9 cases:

| Case | Observed acceptance |
| --- | --- |
| Upload keyboard/validation/cancel | Enter opens; file input initially focused; Shift+Tab wraps to Close and Tab wraps to input. Empty TXT/unsupported extension show validation and disable submit. Escape closes, returns focus to upload trigger and sends no mutation. |
| Upload pending/success | A promise gate holds the upload request. Busy form, disabled submit/close, Escape and X do not close; no premature INDEXED receipt. Release permits real mock201; receipt is displayed, list refresh shows uploaded file, close restores trigger focus. Exactly one upload. |
| Mobile320 and375 | Each viewport separately exercises version/re-index/delete: Enter opens, initial focus is file or Close, Tab/Shift+Tab wrap inside, all dialog bounds fit568px height/viewport width. Close and Escape return focus to the action trigger; no mutation on cancel. |
| Failure/active preservation/lifecycle | `qa-fail.txt` produces mock500 with a persisted FAILED version. UI displays safe error and disallows automatic resubmission. After closing, version3 is shown as Thất bại while document remains INDEXED and active ID unchanged. Explicit re-index creates version4 and changes active ID only after reread. Confirmed DELETE202 removes default-list row and reports pending cleanup/raw retention; a fresh confirmation sends DELETE200, disables further cleanup and include_deleted restores the tombstone row. |
| Stale confirmation | TabA proposes DELETE; tabB confirms re-index. TabA's preflight detects changed snapshot, updates detail and shows review warning with disabled confirm. Zero DELETE requests; after close focus returns to the same action and version3 is visible. |
| Post-mutation read failure | Re-index succeeds; its authoritative GET is forced503. Receipt remains, warning identifies stale detail, prior active ID is retained and confirm stays disabled. No loop/replayed mutation. Explicit list refresh and reselect read the actual new active ID. |
| Stop waiting/navigation | During a deliberately delayed re-index, close is disabled and Escape keeps the dialog open. Keyboard Stop waiting produces uncertain-state guidance, not a server-cancellation claim; confirm remains disabled. Close/navigate Chat→Documents does not replay the single POST. |
| Status guards | PROCESSING and FAILED fixtures show their document status separately from absent active version. PROCESSING disables new version/re-index; FAILED permits a new version but re-index remains disabled without active ID. GET-only case. |

The existing workspace E2E additionally verifies successful multipart upload/new-version/re-index/delete202/cleanup200/include_deleted end to end. Existing frontend tests cover exact methods/headers/multipart field/ownership, confirmation/duplicates, canceled-page-slot release/adjusted offset, late responses, selection/filter/unmount, malformed receipt and error paths. Browser cases complement these tests rather than claim a live ingestion result.

## Audit findings and changes

No new application defect was reproduced in these checks. `DocumentsController.reconcile` already aborts and clears request slots, with signal/identity guards against stale results; the existing regression was rerun within the full frontend suite. Successful/error action paths already reread authoritative detail; stale preflight prevents mutation; delete retains tombstone detail and distinguishes cleanup200/202/raw retention. Existing FastAPI routes/Pydantic/OpenAPI contract and repository failure semantics were checked, not modified.

Only fixture change: expose the existing mock's request delay as test option `apiDelayMs`, default25ms unchanged. A larger per-test delay makes the pending Stop waiting case observable. Upload pending uses an explicit promise gate. No polling/job API/progress percentage or provider integration was introduced.

Initial browser assertions attempted to read the background region while a modal intentionally removed it from the accessibility tree. Tests now close the modal before inspecting detail. Other assertions were corrected against source: FAILED is displayed as “Thất bại”, and the list refresh label is “Làm mới”. No UI was changed to satisfy mistaken assertions. One overlapping CLI attempt was rejected because the owned3100 server was still running; it also disturbed that failed run's trace files. Subsequent acceptance runs are serialized with fresh reports; developer3000 was not reused or stopped.

## Verification

| Command / check | Actual result |
| --- | --- |
| `npm.cmd test` | PASS196/196,0 skipped; includes prior reconciliation regression and lifecycle composition tests. |
| `npm.cmd run build:e2e` | PASS7/7 production prerender. Public API base overridden only for build child process; `.env` untouched. Rebuild normally before using another API base. |
| `npm.cmd run typecheck` / `npm.cmd run lint` | PASS / PASS0 warnings after final test edits. |
| `npm.cmd run test:contract` | PASS45 REST/SSE/health schemas, offline/network blocked. |
| Final `npm.cmd run test:e2e` | PASS31/31 Chromium headless, expected31/unexpected0/skipped0/flaky0, retries0; includes all9 new cases and22 existing regressions. |
| Diff/new-file whitespace/archive/owned-server cleanup | PASS; CURRENT_CHANGE15 entries, F6-03 archived verbatim before removal; owned3100 ECONNREFUSED, developer3000 untouched. |
| Backend tests / audit / live ingestion | NOT RERUN / NOT RERUN / NOT RUN in this continuation. Groq=0/Gemini=0. |

Generated browser evidence: ignored `frontend/test-results/e2e-results.json` and `frontend/playwright-report/index.html`. Failed runs were inspected through error-context/trace/screenshot evidence; no skips, rule disabling or relaxed application guards were introduced.

## Files and remaining limits

Changed in this continuation: `frontend/e2e/fixtures.mts`, new `frontend/e2e/document-actions.spec.mts`, this report, FRONTEND_PLAN.md, CURRENT_CHANGE.md, docs/changelog/phase-02.md and scoped addenda in accessibility/browser/functional/automated-test reports. Prior worktree changes are preserved.

Mock metadata/version counters are not evidence of actual parsing, embeddings, raw-file retention/deletion or cloud cleanup. No raw files are written; only synthetic buffers are submitted. No real document/session mutation or stress test was performed.

Sync ingestion has no polling/progress job API; preflight GET is not atomic If-Match protection; aborted/uncertain requests can still complete server-side. Deliberate refresh/review and fresh confirmations remain required. Human screen-reader, contrast, zoom200%, real touch and full F7-02/F7-03-05 acceptance are not certified here. BUG-STREAM-001/prior backend80/81 and npm audit9 high remain open, not rerun or waived. Concurrent RAG incident stays NOT REPRODUCED. Stop after task04; do not start another task or live smoke.
