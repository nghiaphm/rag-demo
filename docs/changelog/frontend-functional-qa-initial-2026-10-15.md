# F7-03-05 — Functional QA & Regression

2026-10-15. **IN PROGRESS; gate before F8 is NOT PASSED.** Two blockers: actual browser/manual acceptance is unavailable, and BUG-STREAM-001 is reproduced. Neither is waived. This report supersedes the current-status interpretation of the historical matrix in FRONTEND_PLAN section31; it does not rewrite that audit snapshot.

## Executed checks

| Check | Actual result and limit |
| --- | --- |
| `node --test tests/*.test.mjs` in frontend | **PASS193/193**. Production REST/SSE/parser/controllers, component callback/SSR/effect harnesses and local HTTP fixtures. Includes new combined session CRUD/3-turn/history/document lifecycle flow and whitespace mismatch recovery. No browser DOM E2E claim. |
| `.venv/Scripts/python.exe backend/scripts/verify_frontend_functional_qa.py` | **FAIL:80/81 pass,1 fail**. Sessions/action repository/concurrency/models, documents/ingestion, chat persistence/stream, SSE/CORS and terminal parity. External TCP blocked; loopback IPC allowed. Real whitespace-only parity failure, not an environment failure. Local Qdrant warns payload indexes have no effect; cloud behavior is not verified. |
| `node tests/verify-api-contract.mjs` in frontend | **PASS45 schemas**, offline source OpenAPI/Pydantic/SSE/type checks; network disabled in export. |
| `node scripts/verify-local-integration.mjs` in frontend | **PASS** against actual port8000: runtime/source paths and component schemas identical,11 paths. Two allowed origins × GET sessions/documents200 with exact ACAO/Vary; two actual OPTIONS chat/stream200 allowing POST/content-type; localhost3001 preflight400/noACAO. No response data printed; no chat POST or mutation. |
| Configured `npm.cmd run build` | **PASS7/7 prerender**, exit0; process-only API base `http://127.0.0.1:4011/lifecycle`, restored afterward. Chat session route remains partial prerender, documents static. No config/.env edits. |
| `node scripts/verify-production-delivery.mjs` | **PASS**: production `/chat`, `/chat/{fixture UUID}`, `/documents`200/main content; client JS200. Uses an owned temporary server on an ephemeral loopback port, then verifies its exit. Developer servers untouched. HTTP delivery does not prove hydration/active navigation/accessibility. |
| `node node_modules/typescript/bin/tsc --noEmit` | **PASS** after production build. |
| `npm.cmd run lint` | **PASS0 warnings**; no disabled rules. |
| `git diff --check`, new-file whitespace and archive verification | **PASS**. F4-03 archived verbatim before removing its old log entry; CURRENT_CHANGE retains15 entries. |
| Browser bootstrap | **FAIL** at import: `Cannot redefine property: process`, before setup/connection/URL. Skill/troubleshooting workflow attempted. Keyboard/mobile/zoom/focus/screen-reader/actual browser flows **NOT RUN**. |
| Live provider generation/embedding or user-data mutations | **NOT RUN**. Groq=0, Gemini=0. All mutation fixtures stay in local RAM/temp in-memory test stores. Actual backend probes are read-only GET/OPTIONS. |

Existing sandbox restrictions on Python outside the workspace and Google Fonts are handled with the authorized escalated check commands; no environment reconstruction or rule bypass. No frontend/backend application implementation changed in task05. Source/config changes from earlier tasks are preserved.

## Current capability coverage

