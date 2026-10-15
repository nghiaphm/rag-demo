# F8-02 — Controlled live E2E (2026-10-15)

**COMPLETED.** One controlled live execution,7/7 browser stages PASS, three COMPLETED turns, cleanup independently verified. This is a small live happy-path sample, not full release/security/accessibility or backend-scale certification. F8-03 is NOT STARTED; earlier F7 manual/security disposition remains open.

## Explicit scope and budget

The user approved at most5 Groq HTTP attempts including query rewriting, then separately approved at most4 Gemini embedding HTTP requests (3 queries + one tiny TXT), and a fresh temporary MongoDB/Qdrant namespace/raw directory with exact-namespace cleanup. No default database/corpus or pre-existing document was used for mutation/retrieval. No further paid requests were made after this run.

Initial probes of127.0.0.1:8000/3000 returned ECONNREFUSED. Read-only MongoDB ping and Qdrant connectivity succeeded. The runner checked that its fresh namespace did not exist before claiming ownership, then started its own backend8000 and production frontend3000 with process-only overrides. It did not edit `.env`, application config, routes, RAG logic or schema. Both owned servers were stopped afterward.

Run namespace: `f8_02_13a880b0bfc64daf8409451c9886b062` (now absent). Raw root was inside the ignored workspace folder `frontend/.playwright-tmp/<namespace>/raw` (now absent). Ignored evidence manifest: `frontend/.playwright-tmp/f8_02_13a880b0bfc64daf8409451c9886b062/report.json`, with separate browser/budget JSON files. These record owned IDs, counts, safe timing/usage and cleanup status, not credentials or raw provider answers.

The controlled backend uses the actual FastAPI application, Atlas/Qdrant, configured Groq model and Gemini embeddings. The only runtime provider-factory substitutions supply real SDK clients with retries disabled, HTTP attempt counters, approved caps and256 maximum output tokens per Groq request. No provider/retriever/answer fixtures were substituted. Groq SDK max_retries=0; Gemini attempts=1. HTTP error opens a circuit before any subsequent provider send. No test/stress retries.

| Provider | Approved maximum | Observed HTTP attempts |
| --- | --- | --- |
| Groq (generation + rewriting) |5|**4**|
| Gemini (query + document embeddings) |4|**4**|

Budget counts include attempts before HTTP send, not successful/billed token totals. Reported per-turn usage is generation usage; it excludes the separate rewrite request's token usage. Do not rerun the execute command under this spent approval; a further live run needs a fresh budget.

## Actual browser flow

| Stage | Actual result |
| --- | --- |
| Health | PASS real HTTP `/health` and `/health/dependencies`200/ok; header health UI reports MongoDB/Qdrant ready. UI makes genuine cross-origin calls3000→8000. |
| Prepare isolated corpus | PASS UI multipart upload of one tiny synthetic TXT containing a project code, support window and team. Real Gemini embedding/indexing returned201/INDEXED/activated; list refresh displayed the owned filename. This prerequisite runs before chat so citations have a real source. |
| New chat / three turns | PASS sidebar New Chat creates one backend session; three sequential questions reuse its ID. Three distinct request IDs and six distinct user/assistant message IDs; all SSE `done/COMPLETED`. Real persisted assistant content/status/request/session IDs match each observed stream exactly. No duplicate POST/resend. |
| Live citation | PASS inline[1] on the correct assistant opens source drawer selecting the uploaded filename/source[1]. No guessed document link or PDF viewer. |
| Refresh history / citation fallback | PASS reload restores three assistant replies and all three questions from backend. Persisted citation card opens correctly. Inline ordinal metadata is not exposed by history API, so the UI explicitly shows the saved-source fallback instead of fabricating[1] mapping. Both pre-refresh live inline citation and post-refresh persisted citation were checked. |
| Document operation | PASS explicit UI soft-delete confirmation receives HTTP200 cleanup complete; UI reports raw retention correctly. No new version/re-index request or additional embedding call. |
| Session API cleanup | PASS explicit UI session DELETE confirmation. Final teardown additionally removes only the owned temporary namespaces/raw data, including retained tombstones/history. |

Playwright Chromium156 headless was used through the repository SDK, not Codex in-app Browser. Unexpected browser request origins were blocked, uncaught page errors asserted absent; browser closed normally. No screenshot/video was requested or captured. Three streamed answers are synthetic QA responses; they are not stored in the committed report.

## Timing and usage

