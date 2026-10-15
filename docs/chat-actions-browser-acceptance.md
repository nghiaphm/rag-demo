# F7-03-03 — Chat Actions browser acceptance (2026-10-15)

**COMPLETED.** Scope: close the browser acceptance gap in FRONTEND_PLAN sections31.4/33 using the existing repository Playwright/Chromium156 runtime on Windows. Reuse the implemented composer session creation, sidebar invalidation, deferred URL/recovery, history provenance, Stop/copy/citations/SSE. No Edit/Regenerate/Delete Message, backend/API/schema/provider/dependency changes. Codex in-app Browser was not invoked or modified.

## Actual browser coverage

New `frontend/e2e/chat-actions.spec.mts` contains10 cases, with a separate RAM-only loopback mock per case, external-origin requests blocked and uncaught browser exceptions failing teardown. Existing12 browser cases remain in the suite.

| AC | Actual browser observation |
| --- | --- |
| Composer → sidebar | One POST session followed by stream with that returned ID; the new sidebar link is present while the reply is still generating. Composer remains read-only; keyboard Enter does not duplicate the request. |
| Deferred URL / new tab | Parent remains `/chat` while streaming, with explicit refresh limitation and correctly targeted recovery link. Enter opens history in a new tab without aborting the parent. That tab shows STREAMING as a backend snapshot, no Stop/live busy state and no automatic stream. |
| Remote409 / explicit reload | Deliberate submit from history receives actual pre-header409, releases composer and retains historical STREAMING. Exactly one intentional extra POST, no replay. Parent canonicalizes only after terminal/history verification; explicit history reload reads COMPLETED. |
| Refresh before canonical URL | Reload `/chat` during generation shows the empty workspace, not a pretend restored stream. Persisted session remains reachable in sidebar; open it to read saved partial text. One create/one stream, no automatic generation. |
| Failed verification | One503 history read or a lagging STREAMING history response after terminal retains completed local answer and recovery link on `/chat`. A second deliberate question reuses the same session; successful verification then canonicalizes. |
| Historical states | PENDING/STREAMING/FAILED/PARTIAL are separately tested from actual mock history DTOs with controlled status/content overrides. No Stop, live aria-busy or message spinner. Nonterminal states retain raw status and explicit reread; each click makes one GET, no stream. Terminal empty responses show no-content copy, not a preparation spinner. |
| Switch / cleanup | Native browser fetch is observed without replacing the transport: A's AbortSignal fires when navigating to B during generation. B has its own history and request session_id; no visible A question, no duplicate session creation/replay. Return/reload rereads A independently. |
| Copy | Native clipboard write receives exactly the full persisted assistant string and code string, including tabs/double spaces/newlines. Actual OS clipboard roundtrip is also checked. On Windows Chromium changes LF to CRLF; only this OS roundtrip assertion normalizes CRLF, while the writeText argument assertion stays exact. Denied permission displays the safe manual-copy fallback. |
| Citations / mobile keyboard | At375×812, Enter on the new assistant's citation selects source[1], page0 displays Trang1, drawer fits viewport, initial focus is Close and Escape returns focus to the same trigger. History reload retains saved citations, removes unavailable ordinal links and presents the explicit saved-source fallback. No fake document links. |

Existing workspace browser cases additionally cover3 successful turns/session reuse/refresh, Stop partial/recovery, post-header error/disconnect/no replay. Existing196 unit/component/integration tests cover distinct request IDs, late callbacks, invalidation coalescing/scopes, persisted content/status parity checks, sparse/repeated/out-of-range citations and clipboard failure modes.

## Proven focus defect and minimal fix

Before the fix, opening a citation ran `setSelected` in `CitationContent`. Its inline Markdown component functions were recreated, replacing the citation opener DOM node. A targeted browser regression stored the original element and proved `isConnected === false` after opening; Escape focus restoration was inconsistent. This was a real failure, not inferred from source alone.

`frontend/components/chat/citation-content.tsx` now memoizes the Markdown subtree by `message`. Source selection alone retains its renderers/trigger DOM; new message content/metadata still updates normally. No mapper, source order, streaming contract or persisted fields changed. The same regression now proves the original node stays connected and Escape restores focus; copy and history-fallback checks also pass.

Other test corrections did not change application behavior: use visible current-route nodes because Next Cache Components retains hidden DOM; do not assume a returned route must retain its old cancellation banner or that fetch abort guarantees server rollback. Test observes the actual AbortSignal instead. Await drawer closure before checking final focus. Initial TypeScript helper omitted the request body field; its test-only annotation was corrected without suppression.

## Verification

| Check | Result |
| --- | --- |
| `npm.cmd test` after UI fix | PASS196/196, skipped0. |
| `npm.cmd run build:e2e` | PASS7/7 production prerender after fix; mock public API base is process-only. No `.env` edits. Rebuild for another API base before normal integration use. |
| `npm.cmd run typecheck` / `npm.cmd run lint` | PASS / PASS0 warnings after final test changes. |
| `npm.cmd run test:contract` | PASS45 REST/SSE/health schemas, offline export/network blocked. |
| `npm.cmd run test:e2e` final suite | PASS22/22 Chromium headless, retries0/skipped0/flaky0/unexpected0. Includes10 new Chat Actions cases and12 existing regressions. |
| Diff / whitespace / archive / server cleanup | PASS; CURRENT_CHANGE15 entries, F6-02 archived before removal; owned3100 server probe ECONNREFUSED. Developer3000 untouched. |
| Backend broad suite / npm audit / live providers | NOT RERUN / NOT RERUN / NOT RUN. Prior BUG-STREAM-001 parity80/81 and9 high advisories remain open. Groq=0/Gemini=0. |

Reports: ignored `frontend/test-results/e2e-results.json` and `frontend/playwright-report/index.html`; failing runs produced error-context/screenshot/trace before diagnosis. One full run was21/22, failing an overly specific route-cache banner assertion; replaced with direct native abort evidence, no skip/retry or weakened error expectations.

## Files and limits

This continuation changes `frontend/components/chat/citation-content.tsx`, `frontend/e2e/fixtures.mts` (opt-in lagging history response), adds `frontend/e2e/chat-actions.spec.mts` and this report, and updates FRONTEND_PLAN.md/CURRENT_CHANGE.md/archive plus scoped accessibility/browser/functional/automated-test addenda. Other dirty work is preserved.

Remaining API limits are explicit: no stream resume; refresh of `/chat` before canonical navigation cannot restore the session without its link/sidebar; an uncertain create response cannot reveal a lost receipt; offset pagination is not a snapshot; REST history lacks ordered sources for ordinal mapping. Aborting fetch does not guarantee backend rollback. No change to these contracts.

This is scoped automated browser acceptance, not human AT/contrast/zoom/touch certification or full F7-03-05 acceptance. F7-03-02 remains COMPLETED; document/functional gates and BUG-STREAM-001/security debt are not waived. Concurrent RAG incident stays NOT REPRODUCED. Stop after this task; no live smoke or next-task work.
