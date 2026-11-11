# RAG Core Audit — Round 0B-01

Date: 2026-10-27 (Asia/Bangkok). Mode: read-only source audit. Only this report was created. Phase 0A inventory was consulted but rechecked against current source. No application, dependency, configuration, database or README changes; no application startup, cloud requests or Groq/Gemini calls.

## 1. Executive Summary

The main ingestion path delays publication until vector upsert and count verification, and retrieval constrains searches to MongoDB-selected active versions. History, rewriting and generation share preparation across JSON/SSE. These are source-confirmed properties, **not runtime certification** ([ingestion.py:189–278](backend/app/ingestion.py#L189), [pipeline.py:64–155](backend/app/rag/pipeline.py#L64), [retriever.py:38–68](backend/app/rag/retriever.py#L38)).

Two correctness defects are demonstrable by source reasoning: text encoding fallback catches the wrong exception for the locally installed LangChain implementation, and reconciliation can repeatedly select ineligible old jobs while starving eligible later jobs. A separate recovery gap excludes interrupted PENDING/zero-plan jobs. None was executed as a reproduction; exact premises and source traces are in F01–F03.

| Category | Assessment | Finding references |
| --- | --- | --- |
| Confirmed correctness issues | Encoding autodetection is unreachable after UTF-8 decode failure with local langchain-community 0.4.2; reconciliation selection can make no progress; interrupted early-stage jobs have no recovery path in the inspected reconciler. | F01, F02: CONFIRMED_DEFECT; F03: CONFIRMED_GAP |
| Unverified high-risk scenarios | Same-dimension embedding model drift, overlap between reconciliation/retry/live ingestion, and ambiguous distributed write/compensation outcomes. | F04–F06: DESIGN_RISK; no observed race or production corruption claimed |
| Other unverified correctness/availability risks | Unbounded non-XLSX processing, incomplete model-facing budget enforcement, prompt-injection/semantic-grounding boundary. | F07–F09: DESIGN_RISK |
| Documentation correction | Phase 0A incorrectly described relative storage configuration as CWD-dependent. Production factory anchors it to PROJECT_ROOT. | F10: DOCUMENTATION_MISMATCH |
| Deferred optimization opportunities | Bounded recent-history reads, embedding/upsert batching, avoiding duplicate XLSX parsing, retrieval relevance calibration. | Section 10; not prerequisites inferred from feature absence |

Recommendation: authorize narrowly targeted regression work for F01–F03 before performance optimization. Verify F04–F06 with offline adapter/failure-injection scenarios before treating distributed recovery as reliable. No full RAG replacement is justified by this audit, and no final project maturity level is assigned.

## 2. Audit Scope and Methods

Inspected the actual document API/service/repository/models/indexes, local storage, ingestion/reconciliation, parsers/splitter, vector models/Qdrant adapter, active-version retriever, history loading, rewriting, context budgeting, prompt/preparation/generation, attachment resolution, and relevant test bodies/declarations. Primary map: [CODEBASE-INVENTORY.md](CODEBASE-INVENTORY.md). This report does not repeat its full inventory.

Methods: read source with line numbers; trace state/write ordering; inspect error branches; compare production adapters with test fakes; search test coverage; reason about explicit state examples and possible interleavings. Existing dependency source was read without importing it to resolve TextLoader exception behavior: [.venv/Lib/site-packages/langchain_community/document_loaders/text.py:38–58](.venv/Lib/site-packages/langchain_community/document_loaders/text.py#L38), [.venv/Lib/site-packages/langchain_core/document_loaders/base.py:37–44](.venv/Lib/site-packages/langchain_core/document_loaders/base.py#L37). Local distribution metadata reports 0.4.2 (`.venv/Lib/site-packages/langchain_community-0.4.2.dist-info/METADATA:3`); that is local dependency evidence, not a pinned deployment guarantee.

Evidence classifications used:

- **CONFIRMED_DEFECT:** an explicit invariant is contradicted by source or deterministic reasoning; no execution is implied.
- **CONFIRMED_GAP:** recovery behavior required by this audit is absent in the inspected implementation.
- **DESIGN_RISK:** a plausible failure with preconditions requiring verification; never presented as an observed bug.
- **DOCUMENTATION_MISMATCH:** a documentation statement contradicts current implementation.
- **NOT_VERIFIED:** insufficient evidence, including runtime behavior and model quality.

Severity: High = potentially silent incorrect retrieval, unsafe state changes or sustained recovery failure; Medium = bounded functionality/availability/correctness impact; Low = documentation/operator confusion. Severity is consequence-based, not a measured likelihood score.

**Executed tests: none. All existing test suites: NOT_EXECUTED.** The Python environment was already broken in Phase 0A and was neither recreated nor modified. This round read `.venv/pyvenv.cfg:1–3`; an attempted read-only existence probe of its external interpreter path was denied by filesystem access controls. That probe is not a new proof of interpreter absence and not a failed application test. No alternate environment was provisioned. Tests using temporary filesystem writes also were not represented as strictly side-effect-free executions.

Excluded: authentication/RBAC, unrelated frontend UX/styling, streaming transport/persistence deep audit, live model-quality evaluation, cloud data inspection and operational experiments. No external web lookup was needed; findings concern this checkout and local dependency source.

## 3. Document Lifecycle Assessment

### Source-confirmed state handling

| Operation | Actual state/write sequence | Assessment |
| --- | --- | --- |
| New upload | New DocumentRecord UPLOADED with no active pointer; version UPLOADED and job PENDING; raw file published before metadata inserts. | Defaults in [document_models.py:31–44,54–69,92–111,131–147](backend/app/document_models.py#L31); orchestration [ingestion.py:96–152](backend/app/ingestion.py#L96). No initial premature publication. |
| Processing | Job PENDING → PROCESSING; version → PROCESSING; document becomes PROCESSING only when active pointer is absent and not deleted. | [document_repository.py:199–229](backend/app/document_repository.py#L199). Existing published version remains available during candidate processing. These are multiple updates, not an atomic cross-record transition. |
| Success | Save plan → candidate cleanup/upsert → exact count → version INDEXED → conditional document pointer/status update → job COMPLETED. | [ingestion.py:207–257](backend/app/ingestion.py#L207), [document_repository.py:256–318](backend/app/document_repository.py#L256). INDEXED version and active version are intentionally different concepts. |
| Update | Same document identity, new version UUID and next version number; old active remains until candidate activates. | [document_service.py:84–87](backend/app/document_service.py#L84), [ingestion.py:111–149](backend/app/ingestion.py#L111). Version numbers use read-max-plus-one, backed by a unique compound index, so collision can reject an update rather than corrupt version numbering ([document_repository.py:138–179](backend/app/document_repository.py#L138), [document_indexes.py:33–39](backend/app/document_indexes.py#L33)). |
| Re-index | Read raw bytes of the active version and call update to create a new immutable source version. | [document_service.py:89–102](backend/app/document_service.py#L89). Not an in-place edit to published raw/vector data. |
| Failure before activation | Delete candidate-version vectors best-effort; mark version/job FAILED; only documents with no active version become FAILED. | [ingestion.py:241–252,280–295](backend/app/ingestion.py#L241), [document_repository.py:320–349](backend/app/document_repository.py#L320). Active old version survives ordinary candidate failure. |
| Delete | Unpublish first: DELETED, active pointer null, cleanup_pending true; count/delete/recount document points; clear cleanup flag after success; retain raw/audit records. | [document_repository.py:382–418](backend/app/document_repository.py#L382), [document_service.py:104–128](backend/app/document_service.py#L104). Repeat DELETE retries cleanup; API returns 202 while pending ([api/documents.py:241–264](backend/app/api/documents.py#L241)). |
| Retry | Only FAILED, nonactive versions are retryable; create a new job and rerun processing using same immutable raw version and deterministic point IDs. | [ingestion.py:154–168](backend/app/ingestion.py#L154), [document_repository.py:181–197](backend/app/document_repository.py#L181). Job attempt allocation has no per-version ownership/lease in this path; overlapping retries remain F05. |
| Reconciliation | Processing-job selector with positive chunk plan → count candidate vectors → activate if complete; otherwise clean/fail nonactive candidate, skip an active mismatch. | [document_repository.py:417–439](backend/app/document_repository.py#L417), [ingestion.py:297–337](backend/app/ingestion.py#L297). F02/F03 constrain recovery; skip on active mismatch avoids destructive cleanup but does not repair it. |

### Concurrency and interruption boundaries

`complete_and_activate` rereads the current pointer, rejects a deleted document, compares active version numbers, and uses a compare-and-set filter including the pointer and non-DELETED status. An older finishing candidate cannot normally replace an already newer active version; a delete that wins before this conditional update cannot be undone by that update ([document_repository.py:270–304](backend/app/document_repository.py#L270)). These protections do **not** make parsing, vector cleanup/upsert, activation and job completion one transaction.

After successful upsert/count, finalization failure intentionally preserves vectors rather than deleting a possibly active version. A deleted document is handled separately via candidate cleanup/FAILED state ([ingestion.py:254–271](backend/app/ingestion.py#L254)). Runtime races, process crashes and network-ambiguous commits were not exercised. F05 and F06 describe remaining risks without asserting they occurred.

Repeated upload HTTP requests create new document identities; only internal retry has same-version idempotency. No upload idempotency-key contract is present in the inspected endpoint, so independent uploads are not reported as a duplicate-creation defect ([api/documents.py:156–167](backend/app/api/documents.py#L156), [ingestion.py:96–110](backend/app/ingestion.py#L96)).

## 4. Ingestion Pipeline Assessment

Execution: multipart API validation → raw immutable local save → Mongo lifecycle records → temporary materialization → format parser → character splitter → embed_documents → plan metadata → candidate version delete/upsert → exact count → activation. All stages are traced in [api/documents.py:125–167](backend/app/api/documents.py#L125), [ingestion.py:96–278](backend/app/ingestion.py#L96).

| Concern | Source-confirmed behavior | Qualification |
| --- | --- | --- |
| TXT/MD/Markdown | TextLoader UTF-8 first; intended autodetect fallback; Markdown treated as plain text. | [rag/loader.py:13,41–65](backend/app/rag/loader.py#L41). F01 breaks fallback with local dependency; UTF-8 success path is not implicated. |
| PDF | PyPDFLoader(mode=page), then same splitter. | [rag/loader.py:44–46](backend/app/rag/loader.py#L44). Existing PDF fixture asserts zero-based page metadata ([tests/test_message_attachments_excel.py:143–159](backend/tests/test_message_attachments_excel.py#L143)); OCR/encrypted-PDF support is not promised or verified. |
| XLSX | 10 MiB upload limit, allowed MIME set, ZIP entry/expanded-byte limits, workbook signatures, macro rejection, openpyxl read_only/data_only=false/keep_links=false, sheet/row/column/cell/value limits. | [excel.py:11–23,43–94](backend/app/excel.py#L43). Formulas are literal text; not computed. Workbook parsed at API validation and again by loader; resource efficiency is deferred. |
| XLSX rows | First nonempty row supplies columns; each later row becomes a Document with sheet_name/row_index; header-only sheet uses a fallback row. Post-serialization limits cap row/total text. | [excel.py:79–85,97–112](backend/app/excel.py#L97). Generic splitter may split one row further, preserving row metadata; no row-atomic chunk promise is inferred. |
| File validation | Basename/extension checks at API and service; empty uploaded bytes rejected. | [api/documents.py:33–46,125–135](backend/app/api/documents.py#L125), [ingestion.py:86–108](backend/app/ingestion.py#L86). No non-XLSX read limit here: F07. Long filename model validation/HTTP mapping was not comprehensively exercised. |
| Chunking | RecursiveCharacterTextSplitter with configured character size/overlap and size>overlap guard. | [rag/splitter.py:14–45](backend/app/rag/splitter.py#L14). Character chunks are not model-token chunks. No chunks causes empty_chunks before embedding; API currently maps that code to generic 500, whereas parse_failed maps to 400 ([ingestion.py:185–187](backend/app/ingestion.py#L185), [api/documents.py:102–119](backend/app/api/documents.py#L102)). Client-error taxonomy should be clarified; no required HTTP code was inferred. |
| Vector integrity | Nonempty finite vectors, consistent dimensions per write, nonblank chunk text, nonnegative chunk/page index; UUID-normalized IDs; UUID5(version_id:chunk_index). | [vector_index.py:23–76](backend/app/vector_index.py#L23), [qdrant_ingestion.py:65–74](backend/app/qdrant_ingestion.py#L65). Blank individual chunks/invalid vectors fail ingestion and attempt cleanup. |
| Metadata provenance | Vector payload takes document/version IDs and original file name from server records, not loader temporary path; page/sheet/row from parser metadata; returned chunk identity uses point.id. | [ingestion.py:217–236](backend/app/ingestion.py#L217), [vector_index.py:67–76](backend/app/vector_index.py#L67), [qdrant_ingestion.py:180–198](backend/app/qdrant_ingestion.py#L180). Valid UUID shape is not independent semantic verification of every payload field. |
| Collection compatibility | Create unnamed cosine collection if absent; reject dimension/distance mismatch; create keyword payload indexes if absent; upsert wait=true. | [qdrant_ingestion.py:87–120,144–154](backend/app/qdrant_ingestion.py#L87). No embedding-model identity guard: F04. |
| Verification/recovery | Count exact version points equals chunk count before publication; retain verified vectors on uncertain finalization; internal retry deletes candidate points then rebuilds. | [ingestion.py:213–271](backend/app/ingestion.py#L213). Count equality verifies cardinality, not chunk text/checksum completeness after arbitrary external corruption. F05/F06 cover overlap and uncertainty. |

Actual parser performance, memory peaks, non-UTF8 reproduction, failure-injected embedding/upsert behavior and live dimension compatibility are NOT_VERIFIED. No provider-quality evaluation was attempted.

## 5. Retrieval Correctness Assessment

**ALL_ACTIVE:** query Mongo document identities whose status is INDEXED and active_version_id is a string; return the pointer tuple ([document_repository.py:124–136](backend/app/document_repository.py#L124)). **SELECTED_DOCUMENTS:** resolve each stored document ID, skip missing documents, require INDEXED, nonnull pointer and deleted_at=null; do not fall back to ALL_ACTIVE when all selected documents are excluded ([rag/pipeline.py:242–262](backend/app/rag/pipeline.py#L242)). Scope model disallows empty selected-ID lists and duplicates ([conversation_models.py:36–56](backend/app/conversation_models.py#L36)).

Retriever uses the explicit active-version tuple once prepared, skips embed_query and vector search if it is empty, otherwise embeds the retrieval query and asks Qdrant top-k with a server-side version_id MatchAny filter ([rag/retriever.py:31–68](backend/app/rag/retriever.py#L31), [qdrant_ingestion.py:42–62,156–178](backend/app/qdrant_ingestion.py#L42)). Empty explicit scope cannot accidentally become an unfiltered query because the retriever returns before constructing VectorFilter(version_ids=()). Under normal repository invariants, deleted/inactive candidates are excluded from newly resolved scopes.

Important boundaries:

- Scope is **request-local**, not a database transaction or revocation barrier. Selected documents are read sequentially; deletion or activation during those reads/provider generation can produce an older snapshot. The tuple does not expand after preparation, but old-version points may be removed before Qdrant search completes ([rag/pipeline.py:84–98,250–262](backend/app/rag/pipeline.py#L84)). Concurrent runtime outcomes remain NOT_VERIFIED.
- Resolver trusts the document pointer; it does not join the version record to revalidate status, embedding_model or vector_collection. ALL_ACTIVE also relies on DELETED/status consistency rather than additionally checking deleted_at. Normal unpublish clears status/pointer together; corrupted/out-of-band metadata is not independently repaired on reads ([document_repository.py:124–136,382–411](backend/app/document_repository.py#L124)). This is a trust boundary, not proof normal lifecycle leaks inactive versions.
- Returned payloads are parsed/UUID-validated, but there is no independent Mongo document/version ownership lookup or point-ID recomputation per hit. Normal ingestion writes those relationships consistently; external tampering/mixed embedding spaces are not disproved by source metadata validation ([qdrant_ingestion.py:180–198](backend/app/qdrant_ingestion.py#L180), [vector_index.py:133–144](backend/app/vector_index.py#L133)).
- Missing Qdrant collection returns []; vector/provider exceptions are raised rather than converted to a no-information answer. The missing-collection behavior is intentional in an existing test, although it cannot distinguish a lost collection from an empty corpus for the caller ([qdrant_ingestion.py:168–170,200–203](backend/app/qdrant_ingestion.py#L168), [tests/test_multi_session_isolation.py:275–281](backend/tests/test_multi_session_isolation.py#L275)). Operational detection remains NOT_VERIFIED.

**Attachments are message references, not retrieval filters.** Backend checks version ownership, non-deleted document and INDEXED version, persists the references, then prepares retrieval from session scope; it does not pass attachments into preparation ([attachments.py:17–38](backend/app/attachments.py#L17), [api/chat.py:315–362,450–473](backend/app/api/chat.py#L315), [rag/pipeline.py:64–98](backend/app/rag/pipeline.py#L64)). The existing UI contract explicitly says attachments do not change scope ([frontend/components/chat/message-attachment.tsx:24–25](frontend/components/chat/message-attachment.tsx#L20)). Absence of attachment-scoped retrieval is **not a defect**. Attaching an older INDEXED version does not make it active; its preview identity and the version retrieved under session scope can differ by design.

## 6. RAG Preparation Assessment

### History, rewrite and generation

History loader gets the server session/scope, pages all messages, groups by request_id, requires exactly two same-session messages ordered USER COMPLETED then ASSISTANT COMPLETED with adjacent sequence; defaults exclude partial/failed/active turns. Diagnostic opt-in can include terminal unsuccessful turns, never active ones ([history.py:66–139](backend/app/history.py#L66)). Budget selection takes the most recent whole-turn suffix and stops if the newest remaining turn cannot fit; it does not substitute an older turn ([context_budget.py:194–205](backend/app/context_budget.py#L194)).

Preparation budgets history before rewriting, then invokes the rewriter with the original full question and selected history. No history/independent query skips provider; timeout/provider error/invalid/ungrounded rewrite falls back to the original. Lexical grounding accepts only original/history tokens plus safe connectors and requires some history-derived token ([rag/pipeline.py:114–124](backend/app/rag/pipeline.py#L114), [query_rewriting.py:170–276](backend/app/query_rewriting.py#L170)). This is a vocabulary guard, not proof that a rewrite preserves meaning or question intent (F09). Long original questions are still unbounded at the rewrite/retrieval input stage even when generation later truncates them (F07/F08).

Rewritten query is used only for retrieval. Generation receives budget.query from the original question, whole selected history, ranked selected context; JSON and SSE use the same prepared representation ([rag/pipeline.py:124–155,175–188,228–239](backend/app/rag/pipeline.py#L124)). This is supported by assertions in [tests/test_rag_integration.py:76–167](backend/tests/test_rag_integration.py#L76); those tests were not executed.

### Budget, ordering and empty context

Allocation sums are validated; system is rejected rather than truncated; query uses head-tail truncation, chunks preserve prefix ranking and truncate only the last fitting block. Sources are the prefix of returned documents matching selected block count; format_context_blocks prefixes every production block with [ordinal] and file metadata, so the blank-block skipping branch in the generic builder is not a demonstrated production source-index mismatch ([context_budget.py:34–58,134–192,207–278](backend/app/context_budget.py#L134), [rag/prompt.py:55–64](backend/app/rag/prompt.py#L55), [rag/pipeline.py:125–148](backend/app/rag/pipeline.py#L125)). A severely truncated block can consist mostly of its source header; metadata existence alone does not prove enough grounding text remains.

Budget uses an approximate counter over component messages; the final prompt renders history and context inside a separate human template. Wrapper text, empty-history/context labels and final serialization are not remeasured; output reserve is not bound as an output limit in the LLM factory or calls (F08). Reported usage.total is not a guarantee of actual provider token count.

Empty retrieval inserts a no-relevant-document label into context and **still calls generation**. System instructs refusal when context is insufficient, disallows outside knowledge and invented sources/citations. There is no server-side forced refusal or deterministic semantic sufficiency check ([rag/pipeline.py:132–145,175–184](backend/app/rag/pipeline.py#L132), [rag/prompt.py:6–22](backend/app/rag/prompt.py#L6)). Irrelevant but nonempty top-k also relies on prompt compliance; no score threshold/reranker is applied in [qdrant_ingestion.py:171–178](backend/app/qdrant_ingestion.py#L171). These are quality/trust limitations, not unimplemented roadmap bugs.

Basic trust boundary: system instructions occupy a separate system message; history is described as reference-resolution data, not factual evidence. Rewriter labels HISTORY untrusted. Final context/history/file names are interpolated as plain text without enforced data delimiters or a semantic policy checker ([rag/prompt.py:18–41,45–64](backend/app/rag/prompt.py#L18), [query_rewriting.py:268–276](backend/app/query_rewriting.py#L268)). Citation eligibility validates source identity/ordinal, not whether the cited chunk supports the answer ([citation_mapping.py:12–55](backend/app/citation_mapping.py#L12)). No live injection/quality claims are made (F09).

## 7. Cross-store Data Consistency Assessment

| Boundary/failure point | Enforced guarantee | Best-effort or uncovered behavior |
| --- | --- | --- |
| Local save | Temp write + flush/fsync + atomic hard-link publication, no overwrite; cleanup temp path in finally. | Process death can leave temp/orphan raw file before Mongo creation; no crash sweep in this path. [storage.py:140–167](backend/app/storage.py#L140), [ingestion.py:124–152](backend/app/ingestion.py#L124). |
| Raw ↔ Mongo creation | Save precedes metadata; metadata errors attempt raw delete; repository compensates acknowledged earlier inserts. | Network-ambiguous inserts/failed rollback can leave records without raw or raw without complete records; no transaction across stores. [document_repository.py:45–71,149–179](backend/app/document_repository.py#L45), [ingestion.py:138–150](backend/app/ingestion.py#L138); F06. |
| Embedding/upsert | Published pointer normally stays old/absent; deterministic same-version IDs and wait=true upsert; verify exact count. | Partial writes attempt candidate delete/FAILED; cleanup errors are swallowed. Stale inactive vectors may persist. [ingestion.py:195–250,280–295](backend/app/ingestion.py#L195), [qdrant_ingestion.py:144–154](backend/app/qdrant_ingestion.py#L144). |
| Upsert verified → activation | Preserve vectors on metadata finalization error; reconcile can retry complete plan. | Activation uses multiple Mongo updates; early-stage interruptions excluded, later recovery can starve, concurrent worker not fenced: F02/F03/F05. [ingestion.py:254–271,297–337](backend/app/ingestion.py#L254), [document_repository.py:256–318,417–439](backend/app/document_repository.py#L256). |
| Version supersession | New pointer means old points no longer included in newly resolved retrieval scope. | Old-version raw and vectors are not garbage-collected on activation; retention is not an active-retrieval violation. [document_repository.py:270–304](backend/app/document_repository.py#L270), [document_service.py:84–102](backend/app/document_service.py#L84). |
| Delete | Metadata unpublish precedes vector deletion; vector failure leaves cleanup_pending=true and repeat DELETE can retry. | Hard interruption has no automatic cleanup scheduler in inspected startup/CLI; cleanup flag can depend on manual invocation. Concurrent ingester may still write candidate points before noticing deletion; future retrieval remains constrained by pointer/status, physical cleanup must be separately verified. [document_service.py:104–128](backend/app/document_service.py#L104), [ingestion.py:254–271](backend/app/ingestion.py#L254), [main.py:20–38](backend/app/main.py#L20). |
| Re-index/raw integrity | Immutable source read is required; missing file produces raw_file_read_failed; old active survives new candidate failure. | Stored checksum is not recomputed when materializing/re-indexing; out-of-band raw changes/corruption are not detected against metadata in these reads. [document_service.py:89–102](backend/app/document_service.py#L89), [ingestion.py:170–187](backend/app/ingestion.py#L170). No actual corruption observed. |

Invariants are enforced locally and by conditional updates, not by a distributed transaction. Recovery is partly manual and compensatory; neither all-or-nothing consistency nor complete crash recovery should be inferred from a successful happy-path test.

## 8. Findings Register

### F01 — UTF-8 decode failure bypasses intended autodetection

- **Component/location:** [backend/app/rag/loader.py:54–65](backend/app/rag/loader.py#L54), `_load_text`; local [TextLoader.lazy_load:41–58](.venv/Lib/site-packages/langchain_community/document_loaders/text.py#L41); [BaseLoader.load:37–44](.venv/Lib/site-packages/langchain_core/document_loaders/base.py#L37).
- **Expected invariant:** the function's documented UTF-8-first behavior falls back to autodetect for a non-UTF8 text file.
- **Actual path:** first TextLoader has autodetect_encoding=false. Its UnicodeDecodeError is caught and raised as RuntimeError; load() propagates it. Application catches only UnicodeDecodeError, so second loader is never reached. Ingestion wraps it as parse_failed.
- **Reproduction reasoning:** provide UTF-16 BOM bytes, e.g. FF FE 41 00, in a .txt or .md file. UTF-8 decoding fails immediately; local TextLoader's else branch raises RuntimeError; application fallback cannot catch that type. This is static reasoning, NOT_EXECUTED.
- **Impact/severity:** valid non-UTF8 text is rejected, despite fallback contract; **Medium**. UTF-16 preview support does not fix ingestion ([attachments.py:60–68](backend/app/attachments.py#L60)).
- **Classification:** **CONFIRMED_DEFECT**, source-confirmed with local langchain-community 0.4.2; other deployment versions NOT_VERIFIED.
- **Existing coverage:** inspected ingestion tests use UTF-8/ASCII content, XLSX/PDF fixtures; no non-UTF8 fallback regression found in `backend/tests/` search. Related [test_ingestion.py:282–315](backend/tests/test_ingestion.py#L282), [test_message_attachments_excel.py:136–159](backend/tests/test_message_attachments_excel.py#L136). No test executed.
- **Recommended action:** approve a narrow encoding-handling change compatible with actual TextLoader exceptions or supported built-in autodetection; add UTF-8 Vietnamese, UTF-16 BOM and a deliberately invalid text fixture. Do not silently swallow unrelated RuntimeError failures.

### F02 — Reconciliation applies its job limit before eligibility filtering

- **Component/location:** [backend/app/document_repository.py:417–437](backend/app/document_repository.py#L417), `list_processing_versions`; [backend/app/ingestion.py:297–337](backend/app/ingestion.py#L297), `reconcile_processing`.
- **Expected invariant:** repeated bounded reconciliation runs can eventually inspect eligible recoverable jobs, rather than being permanently blocked by records it never processes.
- **Actual path:** select oldest PROCESSING jobs and limit to 100, extract version IDs, then query versions with PROCESSING/INDEXED and chunk_count>0. Excluded jobs are not advanced, failed or touched by the caller because no version is returned for them.
- **Deterministic scenario:** seed 100 oldest PROCESSING jobs with associated PROCESSING versions whose chunk_count=0; add one newer PROCESSING job with a positive plan and complete vectors. Each default run selects the same first 100, returns no versions, and reports zero work; newer valid candidate is never reached. No concurrency is needed to demonstrate the selector logic. Dataset was reasoned about, not inserted or executed.
- **Impact/severity:** sustained recovery failure and misleading zero-work summaries for recoverable jobs; **High** once that backlog exists.
- **Classification:** **CONFIRMED_DEFECT**, source-demonstrated selection starvation. Existence/frequency of such backlog in deployment is NOT_VERIFIED.
- **Existing coverage:** [test_ingestion.py:349–364](backend/tests/test_ingestion.py#L349) covers one finalization failure using MemoryRepository. Its [list_processing_versions:228–239](backend/tests/test_ingestion.py#L228) filters eligible versions **before** limiting, unlike production. Test cannot reveal this selector-order defect. No test executed.
- **Recommended action:** approve production-selector pagination/eligibility correction with a repository-level regression containing >limit ineligible older jobs and an eligible later candidate. Require progress across repeated runs, not just summary counts.

### F03 — Interrupted early ingestion stages are outside recovery selection

- **Component/location:** [backend/app/ingestion.py:124–152,154–168,195–213,297–337](backend/app/ingestion.py#L124); [backend/app/document_repository.py:417–437](backend/app/document_repository.py#L417); [backend/scripts/reconcile_ingestion.py:16–36](backend/scripts/reconcile_ingestion.py#L16).
- **Expected behavior:** the failure-recovery assessment must distinguish complete post-plan recovery from crashes before a plan exists; early abandoned records need an explicit terminalization/retry mechanism if recovery is to be complete.
- **Actual path:** plan is saved only after parsing and embedding. PENDING jobs are excluded; PROCESSING versions with chunk_count=0 are excluded. retry() accepts only FAILED versions. CLI invokes the same reconciler; it has no separate early-stage sweep.
- **Scenario:** process stops after create_upload but before mark_processing, or after mark_processing during parse/embed but before set_chunk_plan. Restart leaves UPLOADED/PENDING or PROCESSING/zero-plan records. Inspected retry/reconcile cannot advance these states. A raw file saved before metadata inserts has no corresponding job to enumerate at all.
- **Impact/severity:** abandoned jobs/documents/raw files require operator intervention; first upload can remain nonretrievable; **Medium**. Existing old active versions need not become unavailable.
- **Classification:** **CONFIRMED_GAP** in comprehensive interruption recovery. No hard crash was performed, and this does not contradict the narrower existing post-verification recovery test.
- **Existing coverage:** [test_ingestion.py:349–364](backend/tests/test_ingestion.py#L349) only simulates finalization failure after plan/vectors. [test_storage.py:104–109](backend/tests/test_storage.py#L104) covers caught write failure, not process death. No test executed.
- **Recommended action:** define stale-age/ownership criteria and early-state recovery policy before implementing it; test crash checkpoints before metadata, before processing and before plan. Keep intentional retained audit/raw files distinct from actual orphans.

### F04 — Dimension compatibility does not prevent mixed embedding spaces

- **Component/location:** [backend/app/qdrant_ingestion.py:87–108,156–178](backend/app/qdrant_ingestion.py#L87); [backend/app/rag/retriever.py:38–52,95–103](backend/app/rag/retriever.py#L38); [backend/app/document_repository.py:124–136](backend/app/document_repository.py#L124); [backend/app/ingestion.py:207–212](backend/app/ingestion.py#L207).
- **Expected invariant:** query and selected indexed vectors must come from compatible embedding spaces, not merely equal dimension/cosine distance.
- **Actual path:** ingestion stores embedding_model on each version but collection check compares only size/distance; active resolution does not filter/check model or stored vector_collection; query embeds using currently configured provider/model.
- **Scenario/premise:** configuration changes to a different same-dimension model while older active versions remain in the same collection. New upserts pass schema checks; retrieval silently compares incompatible vectors. Different dimensions tend to fail at collection check/provider search instead, not silently validate the model identity.
- **Impact/severity:** plausibly incorrect relevance across the corpus without a schema error; **High**, conditional on model drift.
- **Classification:** **DESIGN_RISK**; model change and resulting quality degradation NOT_VERIFIED. Not a claim current collection is mixed.
- **Existing coverage:** [test_ingestion.py:366–369](backend/tests/test_ingestion.py#L366) checks dimension mismatch only; [test_retriever.py:56–95](backend/tests/test_retriever.py#L56) checks version metadata/filtering with fake embeddings. No same-dimension model-identity compatibility test found. No test executed.
- **Recommended action:** define an embedding-space fingerprint/versioned collection policy and fail closed on incompatibility; add offline same-dimension/different-model cases. Require explicit, separately approved re-index/migration before any live change.

### F05 — Reconciliation/retry can overlap an active candidate writer

- **Component/location:** [backend/app/ingestion.py:154–168,195–240,297–337](backend/app/ingestion.py#L154); [backend/app/document_repository.py:181–229,256–318,417–437](backend/app/document_repository.py#L181); [backend/app/document_indexes.py:50–59](backend/app/document_indexes.py#L50).
- **Expected invariant:** candidate cleanup/FAILED transitions cannot destroy or invalidate data another owner is about to publish; a recovery process should distinguish abandoned and live work.
- **Actual path:** selector has no stale-age cutoff/lease/claim. Reconciler counts and deletes incomplete nonactive candidates. Version processing/finalization does not fence updates by a worker token; separate retry attempts can also enter processing of the same FAILED version. Document pointer CAS protects publication ordering/deletion but does not serialize all candidate vector writes.
- **Plausible interleaving:** writer saves plan and begins vector write; reconciler observes incomplete count; writer completes/upsert-verifies; reconciler deletes vectors and marks FAILED; writer later calls complete_and_activate, which does not require previous PROCESSING/version ownership. Alternatively simultaneous retries can delete each other's same-version points. Timing/driver behavior needs controlled verification.
- **Impact/severity:** possible active pointer with missing/changed vectors or contradictory job/version states; **High**.
- **Classification:** **DESIGN_RISK**, not a proven concurrent bug. No interleaving, cloud write or deterministic concurrency reproduction was executed.
- **Existing coverage:** MemoryRepository finalization recovery and failed-version retry tests are sequential ([test_ingestion.py:315–364](backend/tests/test_ingestion.py#L315)); unique document-version index coverage verifies specification, not job ownership ([test_document_models.py:90–103](backend/tests/test_document_models.py#L90)). No relevant worker/reconciler race test found. No test executed.
- **Recommended action:** specify stale detection and per-version processing ownership/fencing; first add deterministic blocked-writer/step-controlled offline tests. Also test update/delete overlap and duplicate version-number conflicts against production repository semantics.

### F06 — Metadata/raw/vector rollback depends on ambiguous best-effort compensation

- **Component/location:** [backend/app/document_repository.py:45–71,149–179,256–318](backend/app/document_repository.py#L45); [backend/app/ingestion.py:138–150,254–295](backend/app/ingestion.py#L138); [backend/app/document_service.py:104–128](backend/app/document_service.py#L104).
- **Expected invariant:** failure handling should preserve enough durable intent to distinguish absent, committed and uncertain writes before destructive rollback.
- **Actual path:** repository compensates inserts acknowledged in its local list; cleanup exceptions are swallowed. Any create-metadata error makes ingestion attempt raw delete. Candidate vector/FAILED cleanup is best-effort. Pointer, version and job finalization are separate Mongo writes; DELETE metadata and vector cleanup are separate stores.
- **Scenario/premise:** an insert commits on server but raises a network/ack error, or rollback delete fails. Client can remove raw bytes while a committed record survives, or leave unreferenced bytes/vectors. A finalization response can fail after pointer activation even though client sees metadata_finalize_failed. No real ambiguous commit was simulated.
- **Impact/severity:** possible orphan raw/vectors, metadata pointing at missing raw, incomplete jobs and uncertain client outcome; **High** for cross-store durability, conditional on failures.
- **Classification:** **DESIGN_RISK**. Ordinary caught error compensation exists; this finding does not claim transactions would atomically encompass Qdrant/local storage.
- **Existing coverage:** [test_ingestion.py:349–364,433–452](backend/tests/test_ingestion.py#L349) covers single injected finalize failure and vector-cleanup unavailability through fakes; [test_storage.py:104–109](backend/tests/test_storage.py#L104) covers local write cleanup. No ambiguous acknowledged/committed insert or compensation-failure matrix found for MongoDocumentRepository. No test executed.
- **Recommended action:** define durable stage/intent records and idempotent reconciliation including raw/metadata ownership; test commit-then-raise and cleanup-raises adapters. Consider Mongo transactions only within Mongo boundaries; keep distributed recovery explicit.

### F07 — Non-XLSX ingestion and pre-generation query processing lack application bounds

- **Component/location:** [backend/app/api/documents.py:125–135](backend/app/api/documents.py#L125), [backend/app/ingestion.py:170–201,237](backend/app/ingestion.py#L170), [backend/app/rag/loader.py:41–65](backend/app/rag/loader.py#L41), [backend/app/schemas.py:99–106](backend/app/schemas.py#L99), [backend/app/rag/pipeline.py:114–129](backend/app/rag/pipeline.py#L114).
- **Expected boundary:** processing should fit a defined resource envelope before complete reads/parsing/embedding; generation budget alone does not bound all preceding provider work.
- **Actual path:** PDF/TXT/MD use file.read() with no maximum here; parser/chunks/vectors materialize whole inputs and embedding receives all chunk texts. question has minimum length but no maximum; full original question goes to rewrite/embedding before generation truncation. XLSX has explicit separate limits.
- **Scenario/premise:** a very large text/PDF or question consumes memory/CPU, creates many chunks or exceeds provider request limits before budget truncation. External proxy/request limits may reduce exposure but were not inspected/verified as an active deployment control.
- **Impact/severity:** possible request exhaustion, rejection or excessive provider workload; **Medium**. No OOM, performance limit or provider charge was triggered.
- **Classification:** **DESIGN_RISK**, not a demonstrated incident or claim the framework has no multipart safeguards.
- **Existing coverage:** [test_message_attachments_excel.py:250–280](backend/tests/test_message_attachments_excel.py#L250) checks workbook limits; [test_context_budget.py:137–168](backend/tests/test_context_budget.py#L137) checks later text truncation. No non-XLSX size or pre-rewrite oversized-query contract test found. No test executed.
- **Recommended action:** decide accepted file/question limits, enforce before full processing/provider use, then test rejection offline. Batch embedding/upsert only after those semantics are settled.

### F08 — Reported context budget is not a final provider request/output bound

- **Component/location:** [backend/app/context_budget.py:96–119,147–186](backend/app/context_budget.py#L96); [backend/app/rag/prompt.py:18–22,35–51](backend/app/rag/prompt.py#L18); [backend/app/rag/pipeline.py:125–145,175–184,228–239](backend/app/rag/pipeline.py#L125); [backend/app/rag/llm.py:16–27](backend/app/rag/llm.py#L16).
- **Expected boundary:** if budget is intended as a hard request limit, measure the actual final messages and constrain provider output consistently with the reserved allocation.
- **Actual path:** counts system/history/chunks/query as synthetic messages before rendering one human template; labels/separators/empty-context text are added afterwards and not recounted. Synthetic per-message overhead can overestimate some components, so omission is not proof every prompt overflows. ChatOpenAI construction/calls do not explicitly bind rag_output_reserve_tokens as an output cap.
- **Scenario/premise:** a nearly full, multilingual prompt or long model response exceeds intended application window/reserve despite an accepted component estimate. Exact outcome depends on tokenizer, SDK/provider defaults and model limits.
- **Impact/severity:** possible context rejection, unexpectedly long output or inconsistent budget telemetry; **Medium**.
- **Classification:** **DESIGN_RISK**; NOT_VERIFIED actual overflow. Approximate counting itself is already documented and is not mislabeled as a new defect.
- **Existing coverage:** [test_context_budget.py:85–101](backend/tests/test_context_budget.py#L85) asserts builder component totals; [test_rag_integration.py:158–167](backend/tests/test_rag_integration.py#L158) asserts prepared.budget total. Neither measures final rendered message tokens or enforces SDK output limits. No test executed.
- **Recommended action:** define estimate vs hard-limit contract, count final rendered messages with the chosen estimator/tokenizer, leave a validated margin and bind an explicit provider-compatible output limit if required. Verify via offline captured invocation parameters before any live call.

### F09 — Grounding and injection boundaries depend on model compliance

- **Component/location:** [backend/app/rag/prompt.py:6–41,45–64](backend/app/rag/prompt.py#L6); [backend/app/query_rewriting.py:243–276](backend/app/query_rewriting.py#L243); [backend/app/rag/pipeline.py:132–145,175–184](backend/app/rag/pipeline.py#L132); [backend/app/citation_mapping.py:12–55](backend/app/citation_mapping.py#L12).
- **Expected boundary:** context/history are evidence/reference data, not trusted instructions; no-information response and citations should not be mistaken for verified semantic entailment.
- **Actual path:** system instruction expresses grounding policy; rewriter marks history untrusted; final prompt includes raw source name/context/history as text. Lexical rewrite check verifies vocabulary provenance, not query preservation. Citation mapping verifies IDs/ordinals, not factual support. Empty retrieval still generates through LLM.
- **Scenario/premise:** a retrieved chunk/history includes conflicting instructions or a rewrite changes intent while reusing allowed words; model may follow those instructions or produce unsupported content with valid citation IDs. No attack payload or live model evaluation was run, so susceptibility/success is unknown.
- **Impact/severity:** plausible unsupported answer or retrieval misdirection; **Medium** for this correctness audit.
- **Classification:** **DESIGN_RISK**; semantic grounding/refusal robustness **NOT_VERIFIED**. No authentication/data-exfiltration audit implied.
- **Existing coverage:** [test_query_rewriting.py:122–190](backend/tests/test_query_rewriting.py#L122) checks lexical acceptance/rejection and fallback; [test_multi_session_isolation.py:268–273](backend/tests/test_multi_session_isolation.py#L268) uses mocked refusal/rewrite behavior; [test_citation_mapping.py::CitationMappingTests](backend/tests/test_citation_mapping.py) tests identity/ordinal rules. No adversarial semantic test establishes model compliance. No test executed.
- **Recommended action:** clarify trust labels/delimiters and empty-context policy; add offline prompt-boundary and intent-preservation cases. Defer claims of injection resistance/answer quality until separately approved evaluation with explicit provider budget.

### F10 — Phase 0A CWD-dependent storage finding is incorrect for production factory

- **Component/location:** [CODEBASE-INVENTORY.md:35](CODEBASE-INVENTORY.md#L35), [README discrepancy row in section 9](CODEBASE-INVENTORY.md#L370); current [backend/app/storage.py:203–210](backend/app/storage.py#L203), `create_file_storage`.
- **Expected documentation:** describe the application factory's effective root resolution, not just the low-level constructor.
- **Actual path:** factory joins relative config.documents_dir to PROJECT_ROOT, then instantiates LocalFileStorage. Direct constructor resolves a relative argument against CWD, but production service creation uses the factory ([document_service.py:131–145](backend/app/document_service.py#L131)).
- **Reasoning:** default ./data/documents becomes PROJECT_ROOT/data/documents regardless of process CWD in this path. The 0A claim that root/backend launch locations change production raw storage is not supported by current factory code.
- **Impact/severity:** incorrect operator/audit guidance; **Low**. No runtime file-location bug established.
- **Classification:** **DOCUMENTATION_MISMATCH**, including correction of this audit's primary reference. No assertion that source changed between phases.
- **Existing coverage:** [test_storage.py:115–122](backend/tests/test_storage.py#L115) verifies absolute configured path, not factory behavior across CWD. No test executed.
- **Recommended action:** acknowledge this correction in decisions; after owner approval update affected inventory/runbook statements and add a factory-relative-path regression. This round leaves all existing documentation unchanged.

## 9. Existing Test Coverage and Verification Gaps

| Area | Exact existing evidence inspected | What it supports; gap |
| --- | --- | --- |
| Storage | `backend/tests/test_storage.py::test_existing_version_is_never_overwritten` (:97), `test_failed_write_leaves_no_target_or_temporary_file` (:104), `test_factory_uses_configured_local_backend_and_documents_dir` (:115). | Immutable publication and caught-failure cleanup intent. No process-kill/orphan sweep test or relative-factory CWD test. |
| Ingestion/lifecycle | `backend/tests/test_ingestion.py::test_successful_ingestion_saves_indexes_verifies_and_activates` (:282), `test_failed_new_version_preserves_active_version_and_can_retry` (:315), `test_finalize_failure_is_reconciled_without_deleting_verified_vectors` (:349), `test_document_management_list_get_update_reindex_and_delete` (:377), `test_delete_unpublishes_even_when_qdrant_cleanup_is_pending` (:433). | Real temporary local storage/Qdrant :memory: and deterministic embeddings, but MemoryRepository replaces production Mongo operations. Selector mismatch matters for F02; no worker/reconciler interleaving coverage. |
| Metadata/index contract | `backend/tests/test_document_models.py::test_duplicate_document_id_and_version_is_rejected_by_unique_spec` (:90), `test_index_initialization_is_idempotent_for_unchanged_specs` (:127). | Model/index specifications through fakes; not live Mongo transaction/conditional-update behavior. |
| API contracts | `backend/tests/test_documents_api.py::test_document_lifecycle_routes` (:98), `test_delete_returns_202_when_cleanup_must_be_retried` (:139). | Handler response contracts with service doubles, not actual cross-store lifecycle integration. |
| XLSX/PDF/attachments | `backend/tests/test_message_attachments_excel.py::test_real_multisheet_upload_indexes_and_retrieves_correct_row_and_metadata` (:97), `test_real_pdf_upload_still_parses_indexes_and_preserves_zero_based_page` (:143), `test_json_and_sse_user_messages_persist_only_validated_attachment_references` (:172); `WorkbookValidationTests` (:244); `backend/tests/test_xlsx_loader.py::test_xlsx_optional_dependencies_parse_workbook_offline` (:15). | Offline parser/metadata and attachment contract intent. Some use temporary writes and local Qdrant, so not represented as literal zero-filesystem-side-effect tests. No F01 non-UTF8 fixture. |
| Qdrant adapter/retriever | `backend/tests/test_vector_index.py::test_add_query_filter_upsert_count_and_delete` (:49), `test_value_objects_validate_ids_vectors_and_safe_delete_scope` (:111); `backend/tests/test_retriever.py::test_retrieval_uses_mongodb_active_version_filter_and_preserves_metadata` (:56), `test_no_active_versions_returns_no_results_without_vector_query` (:76). | In-memory adapter and fake-filter invariants; no same-dimension model drift, mixed/corrupt payload or concurrent lifecycle revocation test. |
| History | `backend/tests/test_history.py::test_loads_correct_session_scope_order_and_all_pages` (:78), `test_default_drops_whole_partial_failed_and_active_turns` (:95), `test_orphans_cross_session_and_non_adjacent_pairs_are_never_returned` (:136). | Whole-turn filtering/session scope through fake history repository; no live pagination consistency guarantee under concurrent modifications. |
| Budget/rewrite | `backend/tests/test_context_budget.py::test_usage_covers_every_component_and_never_exceeds_allocations` (:85), `test_chunks_keep_rank_and_only_last_selected_chunk_is_truncated` (:151), `test_system_instruction_is_rejected_instead_of_truncated` (:170); `backend/tests/test_query_rewriting.py::test_provider_error_and_timeout_fall_back_without_raw_detail` (:173). | Component estimates and fake-provider lexical behavior; no final serialization/model-token budget or semantic entailment evidence. |
| Shared preparation/isolation | `backend/tests/test_rag_integration.py::test_selected_scope_rewrite_and_prompt_keep_separate_queries` (:76), `test_non_stream_generation_consumes_shared_prepared_prompt` (:169); `backend/tests/test_multi_session_isolation.py::test_empty_retrieval_can_produce_prompt_refusal_without_collision` (:268), `test_no_active_versions_skips_embedding_and_vector_query` (:282). | Mocked shared pipeline/filter/input separation and expected refusal; no actual LLM refusal/quality verification. |

**Execution ledger:** 0 existing tests invoked; 0 tests passed/failed/skipped by a test runner. Status for every suite above is **NOT_EXECUTED**. There was no cloud smoke/evaluation run and no new regression test or runtime fixture created. Static source traces are not counted as tests.

Limitations: broken interpreter retained; no production dependency/version reproducibility guarantee; local library source can differ from deployment; no cloud data/index inspection; no filesystem crash/atomicity experiment; no concurrency/fault-injection execution; no memory measurements; no actual provider tokenization or semantic quality assessment. Coverage searches support "not found in inspected tests," not a claim that no external test exists anywhere.

## 10. Recommended Next Actions

1. **Prioritize correctness, pending owner authorization:** reproduce/fix F01 with encoding fixtures; fix/test production reconciliation selection for F02; define and test early-stage stale recovery for F03. These are small scoped changes, not a platform rewrite.
2. **Validate high-risk distributed behavior offline:** add step-controlled tests for F05 and commit-then-error/rollback-error adapters for F06. Exercise actual Mongo repository query/update semantics in safe offline fixtures; mocks must match selection order and state filters. No cloud run is authorized by this report.
3. **Make compatibility explicit:** establish F04 embedding-space fingerprint and collection/version compatibility checks before any model migration. No production re-index is proposed for immediate execution.
4. **Clarify input, budget and trust contracts:** agree bounds for F07; distinguish estimated prompt allocations from model-facing limits for F08; define deterministic empty-context behavior/trust delimiters for F09. Semantic efficacy still needs a separately approved evaluation plan.
5. **Correct documentation later:** use F10 as an explicit correction now; update inventory/README/runbooks only after approval. This report does not grant permission to repair the Python environment or perform cloud/provider operations.

Deferred optimization opportunities, separate from confirmed defects:

| Opportunity | Source basis | Decision gate |
| --- | --- | --- |
| Read recent complete turns without paging whole history | `backend/app/history.py:88–103` loads all messages before `backend/app/context_budget.py:194–205` selects suffix. | Preserve whole-turn semantics; profile with offline long sessions first. |
| Batch embeddings/upsert | `backend/app/ingestion.py:199–201,237` handles all texts/records together. | Establish limits/error/partial-plan recovery before batching. |
| Avoid duplicate XLSX parse / full parse per preview | `backend/app/api/documents.py:130–132`, `backend/app/rag/loader.py:47–50`, `backend/app/excel.py:115–116`. | Retain validation and immutable-version semantics; measure before caching. |
| Calibrate relevance and chunk strategy | `backend/app/rag/splitter.py:34–45`, `backend/app/qdrant_ingestion.py:171–178`. | Use representative approved evaluation; absence of reranker/hybrid search is not itself a correctness bug. |

## 11. Final Verdict for Round 0B-01

**Source audit complete; runtime correctness remains NOT_VERIFIED.** The normal path has meaningful activation, scope and failure-compensation safeguards, but comprehensive interruption recovery is not established. F01/F02 justify focused correctness work, F03 requires an explicit recovery policy, and F04–F09 require targeted verification before claiming their scenarios occur. F10 retracts the earlier CWD-storage inference for production factory usage.

File-integrity verification: starting worktree had only untracked `CODEBASE-INVENTORY.md`. A read-only SHA-256 fingerprint of all 298 tracked files was recorded and compared before/after report creation; inventory was fingerprinted separately. Both comparisons matched:

- Tracked files aggregate (sorted path + NUL + bytes + NUL): `cea8f0bb1b426d5ec6157a1a136600f03df533c923ff6a46e569284617a9671d`.
- Unchanged Phase 0A inventory: `383f4a02dfdb5d5d3709798579a8190b5f3ea02a1d243a34fc9b97d6ab2469dc`.
- Static report check: all 11 required sections present; F01–F10 present; 149 source links resolve to existing files and valid line bounds. This is report validation, not execution of application tests.
- `git diff --name-only` returned no tracked changes. Worktree status contains the pre-existing untracked inventory and this new audit report only. No application source changes are part of this round.

This verdict assigns **no final project maturity level**. Round 0B-02, implementation, README changes, environment repair and live operations remain outside authorization. Work stops with this report.
