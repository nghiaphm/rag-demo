# RAG Conversation Audit — Round 0B-02

Date: 2026-10-29 (Asia/Bangkok). Read-only audit of conversation lifecycle, MongoDB persistence, SSE, guards and recovery. References: [CODEBASE-INVENTORY.md](CODEBASE-INVENTORY.md), [RAG-CORE-AUDIT-0B01.md](RAG-CORE-AUDIT-0B01.md). Current implementation takes precedence over both documents and READMEs.

## 1. Executive Summary

The production repository uses a per-session conditional MongoDB update to acquire the generation guard and reserve two sequences; assistant terminal replacement is conditional on message/session/request identity and an active state. These are useful single-record safeguards, not a transaction across guard, message pair, terminal record and network delivery ([conversation_repository.py:117–220](backend/app/conversation_repository.py#L117)).

Source inspection establishes three conditional correctness defects: the transcript validator contradicts whitespace-only runtime errors; failed transition into STREAMING can leave a durable unguarded PENDING message; guard-release failure after successful terminal persistence can make wire outcome contradict history. A separate confirmed recovery gap concerns abandoned session guards. No backend fault scenario was executed; those classifications rely on precise source paths, not assumed production incidents.

| Category | Summary | IDs / verification |
| --- | --- | --- |
| Confirmed defects | Whitespace transcript/schema divergence; incomplete stream-start rollback; terminal outcome overwritten by a subsequent release failure. | C01–C03; source-proven conditional paths, NOT runtime-reproduced |
| Confirmed gaps | No automatic stale-guard/abandoned-turn recovery in the inspected application lifecycle. | C04; source-confirmed absence, actual crash behavior NOT_VERIFIED |
| Design risks | Preparation before guard; multi-write ambiguity; response/cancellation ownership handoff; unbounded cleanup/finalization phases; non-snapshot pagination. | C05–C09; explicit scenarios remain NOT_VERIFIED |
| Documentation discrepancies | README's delta-based error rule and atomic pair wording do not describe current runtime/production write guarantees precisely. | C10; DOCUMENTATION_MISMATCH |
| Tests executed | Three existing Node test files, 30 tests: **30 PASS, 0 FAIL, 0 skipped**. They exercise transport/controller/history with in-memory mocks. | Section 9; no real HTTP server, MongoDB or provider verification |
| Tests not executed | All Python/backend tests, Python-dependent Node tests, contract export, browser E2E, live smoke/restart/chaos checks. | NOT_EXECUTED; existing broken Python environment left unchanged |

Recommendation: prioritize C01–C03 with focused fault-injection regressions, then define safe recovery for C04 and validate C05–C09. This report does not authorize implementation or assign a final project maturity level.

## 2. Audit Scope & Methodology

Inspected the **production** `MongoConversationRepository`, `ConversationService`, models/indexes/schemas, session/chat handlers, SSE encoder/transcript schema, provider normalization and history loader. Reviewed relevant test bodies and compared their fakes with repository behavior. Read frontend API/history/controller logic only where needed to assess conversation restoration and recovery; no frontend styling or UX audit was performed.

Evidence methods: numbered source reads, branch tracing, explicit failure/interleaving reasoning, coverage searches and selected existing offline Node tests. Local Starlette source was consulted to understand response-start versus iterator timing ([.venv/Lib/site-packages/starlette/responses.py:224–285](.venv/Lib/site-packages/starlette/responses.py#L224)); local metadata reports Starlette 1.7.0 (`.venv/Lib/site-packages/starlette-1.7.0.dist-info/METADATA:3`). That is dependency-source evidence, not proof of deployed server behavior. Threadpool wrapper delegates to AnyIO ([.venv/Lib/site-packages/starlette/concurrency.py:36–38](.venv/Lib/site-packages/starlette/concurrency.py#L32)); disconnect/cancellation semantics must not be inferred from service-unit tests alone.

Classifications:

- **CONFIRMED_DEFECT:** source demonstrates an invariant violation for a specified input/fault; does not mean it happened in production.
- **CONFIRMED_GAP:** required recovery behavior is absent in the inspected path.
- **DESIGN_RISK:** plausible timing/infrastructure scenario requiring verification.
- **DOCUMENTATION_MISMATCH:** documentation contradicts or overstates implementation.
- **NOT_VERIFIED:** insufficient execution evidence, including every unexecuted backend scenario below.

High severity means possible durable lifecycle inconsistency or persistent session blockage; Medium means bounded contract, restoration or availability impact; Low means documentation/operator confusion. Severity does not quantify incidence.

No application startup, database/provider access, migrations, environment repair, package installation, source/configuration/README edits or new test files. The only created artifact is this report. Existing Node tests transpile source in memory and use injected API/service mocks; no build was needed. The already-broken Python environment was not invoked or repaired this round; `.venv/pyvenv.cfg:1–3` still records its external Python310 location. Its executable availability and backend runtime were not revalidated.

## 3. Conversation Lifecycle Assessment

### Session lifecycle

| Operation | Actual behavior and exact implementation | Guarantee / limitation |
| --- | --- | --- |
| Create | Title-only request; default title/scope/UUID/timestamps from model; insert_one; HTTP 201. [conversation_schemas.py:11–22](backend/app/conversation_schemas.py#L11), [conversation_service.py:72–74](backend/app/conversation_service.py#L72), [conversation_repository.py:49–56](backend/app/conversation_repository.py#L49), [api/sessions.py:85–94](backend/app/api/sessions.py#L85). | New identity per request; no client-controlled request/session idempotency contract. |
| List/get | Lists deleted_at=null sorted updated_at DESC then _id DESC; get distinguishes missing from tombstone. [conversation_repository.py:58–84](backend/app/conversation_repository.py#L58). | Missing → 404; deleted → 410 via [api/sessions.py:39–49](backend/app/api/sessions.py#L39). Count/list reads are separate. |
| Rename | Conditional live-session update changes title/updated_at only, preserving active guard. [conversation_repository.py:86–98](backend/app/conversation_repository.py#L86), [api/sessions.py:128–139](backend/app/api/sessions.py#L128). | Rename is allowed during generation; no conversation-content mutation. |
| Delete | Checks guard; atomically tombstones only a live unguarded session, then delete_many messages. Repeated delete keeps tombstone and retries message cleanup. [conversation_repository.py:222–258](backend/app/conversation_repository.py#L222). | Acknowledged guard/delete ordering prevents normal new generation after tombstone. Multi-step deletion is not atomic; failed cleanup can leave inaccessible records until retry. |
| After deletion | Public get/history and generation session checks reject deleted state; session list excludes tombstone. [conversation_repository.py:58–84,100–104,121–145](backend/app/conversation_repository.py#L58). | A read already in flight can race deletion; no global read revocation/snapshot guarantee (C09). No tenant/authentication conclusions. |

### Message lifecycle, ordering and request linkage

`begin_generation` atomically requires `_id=session_id`, deleted_at=null and active_generation_id=null, sets owner/start timestamp and increments next_message_sequence by two. It returns the prior sequence and the next value. Different sessions use different Mongo documents; there is no global application guard ([conversation_repository.py:117–147](backend/app/conversation_repository.py#L117)). The unique `(session_id, sequence)` index prevents duplicate stored sequence values when installed; request_id index itself is not unique ([conversation_indexes.py:28–46](backend/app/conversation_indexes.py#L28)). Index presence in running MongoDB is NOT_VERIFIED.

| Mode/event | Stored transition | Source |
| --- | --- | --- |
| Both persistent modes | USER COMPLETED + ASSISTANT PENDING share a server request_id; distinct message UUIDs and adjacent sequences. | [conversation_service.py:107–129,192–214](backend/app/conversation_service.py#L107) |
| JSON successful answer | ASSISTANT PENDING → COMPLETED with exact result text, verified citations, normalized usage and completion time. | [conversation_service.py:131–155,175–184](backend/app/conversation_service.py#L131) |
| JSON generation failure / explicitly raised cancellation | Attempts FAILED with safe RAG_PIPELINE_ERROR / GENERATION_CANCELLED; finally releases guard. | [conversation_service.py:157–186](backend/app/conversation_service.py#L157) |
| SSE start | PENDING → STREAMING before handler returns StreamingResponse. | [conversation_service.py:214–229](backend/app/conversation_service.py#L214) |
| SSE success | STREAMING → COMPLETED before done, only after encoder has meaningful content. | [api/chat.py:209–237](backend/app/api/chat.py#L209), [conversation_service.py:232–278](backend/app/conversation_service.py#L232) |
| SSE provider error/timeout/cancel | PARTIAL with meaningful content; FAILED otherwise. Exact whitespace remains stored. | [api/chat.py:195–244,278–297](backend/app/api/chat.py#L195), [conversation_service.py:244–273](backend/app/conversation_service.py#L244) |

Message model requires USER COMPLETED and nonblank content, disallows assistant attachments and user citations/model/usage, requires meaningful content for assistant COMPLETED/PARTIAL and safe error_code for FAILED ([conversation_models.py:136–186](backend/app/conversation_models.py#L136)). It validates record shape; it is not a state-machine transaction. Repository replacement predicates enforce PENDING→STREAMING and active→terminal ownership by message/session/request IDs ([conversation_repository.py:186–220](backend/app/conversation_repository.py#L186)). Terminal records cannot normally be finalized twice through this method; a second attempt conflicts rather than returning idempotent success.

Sequence reservation precedes message insertion, so failed creation can leave **gaps**. Monotonic stable order does not imply a gap-free history or successful turn for every reserved pair. Client resubmission allocates a fresh request_id/pair; guard and unique sequence index do not deduplicate a repeated logical question. Frontend avoids automatic replay, but server-side exactly-once request execution is not promised here ([conversation_service.py:107–129](backend/app/conversation_service.py#L107), [frontend/lib/api/chat.ts:245–247](frontend/lib/api/chat.ts#L245)).

## 4. Persistence & History Assessment

### Atomic and multi-step boundaries

Atomic at the Mongo single-document level: guard acquisition/sequence increment, owner-qualified release, title update, tombstone predicate, assistant state replacement. Multi-step: guard → insert_many pair → mark STREAMING → terminal replacement → guard release; tombstone → message delete_many. `insert_many(ordered=true)` is not a transaction; on error `create_message_pair` attempts delete_many of its two generated IDs and suppresses cleanup failure ([conversation_repository.py:117–258](backend/app/conversation_repository.py#L117)). This prevents many ordinary half-write outcomes but does not prove absence of orphans under crashes/ambiguous writes (C06).

Service finalization releases the guard in finally even if terminal persistence fails. That helps liveness when release succeeds but can leave an active-status message while allowing later turns. Conversely, terminal persistence can succeed and guard release fail, causing a transport failure despite durable terminal success (C03). There is no write/result reconciliation API in this inspected path ([conversation_service.py:175–186,274–278](backend/app/conversation_service.py#L175)).

### Public history versus RAG history

Public history first checks live session, counts messages, then reads one page ordered sequence ASC/_id ASC. It returns **all stored statuses**, including partial/failed/pending, with offset/limit/total ([conversation_repository.py:100–115](backend/app/conversation_repository.py#L100), [api/sessions.py:142–164](backend/app/api/sessions.py#L142)). A stable sorting key prevents nondeterministic ordering of unchanged records; it does not make multiple requests a consistent snapshot (C09).

RAG history loads all pages, groups by request_id, accepts exactly two same-session adjacent USER COMPLETED/ASSISTANT COMPLETED messages, sorts turns by sequence. Default filters out incomplete and unsuccessful turns; diagnostic opt-in allows PARTIAL/FAILED assistants, never active ones ([history.py:66–139](backend/app/history.py#L66)). It excludes malformed/orphaned turns from the prompt, **not from the database**. JSON creates its current placeholders before preparation; that pending assistant causes its own pair to be excluded rather than self-included. SSE prepares before inserting the new pair ([conversation_service.py:129–132](backend/app/conversation_service.py#L129), [api/chat.py:453–470](backend/app/api/chat.py#L453)).

### Persisted metadata and restoration

- USER attachments persist only resolved document/version/file_name references; references survive history serialization, with default [] for older messages ([conversation_service.py:112–119,197–204](backend/app/conversation_service.py#L112), [conversation_models.py:145–146](backend/app/conversation_models.py#L145), [api/sessions.py:65–81](backend/app/api/sessions.py#L65)). Document lifecycle correctness is outside this round.
- Assistant citations are recomputed from final text and retrieved source identities; partial meaningful answers can retain verified citations, FAILED gets none. Usage/model/request/error/timestamps are stored and returned ([conversation_service.py:140–155,251–273](backend/app/conversation_service.py#L140), [conversation_schemas.py:58–87](backend/app/conversation_schemas.py#L58)). Usage can be null; raw provider error strings are not persisted by these handlers.
- Ordered retrieved sources, citation ordinals and source sheet/row details are not fields of MessageRecord/MessageCitation. Consequently fresh restored messages have sources=[] and saved citation identities; complete ordinal reconstruction is unavailable by design, as already recorded in 0A/0B-01 ([conversation_models.py:108–153](backend/app/conversation_models.py#L108), [frontend/lib/sessions/history.ts:120–142](frontend/lib/sessions/history.ts#L120)). This deliberate metadata limitation is not counted as a new defect.
- Client history loader checks session IDs, pagination progress/count, duplicate IDs/sequences and final order; abort/current-controller checks reject stale responses on switching ([frontend/lib/sessions/history.ts:27–67,97–116](frontend/lib/sessions/history.ts#L27), [frontend/hooks/use-sessions.ts:45–89](frontend/hooks/use-sessions.ts#L45)). It loads raw stored states rather than only completed RAG turns.
- After a validated terminal, ChatController reads history once and compares local/persisted IDs, request linkage, role, content, status, user attachment references and assistant model/usage/error code. It adopts server-recomputed citations and keeps any current live sources. Mismatch warns and preserves local content; it does not replay generation ([frontend/lib/chat/controller.ts:311–354](frontend/lib/chat/controller.ts#L311), [frontend/lib/chat/services.ts:9–29](frontend/lib/chat/services.ts#L9)). The 30 executed Node tests support these mocked controller behaviors, not real backend durability.

## 5. SSE Streaming Assessment

### Runtime trace and guarantees

1. FastAPI validates the shared ChatRequest; handler resolves attachments, checks cloud clients, prepares history/retrieval/prompt in a worker, then creates persistent turn if requested. Errors here are HTTP JSON errors, before response headers ([schemas.py:99–124](backend/app/schemas.py#L99), [api/chat.py:439–501](backend/app/api/chat.py#L439)).
2. Handler returns StreamingResponse with `text/event-stream`, no-cache/no-transform and X-Accel-Buffering:no. Existing persistent guard/messages already exist; response body generator has not necessarily begun ([api/chat.py:503–516](backend/app/api/chat.py#L503)). Local Starlette sends http.response.start before iterating the body ([responses.py:250–257](.venv/Lib/site-packages/starlette/responses.py#L250)); C07 covers the ownership gap.
3. Encoder converts source DTOs, emits start sequence=1 with durable IDs, metadata sequence=2 with model and sources. Realtime citation events are deliberately absent despite schema support because verified answer ordinals are known later ([api/chat.py:128–168](backend/app/api/chat.py#L128)).
4. `astream_rag_answer` calls LLM astream and normalizes text/usage. Nontext/empty text chunks are omitted; textless final usage still propagates ([rag/pipeline.py:228–239,265–309](backend/app/rag/pipeline.py#L228)). Encoder tracks latest usage, appends exact text and emits successive delta frames ([api/chat.py:169–194](backend/app/api/chat.py#L169)).
5. Deadline applies to provider iteration. Empty/no-meaningful-content completion becomes RAG_STREAM_EMPTY; timeout becomes RAG_STREAM_TIMEOUT; ordinary provider exception becomes RAG_STREAM_ERROR. Provider close is attempted in finally ([api/chat.py:169–213](backend/app/api/chat.py#L169)). This is not an end-to-end request/persistence deadline (C08).
6. Persistent finalization is awaited before terminal frame; one done on normal success, otherwise one error whose status uses content.strip(). Finalization exception becomes STREAM_PERSISTENCE_ERROR; finalized flag is set even when the call raises ([api/chat.py:214–253](backend/app/api/chat.py#L214)). C03 describes a deterministic fault-path parity issue.
7. Cancellation/GeneratorExit during an entered wrapper attempts shielded inner close and, if not already finalized, shielded persistent cancellation finalization, then rethrows. A disconnected client cannot be guaranteed a terminal frame; cleanup exceptions are suppressed ([api/chat.py:256–312](backend/app/api/chat.py#L256)). Direct generator-close tests do not prove every ASGI disconnect path.

For the normal connected provider-success/error/empty/timeout branches with successful encoding/finalization, the encoder has a single terminal branch and monotonic sequences. No unconditional "exactly one terminal for every possible connected path" guarantee is justified: prefix/internal errors outside provider try are rethrown, cleanup/finalization may stall, response send may fail (C07/C08). Event creation/accumulation occurs before downstream network delivery; stored text equals generated yielded text on tested logical paths, not proof of bytes actually received/acknowledged by the browser.

### Schema versus runtime

Typed individual event models enforce field shapes, sequence>=1 and terminal literal values; `encode_sse_event` serializes each independently. `SSETranscript` checks whole-list start/terminal uniqueness, contiguous sequence, ordering and citation-source membership, **but production encoder does not instantiate a full SSETranscript** ([sse_schema.py:20–207](backend/app/sse_schema.py#L20), [api/chat.py:44–56,118–253](backend/app/api/chat.py#L118)). Its error status rule uses delta presence instead of meaningful content; it rejects current whitespace-only FAILED streams (C01). A passing event-schema unit test is therefore not proof of runtime transcript consistency.

### Error safety and cancellation limits

Normal provider exceptions after headers are mapped to fixed safe error codes/messages; exception strings and credentials are not copied into these frames. JSON generation failure envelope is similarly sanitized. Session/repository errors map to fixed details. Generic persistent JSON errors expose the exception **class name**, not its raw string ([api/chat.py:82–115,197–200,239–251,370–395,480–501](backend/app/api/chat.py#L82)). These observations concern inspected client response construction, not every dependency/logging path; no raw-provider-error leak was found in those normal branches. No real provider error or credential-bearing exception was generated.

JSON runs preparation/generation in a worker; raising CancelledError inside generate is covered by service code, but browser abort need not inject it into an executing SDK worker. SSE cancellation during preparation, before response iteration, while yielding, during provider await and during terminal persistence have different ownership states. They must be verified separately (C07/C08). No live or ASGI cancellation experiment was performed.

## 6. Concurrency & Session Guard Assessment

### Enforced source properties

- Same-session guard acquisition is a single conditional find_one_and_update with sequence reservation; a losing request gets conflict before it writes a pair. Only matching request owner can release. Terminal replacement requires matching request/session/message IDs and active status ([conversation_repository.py:117–220](backend/app/conversation_repository.py#L117)).
- Distinct sessions have separate guard/sequence documents; model factories are cached but request prompt/history/prepared state are local to the request ([rag/pipeline.py:64–155](backend/app/rag/pipeline.py#L64)). Existing isolation tests use mocked components; live shared-client behavior remains NOT_VERIFIED.
- Delete's atomic predicate also requires guard=null. If acquisition wins, delete cannot tombstone; if tombstone wins, subsequent acquisition cannot succeed. Rename does not clear the guard ([conversation_repository.py:86–98,121–145,222–258](backend/app/conversation_repository.py#L222)). Tests directly exercise the production delete predicate through fake collections ([test_session_actions.py:53–84](backend/tests/test_session_actions.py#L53)).
- There is a guard timestamp but no expiration/lease/stale-session recovery in these methods or startup. Hard process death does not run finally (C04; [main.py:20–38](backend/app/main.py#L20)).

### Explicit interleavings — none executed

| Scenario | Event order and conclusion | Evidence/classification |
| --- | --- | --- |
| Same-session ordinary overlap | A acquires guard → B attempts acquisition while A active → B conflicts → A finalizes/releases. Correct intended exclusion, conditional on database atomicity/index availability. | Repository predicate above; NOT live-verified. |
| Stale SSE preparation | B loads history H before guard → A acquires/finishes turn → B finishes its earlier preparation → B acquires freed guard → B generates from H, omitting A's completed turn. | [api/chat.py:453–470](backend/app/api/chat.py#L453); C05 DESIGN_RISK, not an observed race. |
| Rejected SSE performs preparation | A holds guard → B prepares retrieval/possibly query rewriting → B attempts guard and gets 409. No B message pair, but preparation was not protected by guard. | Same path; C05. No provider call was made in this audit. |
| Delete during SSE preparation | B prepares without guard → delete tombstones session → B acquisition fails 410; prepared work is discarded. Existing predicate prevents normal post-delete pair creation. | [conversation_repository.py:121–145,233–255](backend/app/conversation_repository.py#L121); runtime timing NOT_VERIFIED. |
| Terminal write then release failure | A terminal replacement succeeds → release raises → service propagates error → SSE emits PARTIAL/STREAM_PERSISTENCE_ERROR even though durable message is COMPLETED. | C03 source-proven conditional error path; no timing race required. |
| Response never enters body | Durable STREAMING turn returned → response header send/cancellation fails before first anext → generator's cleanup body never executes. | C07 DESIGN_RISK; local framework source supports boundary, actual server behavior NOT_VERIFIED. |
| Crash after guard | Atomic guard commit → process exits before cleanup → later acquisition/delete rejects active owner indefinitely absent operator recovery. | C04 CONFIRMED_GAP; no crash executed. |

No evidence justifies claiming distributed exactly-once generation, guaranteed cleanup on all disconnects, or automatic abandoned-session repair.

## 7. JSON/SSE Contract Comparison

| Aspect | POST /chat | POST /chat/stream | Assessment / exact source |
| --- | --- | --- | --- |
| Request | ChatRequest; optional session UUID, normalized question, validated attachment references. | Same DTO and attachment resolver. | Shared validation: [schemas.py:99–124](backend/app/schemas.py#L99), [api/chat.py:315–341,439–452](backend/app/api/chat.py#L315). |
| Preparation | Stateless answer_question; persistent service guard/pair before callback prepares RAG. | prepare_rag_stream before guard/pair. | Same underlying builder, different lifecycle order: [api/chat.py:342–369,453–470](backend/app/api/chat.py#L342), [rag/pipeline.py:158–225](backend/app/rag/pipeline.py#L158). C05. |
| IDs | Full response carries persistent session/message/request IDs; null persistent fields in stateless. | start carries equivalent durable IDs; stateless null fields. | [api/chat.py:132–149,397–421](backend/app/api/chat.py#L132). SSE pre-header failure need not return IDs. |
| State progression | USER COMPLETED; assistant PENDING→COMPLETED/FAILED. | USER COMPLETED; assistant PENDING→STREAMING→COMPLETED/PARTIAL/FAILED. | [conversation_service.py:97–278](backend/app/conversation_service.py#L97). Partial streamed output has no equivalent normal JSON partial response. |
| Answer | One complete nonblank answer; failure envelope answer=null. | Exact concatenation of textual delta.content; partial/whitespace characters retained on errors. | [rag/pipeline.py:175–188,265–279](backend/app/rag/pipeline.py#L175), [api/chat.py:186–213](backend/app/api/chat.py#L186). Same prompt does not imply byte-identical outputs across independent provider calls. |
| Sources | Returned selected ordered source DTO array. | metadata selected ordered source DTO array. | [api/chat.py:151–159,403](backend/app/api/chat.py#L151). Same prepared-source concept. |
| Citations | Verified ordinals mapped after whole answer; also stored. | No realtime citation emission; persisted terminal message computes citations after answer. | [api/chat.py:161–163,404–408](backend/app/api/chat.py#L161), [conversation_service.py:261–265](backend/app/conversation_service.py#L261). Deliberate timing difference. |
| Usage | Normalize whole response usage; null when absent. | Normalize stream chunks; latest nonnull usage included in terminal and persisted; textless usage allowed. | [rag/pipeline.py:228–239,282–309](backend/app/rag/pipeline.py#L228), [api/chat.py:181–183,237–250](backend/app/api/chat.py#L181). No guarantee all providers emit usage. |
| Generation error | Typical service-caught failure → safe 502 ChatResponse with failed durable IDs; pre-logical failures keep FastAPI detail. | Pre-header HTTP error; after headers 200 plus error frame. Persistent generic initialization failure uses 502 detail; stateless uses failure envelope. | [api/chat.py:370–395,480–501,239–253](backend/app/api/chat.py#L370). Not identical error envelopes across modes/stages. |
| Persistence timing | Terminal write and release attempted before HTTP response. | Terminal write and release attempted before terminal SSE; browser may already have answer deltas. | [conversation_service.py:175–186,274–278](backend/app/conversation_service.py#L175), [api/chat.py:214–253](backend/app/api/chat.py#L214). C03 distinguishes durable success from release failure. |
| Recovery | No server idempotency/resume contract; worker may finish despite disconnect. | No resume/replay; client fetches history after terminal, aborts old work and warns on mismatch. | [frontend/lib/api/chat.ts:245–247](frontend/lib/api/chat.ts#L245), [frontend/lib/chat/controller.ts:207–220,311–354](frontend/lib/chat/controller.ts#L207). Client abort is not evidence backend work was undone. |

## 8. Findings Register

### C01 — Backend transcript validator contradicts whitespace-only runtime terminal classification

- **Classification/severity:** **CONFIRMED_DEFECT — Medium**; source-proven contract divergence, backend runtime reproduction NOT_EXECUTED.
- **Location:** `SSETranscript._validate_transcript`, [sse_schema.py:186–194](backend/app/sse_schema.py#L186); `_encode_provider_stream_impl`, [api/chat.py:209–244](backend/app/api/chat.py#L209); `finalize_streaming_turn`, [conversation_service.py:244–250](backend/app/conversation_service.py#L244).
- **Expected invariant:** transcript validation accepts encoder output for all supported terminal classifications; meaningful-content rule agrees with persistence.
- **Actual behavior:** runtime maps whitespace-only text to FAILED/RAG_STREAM_EMPTY or FAILED on provider error. Transcript schema instead demands PARTIAL after **any** delta. Conversely done validation only tests reconstructed string truthiness and can accept whitespace-only success that runtime rejects. Production does not apply full transcript validation, so this does not mean its HTTP encoder currently crashes on whitespace.
- **Deterministic reasoning:** start(1), metadata(2), delta(3," \n\t "), error(4,FAILED) is produced by the current whitespace path. Schema computes has_delta=true, expected=PARTIAL and raises. No network/timing assumption is needed.
- **Impact:** validators/tools built on backend transcript schema reject valid current encoder output; contract fixtures can remain green without cross-validating parity cases.
- **Coverage:** [test_stream_terminal_parity.py:59–65,100–130](backend/tests/test_stream_terminal_parity.py#L59) checks encoded/stored whitespace equality without SSETranscript validation. [test_sse_schema.py:145–158](backend/tests/test_sse_schema.py#L145) tests meaningful-delta cases only. Frontend validator already permits whitespace-only FAILED ([frontend/lib/api/chat.ts:183–205](frontend/lib/api/chat.ts#L183)). Python tests NOT_EXECUTED.
- **Recommended action:** align schema with chosen meaningful-content rule; feed actual parity-case frames into SSETranscript; test ASCII/Unicode whitespace, BOM and normal meaningful output. Do not change persistence back to delta-presence classification to satisfy the older schema.

### C02 — Failed PENDING→STREAMING transition leaves a nonterminal durable turn after releasing ownership

- **Classification/severity:** **CONFIRMED_DEFECT — Medium**; deterministic conditional fault path, not an observed database outage.
- **Location:** `ConversationService.begin_streaming_turn`, [conversation_service.py:214–230](backend/app/conversation_service.py#L214); repository transition [conversation_repository.py:186–202](backend/app/conversation_repository.py#L186); handler [api/chat.py:489–501](backend/app/api/chat.py#L489).
- **Expected invariant:** when setup has created a durable turn but abandons generation, it must terminalize that owned turn or leave explicit recoverable ownership; it must not silently leave an abandoned active-status placeholder.
- **Actual behavior:** pair insertion succeeds; mark_assistant_streaming raises; except releases guard and rethrows, with no terminalization/removal of the already inserted pair. Handler returns pre-header 503/409. No StreamingTurn reaches the encoder, so its cancellation finalizer cannot recover the placeholder.
- **Failure reasoning:** insert_many acknowledged; transition fails before write (e.g. repository wraps a write error); release succeeds. USER remains COMPLETED, assistant PENDING, session guard=null. A later request can proceed while old placeholder remains indefinitely. If transition write committed before error, the analogous stranded state can be STREAMING; that ambiguity is separately C06.
- **Impact:** abandoned message appears active on raw history and is excluded from subsequent RAG history; user cannot learn durable IDs from the pre-header error; cleanup is absent in this path. This is an incomplete **pair**, not proof of a physically orphaned single message.
- **Coverage:** [test_chat_persistence.py:155–174](backend/tests/test_chat_persistence.py#L155) covers successful begin/finalize; FakeMessageRepository.mark_assistant_streaming never raises ([test_chat_persistence.py:39–41](backend/tests/test_chat_persistence.py#L40)). No setup-transition failure regression found. NOT_EXECUTED.
- **Recommended action:** add a production-service fault-injection test at mark_assistant_streaming and define an owned terminal/compensation result before release. Preserve linkage and safe error metadata; do not delete another request's records.

### C03 — Guard-release exception can overwrite the outcome of an acknowledged terminal write

- **Classification/severity:** **CONFIRMED_DEFECT — High**; source-proven conditional error semantics, no runtime fault injected.
- **Location:** `finalize_streaming_turn`, [conversation_service.py:274–278](backend/app/conversation_service.py#L274); `answer_with_persistence`, [conversation_service.py:175–186](backend/app/conversation_service.py#L175); release [conversation_repository.py:149–166](backend/app/conversation_repository.py#L149); encoder [api/chat.py:214–250](backend/app/api/chat.py#L214).
- **Expected invariant:** distinguish terminal message commit from guard cleanup result; do not describe an acknowledged COMPLETED message as a persisted PARTIAL failure. Durable IDs/outcome must remain recoverable when cleanup fails.
- **Actual behavior:** finalization returns terminal replacement from try, then release runs in finally. A release exception suppresses that successful return. Encoder treats any exception as STREAM_PERSISTENCE_ERROR, sets finalized=true and emits PARTIAL for meaningful content. JSON similarly loses its successful return to the finally exception and maps it to 503/409 detail, without the successful durable IDs.
- **Deterministic fault reasoning:** provider finishes "answer" → terminal replacement acknowledged COMPLETED/error_code=null → release update raises ConversationRepositoryError → SSE emits error(PARTIAL,STREAM_PERSISTENCE_ERROR). History says COMPLETED, not PARTIAL. If release was not committed the guard also remains held. This does not require a race or uncertain terminal write.
- **Impact:** wire/history status and error code diverge; client verification warns; retry may be blocked or, after recovery, duplicate an already completed logical answer. Guard release failure must still be surfaced, but it is not evidence the message commit failed.
- **Coverage:** [test_chat_stream.py:275–321](backend/tests/test_chat_stream.py#L275) injects failure of the entire finalization service, not success of replace followed by release failure. FakeMessageRepository release always succeeds ([test_chat_persistence.py:33–35](backend/tests/test_chat_persistence.py#L33)). Existing parity tests cover provider outcomes, not split finalization/release faults. NOT_EXECUTED.
- **Recommended action:** model terminal persistence and release as separate outcomes, retain durable IDs/status, and test both replace-succeeds/release-fails and replace-fails/release-succeeds. Do not silently claim guard cleanup success or rewrite an already committed terminal record without an explicit policy.

### C04 — Stale guard and abandoned-turn recovery is not implemented

- **Classification/severity:** **CONFIRMED_GAP — High**; recovery absence is source-confirmed, hard-crash scenario NOT_VERIFIED.
- **Location:** [conversation_models.py:66–68](backend/app/conversation_models.py#L66), [conversation_repository.py:117–166,222–238](backend/app/conversation_repository.py#L117), [main.py:20–38](backend/app/main.py#L20); README explicitly acknowledges it at [README.md:620–622](README.md#L620).
- **Expected invariant:** an interrupted generation needs a defined path to safely recover session availability and terminalize/identify abandoned messages.
- **Actual behavior:** timestamp is stored but neither acquisition nor deletion accepts expired ownership; no lease/heartbeat/stale-guard reconciler is invoked by inspected startup/service. finally release handles normal unwinding, not process death. Title update remains available, but new generation and normal deletion are blocked by active_generation_id.
- **Scenario:** crash after guard commit or fail release with no later retry; restart retains guard and potentially PENDING/STREAMING assistant. Future acquisition/delete conflicts until an external operator changes state. No claim of automatic expiration is supported.
- **Impact:** session can remain blocked indefinitely; history may show an active-status message with no worker. This is separate from document ingestion recovery in 0B-01.
- **Coverage:** [test_conversation_concurrency.py:95–111](backend/tests/test_conversation_concurrency.py#L89) raises CancelledError and executes service cleanup; that is not hard process death. Historical clean-restart script [verify_phase2.py:189–191](backend/scripts/verify_phase2.py#L189) does not prove mid-generation recovery. NOT_EXECUTED.
- **Recommended action:** define operator and/or lease-based recovery with ownership fencing and terminal-state policy; validate old/live owner distinction offline before any automated cleanup. Do not clear all nonnull guards indiscriminately.

### C05 — SSE preparation can be stale or consume work before concurrency rejection

- **Classification/severity:** **DESIGN_RISK — Medium**; explicit interleavings remain NOT_VERIFIED.
- **Location:** [api/chat.py:453–470](backend/app/api/chat.py#L453) vs JSON [conversation_service.py:107–132](backend/app/conversation_service.py#L107); shared builder [rag/pipeline.py:75–98,114–124](backend/app/rag/pipeline.py#L75).
- **Expected invariant:** clarify whether a newly acquired turn must use history current at acquisition and whether rejected requests may execute preparation/provider rewriting.
- **Actual behavior:** SSE loads history, rewrites/retrieves, then attempts guard. JSON acquires first and prepares inside generate callback. Guard serializes durable generation, not all request preparation.
- **Scenario:** B prepares H; A completes a turn; B acquires after A release and uses stale H. Or B prepares while A remains active and then receives 409. Safe snapshot revalidation is absent in this handler.
- **Impact:** possible missed recent referent/history or avoidable preparation cost/latency on rejected requests; not cross-session contamination or proof of concurrent stored turns.
- **Coverage:** [test_conversation_concurrency.py:44–93](backend/tests/test_conversation_concurrency.py#L44) tests service overlap with a lock fake; [test_multi_session_isolation.py:247–273](backend/tests/test_multi_session_isolation.py#L247) tests distinct histories via mocks. Neither demonstrates same-session SSE prepare/acquire ordering. NOT_EXECUTED.
- **Recommended action:** decide acquisition/snapshot contract and add step-controlled same-session endpoint tests, including A finishes between B preparation and acquisition. Verify cancellation and deleted-session preparation without invoking providers.

### C06 — Multi-record writes, compensation and manual replay do not provide exactly-once turns

- **Classification/severity:** **DESIGN_RISK — High**; ambiguous write/rollback scenarios NOT_VERIFIED.
- **Location:** [conversation_repository.py:117–184,222–258](backend/app/conversation_repository.py#L117), [conversation_service.py:107–129](backend/app/conversation_service.py#L107), [conversation_indexes.py:28–46](backend/app/conversation_indexes.py#L28).
- **Expected invariant:** partial writes/uncertain outcomes must be recoverable without mistaking sort uniqueness for whole-turn atomicity or logical-request deduplication.
- **Actual behavior:** guard reservation, insert_many, terminal write and release are separate. Pair cleanup is best-effort; reserved sequences are not rolled back. Session tombstone and message deletion are separate; repeat DELETE retries cleanup. Request UUIDs are server-generated anew per submission.
- **Scenarios:** first message inserts, second fails, compensating delete also fails → orphan user; pair commits but acknowledgment fails → compensation may remove it or fail leaving it; tombstone succeeds, message delete fails → retained hidden messages; completed response is lost, user manually resubmits after release → a new logical pair. These are conditional infrastructure/replay scenarios, not observed corruption.
- **Impact:** possible missing/orphan/duplicate logical turns, sequence gaps or hidden retained records. Completed-turn loader filters orphan pairs from prompts but does not repair records.
- **Coverage:** [test_chat_persistence.py:23–45](backend/tests/test_chat_persistence.py#L23) uses assignment-based fake pair insertion; [test_session_actions.py:68–77](backend/tests/test_session_actions.py#L68) covers repeat delete, not cleanup failure/ambiguous commit. Production repository multi-write compensation is not reproduced by these mocks. NOT_EXECUTED.
- **Recommended action:** add commit-then-raise, partial insert and failed-compensation tests around actual repository semantics; document uncertainty and intentional sequence gaps. Decide whether a client idempotency/reconciliation contract is needed before implementing one; it is not silently assumed required today.

### C07 — Cleanup ownership is incomplete before iterator entry and on unexpected encoder errors

- **Classification/severity:** **DESIGN_RISK — High**; actual ASGI/send/cancellation interleavings NOT_VERIFIED.
- **Location:** [api/chat.py:464–516,128–168,256–312](backend/app/api/chat.py#L464); local [starlette/responses.py:250–283](.venv/Lib/site-packages/starlette/responses.py#L250).
- **Expected invariant:** every durable active turn has a cleanup owner even if response delivery cannot start or an internal prefix encoder error occurs.
- **Actual behavior:** turn is created before StreamingResponse body is entered; cancellation cleanup exists inside async generator. Local response code sends headers before iterating. The wrapper's generic Exception branch records metric then raises without finalization; source DTO conversion/event prefix occur outside provider try. Header failures cannot be assumed to execute an unstarted generator's handler.
- **Scenarios:** cancel/send failure after begin_streaming_turn but before first anext; invalid internal prepared-source DTO raises after response start; unexpected encoder exception outside provider loop truncates a connected response with no terminal and can leave guard/messages active. External corruption or injected fault is a premise, not proven normal input behavior.
- **Impact:** possible unfinished persistent turn, missing terminal SSE and stale guard; browser abort during preparation also need not cancel underlying worker/provider work. Direct generator cleanup is not proof all these boundaries are covered.
- **Coverage:** [test_chat_stream.py:323–390,392–441](backend/tests/test_chat_stream.py#L323) covers cancellation while awaiting provider and close after start, **after iterator entry**. No failing-ASGI-send-before-entry or source-prefix validation/finalizer test found. NOT_EXECUTED.
- **Recommended action:** test handler-to-response ownership transfer with local ASGI send/receive doubles, direct cancellation at each await boundary and encoder-prefix faults. Define cleanup outside generator entry as necessary; do not rely on garbage collection as a correctness contract.

### C08 — Stream timeout does not bound closing, persistence or the full request lifecycle

- **Classification/severity:** **DESIGN_RISK — Medium**; hang/timeout timing scenarios NOT_VERIFIED.
- **Location:** [api/chat.py:169–223,278–297,453–470](backend/app/api/chat.py#L169), [rag/pipeline.py:228–239](backend/app/rag/pipeline.py#L228); client wait [frontend/lib/chat/controller.ts:99–100,235–239](frontend/lib/chat/controller.ts#L99).
- **Expected invariant:** state clearly which phases have deadlines; connected paths must not be assumed to reach terminal within STREAM_TIMEOUT_SECONDS if other awaits are unbounded.
- **Actual behavior:** provider deadline starts after start/metadata; asyncio.wait_for may await cancellation completion; shielded aclose has no separate deadline; preparation and terminal persistence are outside that deadline. Cancellation finalizer also awaits shielded threadpool work without its own overall deadline. Configured Mongo/SDK timeouts may bound individual operations, not prove a whole-request limit.
- **Scenario:** provider ignores/delays cancellation or aclose waits; persistence/release blocks after final delta; client timer aborts while server owns cleanup. No terminal by expected application deadline; guard release delayed. No such stall was executed.
- **Impact:** extended session occupancy, incomplete stream and recovery uncertainty.
- **Coverage:** [test_chat_stream.py:251–273](backend/tests/test_chat_stream.py#L251) uses a cooperative sleeping generator whose finally completes promptly. No noncooperative close or delayed terminal/release test found. NOT_EXECUTED.
- **Recommended action:** specify phase deadlines and ownership on timeout; add cooperative/noncooperative close and blocked persistence tests. Keep any cleanup retry policy ownership-safe; do not terminate arbitrary worker threads.

### C09 — Stable offset history/list ordering does not establish a read snapshot

- **Classification/severity:** **DESIGN_RISK — Medium**; concurrent pagination scenarios NOT_VERIFIED.
- **Location:** [conversation_repository.py:58–72,100–115](backend/app/conversation_repository.py#L58), [history.py:88–103](backend/app/history.py#L88), [frontend/lib/sessions/history.ts:39–67](frontend/lib/sessions/history.ts#L39).
- **Expected invariant:** document whether history/list is a snapshot or a moving view; retrieval and client restoration must handle concurrent totals/state changes safely.
- **Actual behavior:** count and find/page calls are separate; offsets carry no high-water mark. Backend history loader has no duplicate-ID/sequence validation like frontend; it groups after all pages. Session list is sorted by mutable updated_at. Client rejects duplicates/inconsistent totals but cannot force a consistent server snapshot.
- **Interleavings:** count reads N, pair inserts before find → page can contain more rows than the old total; newer completed records/status updates appear during later pages; session A's updated_at moves between list pages → duplicate/missing list entry. In-flight history can pass session check before tombstone and return stale/empty data after delete. JSON guard reduces same-session write overlap while its RAG history loads; public reads and SSE preguard preparation are not guarded.
- **Impact:** possible stale/inconsistent restoration, client warnings or omitted prompt turn on a moving dataset; no evidence of arbitrary order changes on a quiescent dataset.
- **Coverage:** [test_history.py:78–95,136–159](backend/tests/test_history.py#L78) checks fixed pagination/filtering; Node `sessions.test.mjs` checks duplicate/mixed/progress state but uses controlled fixed pages. Executed 30 Node tests do not reproduce a concurrent Mongo snapshot race.
- **Recommended action:** define consistency expectations, test count/find mutation and page-boundary state changes offline; consider high-watermark/cursor semantics if required. Avoid declaring append-only message pagination identical to mutable session-list pagination.

### C10 — README overstates atomic pair creation and retains the older delta-based terminal rule

- **Classification/severity:** **DOCUMENTATION_MISMATCH — Low**.
- **Location:** [README.md:278–283,292–300](README.md#L278); production [conversation_repository.py:168–184](backend/app/conversation_repository.py#L168), [api/chat.py:209–244](backend/app/api/chat.py#L209); related historical resolution [docs/bugs/stream-terminal-parity.md](docs/bugs/stream-terminal-parity.md).
- **Expected invariant:** operator/client documentation reflects meaningful-content classification and distinguishes atomic guard acquisition from compensated multi-record message writes.
- **Actual behavior:** README says FAILED when no delta, PARTIAL after output, without whitespace qualification; it calls creation of user and PENDING→STREAMING atomically. Actual pair is ordered insert_many plus best-effort rollback, followed by a separate replace; runtime can emit FAILED after whitespace deltas.
- **Reasoning:** source branch and repository operation sequence directly contradict broad documentation wording. The historical bug note records the encoder/frontend correction but is not a fresh test pass.
- **Impact:** consumers can implement the old validator rule, or assume all-or-nothing pair creation under failures. The existing schema inconsistency is C01, not a second independent runtime failure.
- **Coverage:** schema tests still describe delta-presence semantics ([test_sse_schema.py:145–158](backend/tests/test_sse_schema.py#L145)); runtime parity tests describe the corrected behavior. Neither documentation nor Python suites were executed/edited.
- **Recommended action:** after approval align README/schema contract language with implementation and explicitly qualify exactly-one-terminal and compensation boundaries. Leave historical evidence labeled historical.

## 9. Test Coverage & Verification Gaps

### Actual execution ledger

Command, executed from `frontend/`:

```powershell
node --test tests/chat-controller.test.mjs tests/multi-turn.test.mjs tests/sessions.test.mjs
```

Result: exit 0; **30 tests, 30 PASS, 0 FAIL, 0 cancelled, 0 skipped, 0 todo**; runner duration approximately 1.385 seconds. This is one selected run, not the whole frontend suite. Existing modules read/transpile TypeScript in memory, inject service/API/fetch mocks and use no application server/cloud/provider ([chat-controller.test.mjs:1–31](frontend/tests/chat-controller.test.mjs#L1), [multi-turn.test.mjs:1–26,43–103](frontend/tests/multi-turn.test.mjs#L43), [sessions.test.mjs:1–25,64–94](frontend/tests/sessions.test.mjs#L64)). These tests cover only the conversation restoration/controller scope relevant to this round; browser rendering is not certified.

| Files / methods inspected | Coverage supported by source; execution status |
| --- | --- |
| `backend/tests/test_sessions_api.py::test_create_list_get_update_history_and_delete` (:105), `test_missing_and_deleted_sessions_have_distinct_statuses` (:140) | CRUD/error response fixtures. **NOT_EXECUTED**; fake service is not live repository evidence. |
| `backend/tests/test_session_actions.py::test_generation_race_is_stopped_by_atomic_delete_predicate` (:60), `test_repeat_delete_retains_tombstone_and_retries_message_cleanup` (:68) | Production delete/rename repository through fake collections; useful predicate coverage, no real Mongo concurrency. **NOT_EXECUTED**. |
| `backend/tests/test_chat_persistence.py::test_user_and_pending_assistant_exist_before_successful_generation` (:58), `test_generation_failure_is_persisted_without_raw_error` (:105), `test_cancellation_is_failed_and_releases_guard` (:139), `test_streaming_turn_records_active_and_truthful_terminal_states` (:155) | Service state/IDs/citations/usage/failure through FakeMessageRepository; no failed mark/release/partial insert. **NOT_EXECUTED**. |
| `backend/tests/test_conversation_concurrency.py::test_two_simultaneous_requests_allow_only_one_generation` (:44), `test_cancelled_generation_releases_guard` (:89) | Lock-backed AtomicGuardRepository, not production Mongo atomic update or ASGI cancellation. **NOT_EXECUTED**. |
| `backend/tests/test_chat_stream.py::test_stateless_stream_uses_typed_sse_order_and_headers` (:58), `test_stream_provider_failure_emits_partial_error_and_persists_it` (:192), `test_stream_timeout_cancels_provider_and_emits_terminal_error` (:251), `test_persistence_failure_after_headers_is_terminal_sse_error` (:275), cancellation/prefix-close tests (:323,393) | Patched provider/preparation/service and direct generator cancellation; selected normal transcript is checked. No release-after-commit fault, never-entered body or failed send. **NOT_EXECUTED**. |
| `backend/tests/test_stream_terminal_parity.py::test_whitespace_only_error_terminal_matches_persisted_status` (:59), `test_unicode_whitespace_error_preserves_exact_content_and_usage` (:62), `test_whitespace_disconnect_persists_failed_and_releases_guard` (:67), `test_whitespace_only_normal_finish_is_failed_empty_with_exact_content` (:100) | Real encoder/service with fake repository, no cross-validation against backend SSETranscript. **NOT_EXECUTED**. |
| `backend/tests/test_sse_schema.py::test_terminal_status_must_match_delta_presence` (:145), `test_order_sequence_and_single_terminal_are_enforced` (:160), `test_citation_must_match_metadata_source_and_be_unique` (:173) | Whole-transcript schema guarantees; C01 gap between these and runtime. **NOT_EXECUTED**. |
| `backend/tests/test_chat_response_schema.py::test_persistent_response_requires_session_and_both_message_ids` (:68), `test_usage_is_nullable_but_validated_when_present` (:111); `backend/tests/test_streaming_pipeline.py::test_astream_preserves_usage_on_textless_final_chunk` (:73) | DTO/usage normalization behavior. **NOT_EXECUTED**. |
| `backend/tests/test_history.py::test_default_drops_whole_partial_failed_and_active_turns` (:95), `test_orphans_cross_session_and_non_adjacent_pairs_are_never_returned` (:136); `backend/tests/test_multi_session_isolation.py::test_same_followup_distinct_histories_overlap_without_contamination` (:247) | Whole-turn/filter/isolation through mocked storage/provider components. **NOT_EXECUTED**. |
| `frontend/tests/chat-controller.test.mjs` | **Executed: 8 PASS.** Session creation, duplicate-submit suppression, partial/error, abort/dispose, disconnect, terminal preservation and session API DTO wiring. |
| `frontend/tests/multi-turn.test.mjs` | **Executed: 9 PASS.** Three-turn scripted mock, mismatch/failing-history warning cases, session switch/late callbacks, repeated request IDs, persistence checks, citation reconciliation and abort during history read. "Mock E2E" test title is not browser/live backend E2E. |
| `frontend/tests/sessions.test.mjs` | **Executed: 13 PASS.** REST mock routes/DTOs, lookup states, fixed history pagination, isolation/mixed-page rejection, refresh replacement and source-free history mapping. |

Not run: backend unittest discovery; schema/contract export; all other Node tests; Playwright; live/session-restart/concurrency/cloud smoke scripts. `frontend/tests/sse-parser.test.mjs:59–84` launches Python for backend-generated frames; `frontend/tests/chat-stream-client.test.mjs:99–104` launches Python for whitespace reference, so they were not included merely because they are Node entrypoints. No historical README/test count was adopted as a current pass.

### Missing targeted deterministic fault-injection coverage

Prioritize: current whitespace encoder frames through SSETranscript (C01); mark_streaming failure after pair acknowledgment (C02); successful terminal replace followed by failed owner release (C03); stale-owner/crash recovery policy (C04); blocked SSE preparation before acquire (C05); partial insert/commit-then-raise/failed compensation/tombstone-cleanup error (C06); ASGI headers/body send fault and cancellation at ownership handoff/prefix validation (C07); noncooperative provider close and blocked finalization (C08); count/find and between-page mutation (C09). These are proposed tests, **not executed reproductions**.

## 10. Recommended Next Actions

1. Request separate implementation authorization for C01–C03 and focused regression tests. Preserve existing whitespace/body equality semantics; distinguish message commit from guard release; make stream-setup compensation explicit.
2. Define session recovery policy for C04 with safe ownership/fencing. Include operator-visible durable IDs and recovery outcomes; ordinary task cancellation tests do not substitute for crash tests.
3. Validate C05–C09 through offline step-controlled repository/ASGI/provider doubles before any live experiment. Favor production repository/service execution over fakes that implement stronger atomicity than the real code.
4. After owner approval, reconcile README/schema contract wording (C10) and clearly state intentional JSON/SSE differences: guard/preparation order, partial responses, realtime citation absence, failure envelope stages and post-terminal history verification.
5. Keep environment repair, cloud/provider smoke and browser/UI audit separate. No backend fixes, migrations, README changes or Round 0B-03 work are authorized or performed by this report.

## 11. Final Verdict for Round 0B-02

**Read-only conversation audit completed.** Normal single-session exclusion, stable sequence allocation, meaningful-content terminal persistence and client mock restoration have substantial source/test support. Backend runtime correctness under faults remains **NOT_VERIFIED**; three source-proven conditional defects and one recovery gap prevent claiming comprehensive lifecycle/terminal durability guarantees. Five timing/infrastructure risks are explicitly unverified, not reported as observed races.

The only runtime evidence obtained is **30/30 selected Node tests passing**. No Python/backend test pass, actual Mongo transaction/guard behavior, ASGI disconnect experiment, real SSE network/proxy behavior, crash recovery or provider quality was verified. Local dependency source may differ from deployment; actual database indexes/data were not inspected. Authentication and frontend UI remain outside scope. No final project maturity level is assigned.

File integrity: baseline contained only untracked Phase 0A/0B-01 reports; 298 tracked files and both reference reports were fingerprinted before this report and after the selected test run/report creation. All comparisons matched:

| Read-only SHA-256 check | Unchanged result |
| --- | --- |
| All 298 tracked files, sorted path + NUL + bytes + NUL | `cea8f0bb1b426d5ec6157a1a136600f03df533c923ff6a46e569284617a9671d` |
| CODEBASE-INVENTORY.md | `383f4a02dfdb5d5d3709798579a8190b5f3ea02a1d243a34fc9b97d6ab2469dc` |
| RAG-CORE-AUDIT-0B01.md | `26dc8c93e85bed5e8a8cfc07cecacdeb84c2a680cffb8e206deef739829b18da` |

Report validation: 11 required sections and C01–C10 present; all 137 linked source/report references resolve to existing files and valid line bounds; referenced inline test symbols were checked for presence. Link checks establish location validity, not execution of the cited behavior. `git diff --check` and `git diff --name-only` report no tracked modifications. Worktree status contains the two pre-existing untracked reports and this new report only. No application/configuration/dependency/README changes belong to this round.

Work stops at this report. Round 0B-03, fixes and documentation updates require owner approval.
