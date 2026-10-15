# F7-03-05 — Functional QA & Regression

2026-10-15 continuation. **IN PROGRESS: automated evidence refreshed, BUG-STREAM-001 FIXED; final gate awaits explicit disposition of remaining manual/security/live-integration limits.** No unrun check is PASS. This is the current report; [previous report, preserved verbatim](./changelog/frontend-functional-qa-initial-2026-10-15.md) contains the original193/193,80/81 failure and earlier NOT RUN snapshots.

## Actual checks in this continuation

| Check | Result / practical limit |
| --- | --- |
| `npm.cmd test` | **PASS198/198**, skipped0. Includes combined session CRUD/3-turn/history/document lifecycle, original mismatch warning and new matching whitespace-state/Unicode reference tests. |
| Guarded `backend/scripts/verify_frontend_functional_qa.py` | **PASS84/84 after approved fix**. Before fix: original81 had1 failure; expanded84 reproduced whitespace error/normal-completion failures. Fake providers/stores, external TCP blocked. Local Qdrant payload-index warning is a fixture limitation, not cloud acceptance. |
| Guarded `backend/scripts/verify_multi_session_isolation.py` | **PASS67/67** after backend fix. Overlaps the84-test suite; do not add them as151 unique tests. Original concurrent RAG incident remains NOT REPRODUCED. |
| Focused `npm.cmd run test:e2e -- functional-qa.spec.mts` | **PASS13/13** real Chromium156 headless browser cases using isolated local mocks. |
| Final `npm.cmd run test:e2e` | **PASS44/44 Chromium156**,122.2s, retries0/skipped0/flaky0/unexpected0. Rebuilt production frontend;31 prior cases +13 new functional cases. |
| `npm.cmd run build:e2e` | **PASS7/7 production prerender**, process-only public API mock override; no `.env` edits. Rebuild for another API base before ordinary integration. |
| `npm.cmd run typecheck`, `npm.cmd run lint` | **PASS / PASS0 warnings** after implementation changes. |
| `npm.cmd run test:contract` | **PASS45 schemas**, source OpenAPI/Pydantic/REST/SSE/nullable/optional verification, offline network blocked. |
| `node scripts/verify-production-delivery.mjs` | **PASS** actual production HTTP `/chat`, `/chat/{fixture ID}`, `/documents`, main content and client JS200; its owned ephemeral server exits. Browser suites separately test hydration/navigation. |
| `node scripts/verify-local-integration.mjs` | **FAIL to connect: ECONNREFUSED127.0.0.1:8000**. The runtime OpenAPI/GET/OPTIONS/CORS assertions were NOT REACHED. Existing CORS remains covered by offline backend tests, but live8000 integration is NOT VERIFIED in this run. Did not start/reconfigure a live backend. |
| `npm.cmd audit --json` | **9 high,0 critical**, not a clean security result. Ignored raw report: `frontend/.playwright-tmp/functional-qa-audit.json`. See disposition below. No install/update/audit fix. |
| Diff / new-file whitespace / archive / owned3100 cleanup | PASS; CURRENT_CHANGE15 entries, F7-01 archived before removal; prior QA report archived verbatim, owned3100 probe ECONNREFUSED. |
| Human AT / contrast / desktop zoom200% / real touch | **NOT RUN**; automated browser keyboard/mobile/scroll evidence is not human certification. |
| Live Groq/Gemini/ingestion/user-data mutations | **NOT RUN;0 calls**. All mutation tests use fake stores/RAM/synthetic buffers. |

## Current capability / browser acceptance matrix