| Required capability | Implementation/automated evidence | Actual browser acceptance |
| --- | --- | --- |
| New/open/invalid/missing/deleted sessions | Sessions clients/controllers/navigation fixtures,404/410 and lookup guards PASS | NOT RUN |
| PATCH title, cancel/confirm DELETE, current vs other navigation | Session action clients/repository/callback fixtures PASS; title Unicode/validation and idempotent receipts covered | NOT RUN; no focus/menu claims |
| >50 sessions, refresh, stale mutation reconciliation |60-session mock, load-more/dedupe/abort tests PASS | NOT RUN |
|409 active generation, no automatic retries | Backend guards/atomic race + mock stream conflict PASS | NOT RUN |
| Composer creation→sidebar | Actual hook/workspace effect callback fixture + production services PASS | NOT RUN |
|3-turn SSE, IDs, exact whitespace, paginated history/session isolation | Combined local HTTP test + multi-turn/parser/stream/history suites PASS | NOT RUN |
| Stop/disconnect/unmount/late events, no infinite loading | Cancellation/deadline/recovery/late-callback fixtures PASS | NOT RUN |
| Historical PENDING/STREAMING, deferred URL/recovery | Provenance/SSR/controller/canonical-path fixtures PASS | NOT RUN |
| Copy and citation/Markdown/source drawer | Exact/denied clipboard, message-local sparse/repeated/out-of-range markers, history fallback fixtures PASS | Actual clipboard/drawer/focus NOT RUN |
| Documents list/detail/filter/pagination/status/active ID | List/detail/stale-page regression PASS | NOT RUN |
| Multipart upload/versions/re-index | Existing clients + wired callback/local HTTP profile PASS; no fake progress/activation | NOT RUN |
| Failed version preserves active; DELETE202/cleanup200/raw retention | Repository/mock/controller/composition fixtures PASS | NOT RUN |
| Safe HTTP422/404/409/429/503/network/post-header errors | Error/health/timeout/no-replay fixtures PASS; health readiness fixture only | NOT RUN; real dependency outage not induced |
| SSE terminal vs persisted history status | **FAIL BUG-STREAM-001**, whitespace-only error; frontend warning/recovery PASS | NOT RUN |
| Runtime contracts/CORS/prerender delivery | Actual source/runtime/Origin/OPTIONS/build/production HTTP PASS | Hydration/navigation NOT RUN |
| Responsive320/375px, keyboard/menu/dialog, zoom/reduced motion/AT | Source/SSR/scroll/keyboard-handler tests only | **BLOCKED**, no manual row is PASS |

No previously missing required REST client/action wiring remains unimplemented in this inspection. Required interaction acceptance remains PARTIAL/BLOCKED; passing source/callback fixtures does not complete those rows. Unrequested auth/scope/model/theme/individual-message/rollback/PDF/download features remain NOT REQUIRED FOR MVP.

## Technical-debt disposition

| Item | Decision in this QA gate |
| --- | --- |
| BUG-STREAM-001 whitespace terminal/history mismatch | **BLOCKING, not accepted**. Failing reproduction retained; separately assigned backend bugfix required. See [bug report](./bugs/stream-terminal-parity.md). |
| Browser/manual acceptance | **BLOCKING, not waived**. Recover compatible Browser/runtime or obtain developer Chrome/Edge results using the prepared mock checklist. SSR/HTTP cannot replace it. |
| History lacks ordered source metadata | Keep the previously accepted baseline fallback from F5: persisted citation cards, unavailable inline ordinals, no guessed link/order. Exact history ordinal restoration needs a separate API/schema task. |
| Deferred first-turn URL | Keep the F7-03-03 policy: explicit banner, correct new-tab recovery link, replace only after verified terminal. Refreshing `/chat` mid-turn cannot restore its route automatically; manual acceptance is still blocked above. No early navigation that aborts the keyed workspace. |
| Historical nonterminal messages | UI gap resolved in task03; keep backend status, show snapshot/no live connection and explicit reload. No resume/auto polling/replay. |
| Synchronous ingestion, no public maximum/job polling/cancel API | Keep existing API limits: no fabricated percentage/size cap/status, uncertain results require a deliberate read/confirmation. Mock2MiB cap is not a backend limit. Async jobs/quota/cancel expansion is out of scope. |
| Offset lists can shift under concurrent writes | Keep duplicate/stale guards, reset/reread after confirmed mutation, explicit retry. No snapshot isolation claim. Pagination strategy expansion deferred. |
| Eager history reads all pages | Known latency/RAM constraint; stable ordering and cross-session guards retained. Large-history performance was not measured; do not claim scale acceptance. |
| Live cloud/provider/ingestion verification | NOT RUN under the no-provider scope; mocks do not prove cloud readiness or raw filesystem cleanup. A live test requires a separately authorized scope. |
| Unused static scaffolding/optional features | Leave unchanged; no refactor or additional dependency to make the matrix appear complete. |

Existing API limitations are retained with explicit fallback behavior; this is not a waiver of newly discovered defects or missing manual AC. Gate remains closed until blockers are resolved or explicitly dispositioned by the user.

## Manual acceptance handoff

Run the [Chrome/Edge mock procedure](./frontend-browser-qa-blocker.md) and the [accessibility checklist](./frontend-accessibility-checklist.md). Use `/many` for60-session menu/pagination and `/lifecycle` for document success/failure/cleanup; restart dev with process-only public API base and restore it afterward. Never point protected-action QA at the live backend.

