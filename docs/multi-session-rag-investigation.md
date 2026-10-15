# Concurrent multi-session RAG isolation — 2026-10-15

**Final status: NOT REPRODUCED.** The intermittent Chrome incident has no confirmed root cause. No application fix is made or claimed. Browser Automation was not invoked, reset, patched or bypassed. Groq/Gemini live calls:0.

## Audit findings

| Layer | Source and actual behavior | Finding/limit |
| --- | --- | --- |
| Route/session creation | `frontend/app/chat/[sessionId]/page.tsx` → SessionChat → keyed ChatWorkspace; `lib/chat/controller.ts` sends its own sessionId, creates through POST sessions only when null | No global current_session_id or localStorage/sessionStorage session authority found in the application paths. Route-ready fixtures verify IDs through actual workspace callbacks/client. Actual historical Chrome requests were not available. |
| Hooks/clients/abort | useSessions/useSessionHistory controllers scoped to hook inputs; ChatController owns activeTurn and creates AbortController per accepted turn; API/SSE clients keep reader/parser/request buffers inside each call | Two workspace stores using the same loaded JS modules pass overlap/error/Stop tests. Hook lookup/history readiness is mocked; this is not two real browser realms or hydration QA. |
| Shared frontend module state | `lib/sessions/invalidation.ts` owns API-base-scoped listener sets | Read invalidation only, no active session ID/content mutation or route change. Refresh during the overlap preserves both active session IDs. Browser tabs ordinarily have separate module heaps; this investigation does not test browser extensions or tab restoration. |
| Session lookup/history/persistence | MongoConversationRepository get_session `_id`, list_messages session_id filter; ConversationHistoryLoader groups complete pairs within the requested session | Tests use the real repository queries/service/history loader against thread-safe fake collections. Each session has a distinct pre-existing complete turn; no crossed prompt history, stored message ownership, request ID or message ID observed. Real Mongo transactions/index/driver behavior is not exercised. |
| Guard | begin_generation filter includes session `_id`, deleted_at and active_generation_id=null; release includes owner request_id | Guard is per session, not a global generation lock. Both different-session streams reach the provider rendezvous before content. Same-session conflict tests remain green. |
| Rewrite | `app/query_rewriting.py` constructs per-call prompt/result; factory creates a rewriter; LangChainRewriteProvider may use cached get_llm client | Dependency-aware follow-ups rewrite using only the corresponding history. Provider error/timeout falls back to the original query, not an explicit chat error. This can reduce retrieval quality for unresolved references. No real provider quality/latency verified. |
| Active scope/retrieval | `rag/pipeline.py` loads history/scope per request; `rag/retriever.py` creates a retriever with captured active version tuple | ALL_ACTIVE sessions share the knowledge corpus intentionally. Same question may legitimately retrieve the same documents; session isolation is not a separate document index per session. Active-version lookup is request-time, not an atomic corpus snapshot. |
| Embedding/vector | get_embeddings is cached; Qdrant client in app.state is shared; retriever invokes embed_query and query with local args | Shared fake embedding/index objects pass the barrier tests. `QdrantVectorIndex.query` wraps query exceptions, but returns[] if collection_exists is false. No shared application-level query/result buffer found. SDK internals, real Qdrant consistency and rate limits are not ruled out. |
| Context/generation | PreparedRagStream is created per request; context budget/prompt construction uses request-local values; get_llm is cached | Dataclass is frozen but its nested sources list is not deeply immutable; no production mutation of a shared sources buffer was found. Fake shared LLM checks each prompt and yields request-owned text. Real Groq/SDK streaming behavior and nondeterminism remain unverified. |
| Error handling | API preparation error→HTTP502/503/404/410/409; post-header provider error→SSE error and persisted FAILED/PARTIAL | Injected embedding/vector failures do not become a successful no-information answer; the other session succeeds. Provider failure before/after delta produces error terminal, correct owner and status. Rewrite fallback is a separate quality/observability risk below. |