| Capability | Current evidence |
| --- | --- |
| Session CRUD, title validation, menu/dialog keyboard/focus, current/other delete | Actual Chromium cases PASS from task02, plus backend/client/controller regressions. No UUID input required. |
| Session pagination60/refresh/reconciliation | Actual browser PASS; stale/duplicate/late-response guards covered by unit/integration fixtures. |
| Invalid/missing/deleted session routes | New browser invalid UUID +404/410 lookup cases PASS; keyboard return to Chat and no generation. |
| Composer creation→sidebar/deferred URL/new tab/history snapshots | Task03 real browser PASS; one confirmed creation, remote409/no resume, verified canonical navigation and deliberate recovery. |
| Three turns, request/session isolation, refresh | Existing browser + production-client fixtures PASS, distinct IDs and independent histories in backend/frontend isolation suites. |
| Stop/disconnect/post-header error/navigation cleanup | Actual browser PASS; native AbortSignal observed, partial text/terminal loading/recovery/no replay. |
| Copy/citations/Markdown/history fallback | Browser native clipboard/denied/code/375px drawer/focus and persisted citation fallback PASS; sparse/repeated/out-of-range fixtures PASS. History ordinal restoration remains unsupported and explicit. |
| Document upload/version/re-index/delete202→confirmed200/status/active | Task04 browser PASS, including320×568/375×568 dialogs, failed version preserves active, stale two-tab preflight, post-action GET failure and explicit refresh. |
| Document empty state/pagination | New browser PASS: empty→explicit refresh,21 items via offsets0/20 and reset0, no fake total or polling. |
| Safe pre-header errors | New browser422/404/409/429/503/network cases PASS: no arbitrary error detail rendered, composer unlocks, recovery and no auto replay; deliberate503 recovery succeeds. |
| Health | New browser PASS: no mount/check loop, explicit health/dependencies GET,503 degraded preserved, safe dependency messages, Groq remains unverified. No live outage induced. |
| Reader intent, keyboard, responsive layout | New actual wheel/upstream-growth/jump keyboard/Stop case PASS; skip link focuses main;320px document layout has no horizontal page overflow. Reduced-motion media is active, not a claim that every animation/contrast/AT requirement was audited. |
| Terminal/history parity | BUG-STREAM-001 FIXED with retained failing-before/passing-after regressions and full84 backend/198 frontend checks. |
| Real runtime/CORS/cloud availability | Offline CORS/contract PASS; live8000 check blocked by refused connection, not evidence of a frontend CORS regression. |
| Full manual accessibility | Human AT/contrast/desktop zoom/real touch remain NOT RUN and unwaived. |

## Approved minimal parity fix

The user explicitly approved bringing the minimal bugfix into this QA continuation, overriding the original separate-bugfix requirement in plan35.1. [Bug report and before/after evidence](./bugs/stream-terminal-parity.md).

Existing MessageRecord validation requires meaningful text for PARTIAL/COMPLETED. Preserve this invariant and all model/schema/persistence code. Encoder error status now follows the same classification, retaining every whitespace delta/content byte. Provider normal completion with only whitespace becomes RAG_STREAM_EMPTY/FAILED before persistence. Non-whitespace errors remain PARTIAL; no-content errors remain FAILED; IDs/sequence/usage/guard release are asserted.

The stream client no longer assumes every delta implies a PARTIAL answer. It permits FAILED after Python-whitespace-only deltas, still rejects FAILED with substantive content/PARTIAL without deltas, and retains legacy PARTIAL support so history mismatches continue warning instead of being hidden. Python whitespace parity is tested across its full whitespace set, with NEL/BOM controls. No API/SSE event shape, database schema, retrieval/LLM provider flow or frontend architecture changes.

An initial persistence-side attempt failed the existing model invariant and was fully reverted. Final application changes are confined to encoder classification and client transcript validation. No regression expectation was weakened to manufacture PASS; the original terminal/persisted equality and old frontend mismatch recovery remain tested.

## Technical-debt disposition — proposed, not silently accepted