Record browser/version, viewport/zoom, input/AT, steps, actual result and evidence for each row. Session CRUD/conflict/navigation,3-turn refresh/Stop/copy/citations, document confirms/reconciliation,320/375px/zoom200%/keyboard/reduced motion/screen reader and Suspense hydration all remain **NOT RUN**. No developer manual outcomes were supplied in this task.

Next work is the separate parity bugfix and missing browser acceptance. **Do not mark F7-03-05 COMPLETED or start F8.**

## Subsequent F8-01 evidence

The user subsequently assigned F8-01 explicitly. Its [automated frontend report](./frontend-automated-tests.md) records196/196 unit/integration,7/7 real Chromium mock E2E, build/typecheck/lint/contract PASS and a minimal composer ID accessibility fix. This updates part of the previously NOT RUN browser coverage; the table above remains the task05 snapshot. F7-03-05 is not automatically completed: known backend parity still FAIL80/81 and remaining manual AT/viewport/keyboard coverage is unwaived. F8-02/live provider smoke has not started.

## F7-03-02 scoped browser acceptance update — 2026-10-15

**Session Actions COMPLETED**; [actual observations and commands](./session-actions-browser-acceptance.md) supersede earlier NOT RUN snapshots for these scoped AC only. Repository Playwright/Chromium156:5 new cases + existing current-delete case cover Space/Enter/arrows/Escape, dialog Tab containment/initial/return focus,320/375px, rename validation/trim,60-session pagination/refresh/other deletion, actual remote-stream DELETE409/no replay. Full suite12/12 PASS (39.1s, no skips/retries/flaky/unexpected); frontend196/196, backend session11/11, build/typecheck/lint/contract45 PASS.

Human AT/contrast/zoom/full chat/citation/document acceptance remains unverified. In-app Browser runtime untouched; no live backend/provider calls. F7-03-03/04/05 and unrelated BUG-STREAM-001/security gates retain their prior statuses; no next task started. Earlier counts/statuses above are historical evidence, not current Session Actions blockers.

## F7-03-03 scoped browser acceptance update — 2026-10-15

**Chat Actions COMPLETED**, [full observations/minimal focus fix](./chat-actions-browser-acceptance.md), FRONTEND_PLAN mục39. Existing implementation retained;10 new Chromium cases cover composer/sidebar before terminal, deferred URL/new-tab, refresh/recovery, verification503/lag, historical PENDING/STREAMING/FAILED/PARTIAL snapshots, remote409/no replay, native fetch abort on switch, exact copy/native Windows clipboard/denied permission, citation drawer375px/keyboard/focus/history fallback.

A browser regression proved citation opener DOM was replaced on source selection; memoizing the Markdown subtree retains that node and fixes Escape focus return. Full22/22 browser E2E PASS (77.6s,0 retries/skips/flaky/unexpected), frontend196/196, production build7/7, typecheck/lint/contract45 PASS. Historical NOT RUN snapshots above are superseded only for these scoped AC. Codex in-app Browser untouched;0 live providers/mutations.

Human screen reader/contrast/zoom/real touch/full document coverage remains unverified. Task04/05, BUG-STREAM-001/prior backend80/81 and9 high security advisories are not waived; broad backend/audit NOT RERUN. No Edit/Regenerate/Delete Message, no next task/live smoke.

## F7-03-04 scoped browser acceptance update — 2026-10-15

**Document Actions COMPLETED**, [actual observations/commands/limits](./document-actions-browser-acceptance.md), FRONTEND_PLAN mục40. Nine new Chromium cases cover upload validation/pending/success, version/re-index/delete confirmation/cancel/Escape/Tab/focus on320×568 and375×568, failed version preserves active,202→explicit200 cleanup/raw-retention copy, stale two-tab preflight/no DELETE, success receipt with failed reread/explicit refresh, Stop waiting/no replay and status guards. Full31/31 PASS (93.1s,0 retries/skips/flaky/unexpected), frontend196/196, build7/7/typecheck/lint/contract45 PASS.

No new application defect reproduced; no UI/backend/API/dependency changes or reimplementation. Prior aborted-page-slot regression remains PASS. Earlier NOT RUN snapshots are superseded only for these scoped browser AC. Human AT/contrast/zoom/real touch/full task05 acceptance remain unverified; BUG-STREAM-001/prior80/81 and9 high advisories are not waived. In-app Browser untouched;0 live provider/backend mutations. Stop after task04.
