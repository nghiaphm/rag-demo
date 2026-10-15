# F8-01 — Automated frontend tests (2026-10-15)

**COMPLETED for the requested frontend automated scope.** Release/full-demo readiness is not claimed: BUG-STREAM-001, dependency advisories and remaining manual accessibility checks stay open. The user explicitly assigned F8-01; starting it does not waive the earlier F7 gate. F8-02/live smoke and F8-03 are NOT STARTED.

## Repeatable commands

From `frontend/`, with the existing Node/npm and root `.venv` requirements installed:

```powershell
npm.cmd ci
node node_modules/playwright/cli.js install chromium --no-shell
npm.cmd test
npm.cmd run test:contract
npm.cmd run build:e2e
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run test:e2e
```

The existing offline Python fixtures use `../.venv/Scripts/python.exe`; current verification is Windows-based. `npm ci` is a setup instruction, not a command rerun during this task. Unit tests and contract export reject provider network activity. The build may download Google Fonts; it does not call AI providers. `build:e2e` overrides NEXT_PUBLIC_API_BASE_URL only in the build child process to `http://127.0.0.1:4011/lifecycle`; no .env edits. A normal app build must be rerun for a different public API base after E2E work.

Playwright starts an owned production server at127.0.0.1:3100 with reuseExistingServer=false; stop/fix a conflicting test server deliberately rather than reuse an unknown instance. Each test gets its own ephemeral loopback RAM-only mock. Page requests to the baked4011 mock origin are forwarded to that owned mock; any unexpected backend/provider/origin request is aborted and fails teardown. Uncaught browser exceptions also fail teardown. Service workers are blocked, retries=0 and workers=1. No shared live backend data is mutated.

`run-e2e.mjs` places browser profiles/temp under ignored `.playwright-tmp` on the workspace drive, outside Playwright output cleanup. It forwards CLI arguments, e.g. `npm.cmd run test:e2e -- --grep cancel`. Chromium headless uses `channel:chromium`, not the optional headless-shell package. Reports are ignored generated artifacts: `playwright-report/index.html`, `test-results/e2e-results.json`, failure screenshot/trace. No test source is ignored by ESLint; only generated reports/temp are excluded.

## Actual results

| Check | Result |
| --- | --- |
| `npm.cmd test` | **PASS196/196**, no skipped tests. Includes SSE parser, REST/stream clients, source mapper/citations, state/controller unit tests, component SSR/callback/effect harnesses, real local HTTP integration and multi-session isolation. |
| `npm.cmd run test:contract` | **PASS45 schemas**, offline OpenAPI/Pydantic/REST/SSE parity checks, network blocked in Python export. |
| `npm.cmd run build:e2e` | **PASS7/7 prerender**, production exit0 after the composer ID fix. Chat session route remains partial prerender, documents static. |
| `npm.cmd run typecheck` | **PASS** after build, including `.mts` E2E sources/config. |
| `npm.cmd run lint` | **PASS0 warnings**, including test source. |
| `git diff --check`, new-file whitespace, log/archive and server cleanup | **PASS**. F5-02 archive verified verbatim before removing its old entry; CURRENT_CHANGE retains15 entries. Final3100 probe confirmed the owned test server stopped. |
| `npm.cmd run test:e2e` | **PASS7/7 Chromium156**, Playwright1.64.1, no retries/skips/flaky tests, no unexpected-origin requests or uncaught browser exceptions. Final JSON report: expected7/unexpected0/skipped0/flaky0;25.5s. |
| Existing guarded backend QA runner | **FAIL:80/81 pass,1 fail** at known whitespace terminal/history parity. Not skipped, waived or made green by this task. |
| `npm audit --json` | **9 high**,0 critical. Current advisory paths include eslint-config-next/Next lint plugin and shadcn/registry/ts-morph/glob chains. The reported fix options entail major changes/downgrades; no audit fix/force or runtime dependency migration performed. This is not a security-clearance claim. |
| Browser plugin/manual/live providers | Codex in-app Browser not invoked or modified. Human screen-reader/full manual QA and live provider smoke **NOT RUN**; Groq=0/Gemini=0. Repository Playwright tests are real headless browser tests, not SSR mocks. |

The first browser install downloaded full Chromium and FFmpeg but failed the optional Headless Shell download with ENOSPC on C:. The test runner uses the installed full Chromium and workspace-local temp; final E2E passed. A read-only cache inspection found only completed Chromium/FFmpeg folders, no incomplete shell folder; no unrelated cache/files were deleted. The documented install uses --no-shell. Npm also warned about an unapproved optional unrs-resolver install script; no extra install scripts were approved, and build/typecheck/lint passed with the existing environment.

## Browser E2E coverage