Cached settings/embedding/LLM clients and app-level Mongo/Qdrant connections are the shared objects identified. Their existence does not establish a race. No global current prompt/history/session/result state was found in the audited application code. No claim is made that all SDK/client internals are thread/event-loop safe under real concurrency.

## Where the no-information sentence comes from

`backend/app/rag/prompt.py:SYSTEM_INSTRUCTION` explicitly tells the LLM to say **“Không tìm thấy thông tin trong tài liệu”** when Context is insufficient. There is no application exception handler found that directly substitutes that sentence for an embedding/Qdrant/Groq error.

Possible paths, distinguished from the original incident:

- No allowed active versions→retriever returns[] without embedding/query; independently asserted with the production retriever.
- Qdrant collection does not exist→adapter returns[]; independently asserted with the production Qdrant adapter and fake client.
- Valid query returns no hits, or budget retains no chunks→pipeline uses `(không có tài liệu liên quan)`; prompt can lead to refusal. Source inspection confirms the budget/placeholder path.
- Rewrite provider timeout/error→original ambiguous query is used. The induced fixture returns no hits for that query, then its deterministic fake LLM returns the prompt-prescribed refusal. This demonstrates an allowed cascade, **not proof that a real rewrite failed during the developer incident**. The technical rewrite failure is not surfaced as a fatal chat error by current policy.
- Nonempty but irrelevant/insufficient context, or model variability→LLM can refuse. Nonempty metadata alone cannot prove the answer was present in the context. No real LLM test is performed.
- Embedding/vector failures→HTTP502 before SSE in persistent mode in these tests; post-header provider failures→SSE error. They are not automatically converted to the no-information sentence. Real 429/timeout rates and underlying SDK retry behavior are not measured.

Changing rewrite fallback, missing-collection behavior, client lifetime or session guards based on these possibilities would be speculative. No fix is applied. Current observability does not expose every rewrite decision/retrieval outcome to the browser, so the single anecdotal answer cannot identify which path occurred.

## Automated tests and results

```powershell
# From project root; external TCP blocked, loopback IPC allowed.
.venv/Scripts/python.exe backend/scripts/verify_multi_session_isolation.py

# From frontend; includes local HTTP fixtures only, no browser automation.
node --test tests/multi-session-isolation.test.mjs
node --test tests/*.test.mjs
npm.cmd run lint
```

- Backend runner **PASS67/67**:11 new investigation cases plus existing concurrency/history/rewrite/retriever/streaming/API/persistence/session suites.
- New backend cases: same dependent question; different questions; same independent question sharing ALL_ACTIVE corpus; one provider error after delta; provider error before delta; embedding timeout; vector timeout; empty retrieval; rewrite-provider failure→original query; missing collection; no active versions.
- Two HTTP requests use the real FastAPI router, real RAG preparation/rewrite/retriever/context/stream encoder, real ConversationService/MongoConversationRepository queries. Only storage/cloud/provider I/O is faked. Thread barriers in rewrite/embedding and an async provider rendezvous require overlap, with bounded waits that fail instead of silently running sequentially.
- Assert HTTP and typed complete SSE order/sequence/start IDs/metadata source IDs/delta content/terminal status/error, corresponding persisted user+assistant messages, own pre-existing history and released owner guards. Both stream consumers must enter before either emits content; pre-header failure cases instead require both embedding calls at the barrier before one fails.
- First test execution errored because the harness incorrectly instantiated SSETranscript without required events; corrected to `model_validate` with the complete events list. No application change was used to make tests pass.
- Frontend isolation **PASS3/3** in the final full run: two actual SessionChat→history→ChatPreview→workspace callback cases with fixture-ready lookup hooks and production REST/SSE clients to local HTTP mock. Fetch response headers are held at a two-request barrier, request signals are distinct, route/session IDs match payloads, error/Stop stay local, list reconciliation doesn't navigate either workspace. One test stops A while B completes; the other lets A complete while B receives SSE error. A third test starts two composers without a session, confirms exactly one creation each despite duplicate submit attempts, distinct receipts/stream payloads and verified separate histories.
- Full frontend regression **PASS196/196**; ESLint **PASS0 warnings**; diff/new-file whitespace checks recorded in FRONTEND_PLAN/CURRENT_CHANGE.
- Build/typecheck/contract/live smoke **NOT RUN again** in this test/documentation-only investigation; prior QA evidence remains separate. No application/config/API/schema/RAG change.

