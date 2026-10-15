# F7-03-02 — Session Actions acceptance (2026-10-15)

**COMPLETED.** Existing implementation was audited and retained. The missing scoped browser AC were exercised through repository Playwright Test 1.64.1 / Chromium156 headless on Windows, desktop1280×800 and mobile viewports320×812/375×812, default zoom. No application, API contract, backend business logic or dependency changes were needed. No live backend/provider requests or mutations were made; Groq=0/Gemini=0.

## Browser observations

| Acceptance | Actual observation / evidence |
| --- | --- |
| Menu keyboard | Space/Enter open; first item receives focus; ArrowDown/ArrowUp move between Rename/Delete; Escape returns focus to trigger. |
| Rename dialog | Input initially focused; Shift+Tab wraps to Save, Tab wraps to input. Blank/201-emoji titles disable Save without PATCH. A padded Unicode title sends exactly one trimmed PATCH to the correct session; returned title appears in sidebar, active link remains correct, focus returns to renamed trigger. |
| Confirm/cancel/current delete | Existing workspace E2E verifies Hủy initial focus, Escape sends no DELETE, confirmed current deletion sends one DELETE then navigates to `/chat`, closes dialog and focuses New Chat. |
| Other-session delete | Delete B while viewing A; URL/aria-current remain A, B disappears; authoritative list and total refresh to59. |
| Pagination/refresh | `/many`60-session fixture: initial50, Load More reaches60 unique links, no extra page button; after deletion list resets to50/59, load reaches59 and explicit refresh resets to first50. |
| Mobile320/375 | Open sidebar/session delete via keyboard; Tab/Shift+Tab stay within confirmation, dialog bounding box fits viewport; Escape returns focus to session trigger, next Escape closes sidebar and returns focus to header toggle. Cancel sends no mutation and preserves route. |
| Remote409 | Second browser page starts a real mock SSE stream for A. First page's DELETE receives actual HTTP409 from mock active-generation guard. Alert remains in dialog, confirmation disables, URL/row retained; explicit review refresh closes dialog and keeps active link. Stop in second page releases loading; exactly one DELETE, no replay. |

Sources: `frontend/e2e/session-actions.spec.mts` (5 cases) and existing session case in `frontend/e2e/workspace.spec.mts`. Fixture gained a per-test `streamDelayMs` option so remote stream remains active while the confirmation runs; no fixed sleeps or provider calls. Each case owns a RAM-only mock and fails on unexpected request origins or uncaught browser exceptions.

Initial focused run:2/5 PASS,3 assertion failures. Source/error-context inspection showed incorrect test assumptions: Space already focuses the first menu item; count caption is only rendered while more sessions remain; existing history contains multiple Markdown headings. Assertions were corrected without UI changes. Focused rerun5/5 PASS; final complete suite12/12 PASS, retries0, skipped0, flaky0, unexpected0;39.1s.

## Checks rerun in this task

| Command / check | Actual result |
| --- | --- |
| `npm.cmd test` | PASS196/196,0 skipped; includes session validation/receipts, error statuses404/410/409/422/429/503/network, idempotence, duplicate/pending guards, late/stale response and pagination fixtures. |
| `npm.cmd run test:e2e` | PASS12/12 actual headless Chromium cases across session/chat/document/error/cancel. JSON: `frontend/test-results/e2e-results.json`; HTML: `frontend/playwright-report/index.html` (generated/ignored). |
| `npm.cmd run build:e2e` | PASS7/7 prerender; process-only mock API base override, no `.env` edits. Rebuild normally before using a different public API base. |
| `npm.cmd run typecheck` / `npm.cmd run lint` | PASS / PASS0 warnings. |
| `npm.cmd run test:contract` | PASS45 REST/SSE/health schemas, offline/network disabled. |
| Backend `test_session_actions`, `test_sessions_api`, `test_conversation_concurrency` | PASS11/11 with root `.venv` Python and external TCP blocked; atomic active-generation guard, repeated tombstone cleanup and router fixtures. Initial command mistakenly used backend-local `.venv` and did not execute; corrected root interpreter run passed. |
| Diff / new-file whitespace / archive | PASS; CURRENT_CHANGE retains15 entries, F6-01 archived verbatim. |
| Owned server cleanup | Final probe of127.0.0.1:3100 returned ECONNREFUSED; developer server3000 untouched. |

## Limits and remaining gates

This is browser automation evidence for the session-actions AC, not a human screen-reader or real touchscreen certification. Human AT, contrast, zoom200%, full chat/citation/document accessibility remain outside this task and are not marked PASS. Codex in-app Browser runtime was neither invoked nor modified.

Known unrelated BUG-STREAM-001 (prior backend parity80/81,1FAIL) and npm audit9 high remain open; neither broad check was rerun or fixed here. Session tests do not waive them. Concurrent RAG incident remains NOT REPRODUCED. F7-03-03/04/05 status is unchanged; no live smoke or next task started.

Changed in this continuation: `frontend/e2e/fixtures.mts`, new `frontend/e2e/session-actions.spec.mts`, this report, FRONTEND_PLAN.md, CURRENT_CHANGE.md, docs/changelog/phase-02.md and scoped evidence addenda in accessibility/browser/functional/automated-test reports. Prior worktree changes were preserved.