| Test | Verified outcomes |
| --- | --- |
| Session actions by keyboard | New session/open route; Enter menu; rename input initial focus; PATCH reconciliation; delete initial focus on Hủy; Escape/cancel sends no DELETE; confirmed current-session deletion→/chat; focus returns to New Chat. |
| Composer and3-turn history | Exactly one created session;3 stream POSTs reuse its ID; assistant count3; exact accessible composer label after canonical navigation; reload restores own history. |
| Cancel/recovery | Partial text survives Stop; local generation ends; explicit history link restores partial status; one POST, no automatic replay. |
| Post-header error/disconnect | Both terminal error and missing-terminal disconnect release read-only/loading; explicit recovery remains; two deliberate POSTs only. |
| Document lifecycle | Multipart upload201→list refresh; version PUT and re-index create version3; delete202 shows raw retention; new explicit cleanup confirmation→200; include_deleted exposes tombstone. |
| REST503 recovery | Explicit list retry, one initial request and one deliberate recovery request; no automatic list loop. |
| Mobile375px | Enter opens sidebar, choosing Documents closes it, Escape closes it on reopen, focus returns to toggle. |

This is not complete screen-reader/contrast/zoom200%/320px/touch/reduced-motion or all dialog focus-trap/arrows coverage. Citation drawer real-browser interaction and live ingestion/provider behavior remain outside these7 cases; existing unit/integration checks cover mapper/content, not a substitute for those manual rows. Prior F7 tasks are not all automatically marked complete.

## Proven minimal fix

Initial E2E was5/7: one test locator matched both the dialog and input and was corrected to an exact textbox role. The other failed after canonical navigation: browser accessibility snapshot showed textbox name **“Câu hỏi Câu hỏi”**, caused by static composer/help IDs being reused when Next retained the previous workspace page. No generation/persistence failure occurred.

ChatWorkspace now obtains a React useId and passes it to ChatComposer; label htmlFor, textarea id and help aria-describedby use that instance ID. The composer retains an optional default ID for existing standalone callers/tests. The real3-turn/navigation/refresh test now passes with the exact name “Câu hỏi”, and all196 unit/integration tests pass. The direct-hook isolation harness gained only a useId stub. Stop/send/SSE contracts are unchanged; no route rendering strategy, backend logic/schema, shadcn components or broad UI refactor was added.

Other harness setup issues resolved before final verification: `.mts` test modules for native import.meta mock helpers; fixture callback renamed from use to provide so React's hook lint rule does not misclassify it; no rule disabled. Final E2E was rerun after adding the temp launcher and browser exception guard.

## Open gates

1. [BUG-STREAM-001](./bugs/stream-terminal-parity.md): whitespace-only error remains SSE PARTIAL vs stored FAILED. Backend runner still exits1. Separate bugfix required under its assigned scope.
2. Nine current high npm advisories need a scoped dependency review; no speculative downgrade/force fix is applied here.
3. Remaining human accessibility/manual coverage in [checklist](./frontend-accessibility-checklist.md) is not waived. In-app Browser runtime status is unchanged.
4. [Intermittent multi-session incident](./multi-session-rag-investigation.md) remains NOT REPRODUCED; automated isolation passing is not a FIXED claim. Live smoke remains developer-approved only.

Files changed for F8-01: package.json/package-lock, playwright.config.ts, e2e/fixtures.mts and workspace.spec.mts, scripts/build-e2e.mjs/run-e2e.mjs, .gitignore/eslint generated-artifact ignores, chat-composer.tsx/chat-preview.tsx, useId stub in multi-session-isolation.test.mjs, this report and updated plan/change log/browser/accessibility evidence. F8-02/F8-03 have not started.

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

## F7-03-05 continuation — 2026-10-15

[Current functional QA report](./frontend-functional-qa.md), plan41 supersede prior blanket browser-blocked/parity-failing status. User-approved BUG-STREAM-001 is FIXED: backend84/84 + overlapping isolation67/67, frontend198/198, actual Chromium44/44 (122.2s,0 retries/skips/flaky/unexpected), build/typecheck/lint/contract45 and production HTTP delivery PASS.13 new browser error/health/route/empty/pagination/reader-intent/keyboard/320px checks complement31 prior cases.

Human AT/contrast/desktop zoom200%/real touch remain NOT RUN, dependency audit9 high remains unaccepted, actual backend8000 verifier failed ECONNREFUSED before CORS assertions. F7-03-05 final gate IN PROGRESS until explicit resolution/disposition; no false PASS or automatic F8/live smoke. In-app Browser untouched,0 Groq/Gemini/live mutations. Historical counts/results above are preserved evidence, not current parity/browser blockers.

## F8-02 controlled live follow-up — 2026-10-15

User subsequently assigned and explicitly approved controlled live scope:5 Groq attempts,4 Gemini embedding requests, fresh temporary namespaces/raw storage and owned cleanup. [F8-02 report](./frontend-controlled-live-e2e.md), plan42:7/7 actual browser stages/3 completed turns PASS; actual4 Groq +4 Gemini attempts, no retry. Health, real isolated upload, same-session history/citations and document/session actions verified. Initial Mongo cleanup code8000 recovered by exact-namespace collection cleanup; fresh independent Mongo/Qdrant/raw absence checks and owned-server shutdown PASS.

This supersedes a blanket “live never run” interpretation, not the historical no-provider counts for earlier tasks/default tests. Default unit/mock scripts still make0 live calls; live is a separate opt-in runner. It also proves the controlled isolated runtime, not permanently configured developer8000/default deployment or the entire CORS matrix. Human manual/security debt remains unwaived; F7-03-05 status is unchanged. F8-03 NOT STARTED; no further provider calls under the exhausted Gemini approval.