Client timing starts before `fetch`. “First delta” is a client-observed TTFT proxy to the first parsed content delta; it includes retrieval, embedding, rewriting, network and provider work. It is not provider-internal token latency. SSE parsing buffers frames across arbitrary read chunks; delta counts are not tokens or words.

| Turn | HTTP headers ms | First content delta ms | Terminal SSE ms | Input/output/total tokens reported |
| --- | ---: | ---: | ---: | --- |
|1|1684.0|6247.1|6357.5|345 /65 /410|
|2|2257.9|3121.3|3310.9|380 /101 /481|
|3|18133.0|19214.0|19406.5|428 /65 /493|

Only three observations; turn3 is slower, but no root cause/performance percentile is inferred from this sample. No extra provider requests were spent investigating timing.

## Cleanup evidence and recovered blocker

The initial automatic cleanup encountered MongoDB `OperationFailure`. This correctly left the run BLOCKED despite browser PASS. The owned Qdrant collection was already removed; raw cleanup had not yet run. No chat/embedding was retried.

Recovery confirmed `dropDatabase` returns code8000 for this environment. The exact owned database's collections could be dropped individually; that fallback succeeded. Do not infer a specific Atlas role/root cause solely from code8000. Cleanup targets now run independently so a Mongo/Qdrant error cannot skip raw cleanup. Namespace/nonce/resolved-path checks reject default, mismatched, outside-workspace or already-cleaned targets before deletion/startup.

Fresh read-only clients independently verified:

- MongoDB namespace absent (therefore no owned sessions/messages/documents/versions/jobs/tombstones remain).
- Qdrant collection absent (no owned test vectors remain).
- Exact raw directory absent.
- Owned8000/3000 ports return ECONNREFUSED after teardown.

Cleanup is **PASS**, not soft-delete-only. Raw removal was an explicit test teardown on the fresh owned directory; the document DELETE API itself still retains raw files. Ignored manifests/logs remain intentionally as evidence; they are not application test data.

## Verification performed

| Check | Actual result |
| --- | --- |
| Opt-in runner plan-only default + syntax checks | PASS; no network/provider calls in default mode. Initial sandbox Python attempt could not access the external interpreter; same existing interpreter worked with authorized escalation, no environment repair. |
| Offline `test_controlled_live_guards.py` | **PASS9/9**: caps/async cap/host checks/error circuit/explicit flags, cleanup ownership and independent raw/fallback behavior, internal backend rejects default/already-cleaned targets. New recovery guards were tested offline; the live flow was not repeated. |
| Live browser flow | **PASS7/7 stages**,3/3 completed turns,4 Groq +4 Gemini attempts; independent cleanup PASS. |
| `npm.cmd test` | **PASS198/198**, default mocked/offline tests;0 additional live provider calls. |
| `npm.cmd run build:e2e` after live run | **PASS7/7**; restored prior mock API production artifact. A normal production build with intended public API base remains necessary for ordinary deployment. |
| `npm.cmd run typecheck` / `npm.cmd run lint` | PASS / PASS0 warnings. |
| `npm.cmd run test:contract` | PASS45 schemas offline. |
| Diff/new-file whitespace/log archive | PASS; CURRENT_CHANGE15 entries, F7-02 archived verbatim before removal. |
| Full mock44-browser suite / broad backend suites / npm audit | NOT RERUN in F8-02; prior F7-03-05 evidence remains historical. No need to spend further provider calls for those offline checks. |

## Reproduction and limits

Plan only, from root (no paid calls):

```powershell
.\.venv\Scripts\python.exe backend/scripts/controlled_live_e2e.py
```

The execute mode requires all explicit budget/namespace approval flags and free owned8000/3000 ports. Do not reuse an existing server/corpus; do not start another run under the previous exhausted Gemini approval. Secrets come from the existing backend configuration and are not copied into scripts, reports, CLI arguments or frontend public variables.

Files in this task: `backend/scripts/controlled_live_e2e.py`, `backend/tests/test_controlled_live_guards.py`, `frontend/scripts/controlled-live-browser.mjs`, this report, FRONTEND_PLAN.md, CURRENT_CHANGE.md, docs/changelog/phase-02.md and a scoped addendum in the functional QA report. Prior dirty work preserved; no application implementation/dependency/config change.

Existing human AT/contrast/zoom/touch and9 high dependency advisories were not waived. The default developer deployment is stopped, not certified as permanently configured by this isolated run. Concurrent multi-session incident remains NOT REPRODUCED; this sequential three-turn smoke is not a concurrency/stress test. F8-03 has not started.