| Item | Current decision / gate |
| --- | --- |
| BUG-STREAM-001 | **RESOLVED**, user-authorized minimal fix;84/84 backend and198/198 frontend PASS. |
| Codex in-app Browser import failure | Untouched. Repository Playwright works; no longer a blocker for automated DOM/browser coverage. Does not mean the plugin was repaired. |
| Full human accessibility | **OPEN, not waived.** Need developer human AT/contrast/zoom200%/touch results or explicit acceptance of deferral; no fabricated manual PASS. Prepared checklist remains available. |
| Dependency audit9 high | **OPEN, not accepted.** Current root advisory is braces stack-exhaustion DoS in deeply nested patterns, [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm), propagated through Next lint and shadcn/registry/ts-morph/glob chains. Direct flagged packages: eslint-config-next and shadcn. npm proposes major downgrades14.2.35/1.0.0, incompatible with blindly preserving current setup; no force fix. Runtime exploitability was not established. Proposed: a separate scoped dependency remediation/security review; only the user can accept residual risk for proceeding. |
| Live backend runtime/CORS | **OPEN environmental verification**, port8000 refused. Proposed: repeat the existing read-only verifier when developer starts the backend. No provider smoke or live mutation needed. |
| History ordered sources | Previously accepted baseline fallback retained: saved citation cards, unavailable ordinal links, no guessing. API persistence expansion is separate. |
| Deferred first-turn URL | Existing explicit banner/new-tab/verified terminal policy now browser-tested. Refreshing `/chat` mid-turn still needs sidebar/saved link. No stream resume or auto resend. |
| Sync ingestion/uncertainty | Preserve no progress/job/cancel/max-size claims. No public polling API, raw retention mock is not real filesystem proof. Read/confirm deliberately after uncertain outcomes. |
| Offset pagination/eager history | Existing duplicate/stale/reset guards; no snapshot isolation or large-history performance claim. Separate scalability work. |
| Live provider/cloud ingestion | NOT RUN by explicit scope, separate authorization required; no live smoke started. |
| Optional auth/scope/model/theme/edit/regenerate/message-delete/rollback/PDF | Outside requested MVP; no new features/dependencies added for QA. |

Gate remains IN PROGRESS until the open manual/security/integration items are explicitly resolved or dispositioned by the user. Automated tests passing do not accept those risks on the user's behalf. F7-03-02/03/04 remain COMPLETED; no next-task/F8-02/F8-03/live-smoke work is started.

## Files and repeatability

This continuation: `backend/app/api/chat.py`, `backend/tests/test_stream_terminal_parity.py`, `frontend/lib/api/chat.ts`, `frontend/tests/{chat-stream-client,functional-regression}.test.mjs`, new `frontend/e2e/functional-qa.spec.mts`; plan/current log, this report/initial report archive, parity bug report and scoped accessibility/browser/automated-test documentation. Other dirty work preserved. Existing frontend dependencies/config and backend conversation service/models remain unchanged.

Use existing frontend npm scripts and guarded backend runners listed above. Never run two Playwright CLIs concurrently against the same3100/output directory. Do not point mutation fixtures at a real backend. For remaining human observations record browser/OS/input/AT/viewport/zoom, steps and actual result using the [accessibility checklist](./frontend-accessibility-checklist.md) and [handoff](./frontend-browser-qa-blocker.md).

## F8-02 controlled live follow-up — 2026-10-15

User subsequently assigned and explicitly approved controlled live scope:5 Groq attempts,4 Gemini embedding requests, fresh temporary namespaces/raw storage and owned cleanup. [F8-02 report](./frontend-controlled-live-e2e.md), plan42:7/7 actual browser stages/3 completed turns PASS; actual4 Groq +4 Gemini attempts, no retry. Health, real isolated upload, same-session history/citations and document/session actions verified. Initial Mongo cleanup code8000 recovered by exact-namespace collection cleanup; fresh independent Mongo/Qdrant/raw absence checks and owned-server shutdown PASS.

This supersedes a blanket “live never run” interpretation, not the historical no-provider counts for earlier tasks/default tests. Default unit/mock scripts still make0 live calls; live is a separate opt-in runner. It also proves the controlled isolated runtime, not permanently configured developer8000/default deployment or the entire CORS matrix. Human manual/security debt remains unwaived; F7-03-05 status is unchanged. F8-03 NOT STARTED; no further provider calls under the exhausted Gemini approval.