The new isolation runner is a targeted suite, not an all-backend PASS claim. It does not include the already known BUG-STREAM-001 whitespace-terminal parity regression; that separate F7-03-05 failure remains open and is not fixed or linked to this incident without evidence. F7/manual/F8 gate states are unchanged.

## Hypotheses and remaining risks

| Hypothesis | Conclusion |
| --- | --- |
| Application-wide current session/AbortController/history buffer | Not found in source; corresponding mock overlap cases pass. Not an explanation established for the incident. |
| Cross-session persistence/guard collision | Not reproduced with real repository query construction on fake collections; active guards/IDs remain owned. Real DB/driver failures remain outside this test. |
| Same question necessarily means same prompt/context | False when conversation history differs; rewrite may resolve identical pronouns differently. With independent query and ALL_ACTIVE, shared retrieval is valid. |
| All dependency exceptions are silently no-information answers | Not supported for embedding/vector/generation error paths tested. Rewrite exception fallback can indirectly reduce retrieval quality and needs live evidence to assess this incident. |
| Shared cached SDK/client concurrency | Still possible/unverified. Fake shared clients cannot rule out connection-pool/event-loop/provider-side behavior. No reason established to recreate clients or add a global lock. |
| Quota/rate limit, timeout, transient corpus state, model refusal | Plausible, not proven. No production trace, exact input/history/version snapshot or provider diagnostics from the event were supplied. |

## Proposed bounded live smoke — NOT RUN, developer approval required

This is a handoff for the developer to approve and execute; the Agent has not sent any live generation/embedding request. Limit the initial smoke to **one concurrent pair, two chat requests total**, with no automatic retries or stress loop. Rewriting may add provider calls when histories require it, so use fresh sessions for the first pair.

1. Approve the two-request live provider cost/scope. Keep the active corpus unchanged; do not upload/re-index/delete documents during the smoke. Choose one synthetic/nonprivate question already known to be answerable from an active document.
2. Use New Chat to create two distinct sessions, open their canonical routes in Chrome tabs A/B. Confirm the route IDs differ and DevTools POST payloads use the matching session_id; start with empty histories. Record time and active version IDs.
3. Submit the **same exact question once per tab nearly simultaneously**. Do not click retry/Stop until outcomes are recorded. No Agent Browser is involved.
4. For each request record HTTP status, session_id, SSE request/user/assistant IDs, event sequence and terminal status/code, source count/document/version/chunk IDs, and a brief outcome. Verify persisted history through the UI/API using the same session ID. Record useful server metrics/provider status codes if already available; do not include keys or raw private prompts/files in the report.
5. If one answer refuses: distinguish HTTP/SSE error from a COMPLETED refusal; distinguish empty metadata from nonempty context. Match per-request diagnostics. Without rewrite/retrieval diagnostics, do not infer collision from the sentence alone. Stop after that pair; any sequential baseline or history-aware follow-up pair needs a separately agreed allowance.
6. If reproduced, preserve the evidence and assign a focused diagnostics/bugfix task. Do not automatically alter guards, SDK caching, error contract or schema. If both succeed, record that smoke outcome only; it does not prove the intermittent issue fixed.

Files changed: `backend/tests/test_multi_session_isolation.py`, `backend/scripts/verify_multi_session_isolation.py`, `frontend/tests/multi-session-isolation.test.mjs`, this report, FRONTEND_PLAN.md, CURRENT_CHANGE.md, `docs/changelog/phase-02.md`. **Stop after investigation; no F8 or live provider smoke.**
