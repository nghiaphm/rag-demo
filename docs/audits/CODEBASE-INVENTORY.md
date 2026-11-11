# CODEBASE INVENTORY — Phase 0A

Discovery date: 2026-10-27 (Asia/Bangkok). Scope: source-led repository discovery; authentication excluded. Only this report was created. No implementation, README updates, provider calls, application startup, or cloud mutations were performed.

Evidence notation: paths are repository-relative; each reference identifies a symbol or line. `SOURCE_CONFIRMED` means the implementation exists in inspected source, not that it worked against running infrastructure. `DOCUMENTED_ONLY` means a documentation claim without fresh execution evidence. `NOT_VERIFIED` means behavior or environment was not exercised. `NOT_IMPLEMENTED` means the inspected route/component path has no implementation of the stated capability; this is bounded to that path, not a claim about all possible future integrations. Audit concerns below are hypotheses, not established defects.

## 1. Repository Overview

| Status | Area | Evidence and responsibility |
| --- | --- | --- |
| SOURCE_CONFIRMED | Backend application | `backend/app/main.py::app`, `lifespan`: FastAPI composition root; registers document, chat, session routers and initializes cloud connections/indexes. |
| SOURCE_CONFIRMED | Frontend application | `frontend/app/layout.tsx::RootLayout`, `frontend/app/chat/page.tsx::ChatPage`, `frontend/app/documents/page.tsx::DocumentsPage`: Next.js workspace shell, chat and document screens. |
| SOURCE_CONFIRMED | Tests and QA tooling | `backend/tests/test_rag_integration.py::RagIntegrationTests`, `frontend/package.json::scripts`, `frontend/playwright.config.ts` and `frontend/e2e/fixtures.mts::test`: Python tests, Node tests and browser fixtures. |
| SOURCE_CONFIRMED | Evaluation tooling | `backend/scripts/eval_cli.py::main`, `backend/scripts/eval_history_cli.py::main`; corpus, golden sets and stored reports under `backend/evaluation/` (catalog below). |
| DOCUMENTED_ONLY | Historical operational evidence | Root `README.md:34` describes persistence verified across restarts; `frontend/README.md:112–114` links earlier QA evidence. These are historical claims, not fresh runtime results. |

Inspection prioritized entrypoints, API contracts, persistence boundaries, main RAG and UI controllers, previews, provider adapters, manifests, both READMEs, test declarations and evaluation entrypoints. Ancillary UI primitives, static assets, every test assertion, every smoke-script body, historical logs and every stored evaluation result were not exhaustively audited. Test/script catalogs distinguish enumeration from deeper inspection.

## 2. Actual Technology Stack

All entries in this table are `SOURCE_CONFIRMED` declarations or imports; installed versions and deployment readiness are `NOT_VERIFIED`.

| Layer | Actual source evidence |
| --- | --- |
| Backend HTTP/config | FastAPI >=0.115, Uvicorn >=0.32, python-multipart, python-dotenv and pydantic-settings: `backend/requirements.txt:1–6`; Pydantic schemas: `backend/app/schemas.py::ChatRequest`, `ChatResponse`. Python dependencies use ranges/unpinned entries rather than an exact environment lock (`backend/requirements.txt`). |
| RAG framework | LangChain core >=1.2, OpenAI adapter >=1,<2, Google adapter >=4, community loaders and text splitters: `backend/requirements.txt:7–11`. |
| Generation | Cached LangChain `ChatOpenAI` configured with Groq key and OpenAI-compatible base URL: `backend/app/rag/llm.py::get_llm`. Defaults: Groq endpoint and `openai/gpt-oss-120b`, `backend/app/config.py::Settings`. These are configured identifiers, not a claim of current provider availability. |
| Embeddings | Google/Gemini aliases instantiate `GoogleGenerativeAIEmbeddings`; unsupported providers raise: `backend/app/rag/embeddings.py::get_embeddings`. Default `gemini-embedding-001`: `backend/app/config.py::Settings`. |
| Databases | PyMongo >=4.10,<5 and qdrant-client >=1.12,<2: `backend/requirements.txt`; adapters: `backend/app/cloud_connections.py::MongoDBConnection`, `QdrantConnection`. |
| Parsing | PyPDFLoader, TextLoader, RecursiveCharacterTextSplitter: `backend/app/rag/loader.py::_load`, `backend/app/rag/splitter.py::split_documents`. XLSX uses openpyxl directly: `backend/app/excel.py::read_workbook`; requirements also declare unstructured[xlsx], pandas, networkx and defusedxml (`backend/requirements.txt`). A dependency declaration alone does not establish runtime use. |
| Frontend | Next 16.4.0, React/React DOM 19.3.0; TypeScript ^5, Tailwind ^4, ESLint ^9, Playwright ^1.64.1: `frontend/package.json::dependencies`, `devDependencies`; npm lockfile: `frontend/package-lock.json:1`. |
| UI/rendering | Base UI, Lucide, react-markdown, remark-gfm, rehype-highlight: `frontend/package.json::dependencies`; Markdown/citation rendering: `frontend/components/chat/citation-content.tsx::CitationContent`; code rendering: `frontend/components/chat/code-block.tsx::CodeBlock`. |
| Frontend build | Cache components, partial prefetching and Tailwind Turbopack loader configured in `frontend/next.config.ts::nextConfig`; Google Geist fonts in `frontend/app/layout.tsx`. Build/network behavior was not exercised. |

Configuration: backend resolves root `.env` via `backend/app/config.py::PROJECT_ROOT`, `ENV_FILE`, `Settings`; raw storage defaults to relative `./data/documents`. Frontend pages read `NEXT_PUBLIC_API_BASE_URL` and pass null for blank values (`frontend/app/chat/page.tsx::ChatPage`, `frontend/app/documents/page.tsx::DocumentsPage`). Actual secret files were not read. Development CORS allows exactly localhost:3000 and 127.0.0.1:3000 with credentials disabled (`backend/app/main.py:42–48`).

## 3. Backend Module Map

Every row is `SOURCE_CONFIRMED`; runtime integration is `NOT_VERIFIED`.

| Responsibility | Files and relevant symbols |
| --- | --- |
| Startup/readiness | `backend/app/main.py::lifespan`, `health`, `dependency_health`; `backend/app/cloud_connections.py::CloudConnections.connect_all`. Startup can write MongoDB indexes, which is why discovery did not start the application. |
| HTTP API | `backend/app/api/documents.py::upload_document`, `document_preview`, `get_documents`, `get_document`, `update_document`, `reindex_document`, `remove_document`; `backend/app/api/chat.py::chat`, `chat_stream`; `backend/app/api/sessions.py` session handlers. |
| Public DTOs | `backend/app/schemas.py::ChatRequest`, `ChatResponse`, `Source`, `Citation`, `DocumentInfo`, `DocumentDetail`, `DocumentPreviewResponse`; `backend/app/conversation_schemas.py::CreateSessionRequest`, `SessionResponse`, `MessageResponse`; `backend/app/attachment_models.py::AttachmentReference`, `MessageAttachment`. |
| Document domain | `backend/app/document_models.py::DocumentRecord`, `DocumentVersionRecord`, `IngestionJobRecord`, `DocumentStatus`, `IngestionJobStatus`; `backend/app/document_service.py::DocumentService`. |
| Document persistence | `backend/app/document_repository.py::MongoDocumentRepository`: upload/version/job records, chunk plan, active-version lookup, activation, unpublish and cleanup; `backend/app/document_indexes.py::INDEX_DEFINITIONS`, `initialize_document_indexes`. |
| Ingestion | `backend/app/ingestion.py::IngestionService.ingest`, `_materialize_and_split`, `_process`, `_fail_before_activation`, `retry`, `reconcile_processing`; `create_ingestion_service` composes adapters. Retry/reconciliation methods are internal/script capabilities, not extra public endpoints. |
| Storage/vector abstraction | `backend/app/storage.py::FileStorage`, `LocalFileStorage`, `build_document_storage_key`; `backend/app/vector_index.py::VectorIndex`, `VectorRecord`, `VectorFilter`, `VectorSearchResult`, `chunk_point_id`; `backend/app/qdrant_ingestion.py::QdrantVectorIndex`. |
| Conversation domain | `backend/app/conversation_models.py::SessionRecord`, `SessionScope`, `SessionScopeMode`, `MessageRecord`, `MessageStatus`, `MessageCitation`, `MessageUsage`. |
| Conversation persistence/service | `backend/app/conversation_repository.py::MongoConversationRepository`; `backend/app/conversation_service.py::ConversationService.answer_with_persistence`, `begin_streaming_turn`, `finalize_streaming_turn`; `backend/app/conversation_indexes.py::CONVERSATION_INDEX_DEFINITIONS`. |
| Main RAG runtime | `backend/app/rag/pipeline.py::prepare_rag_request`, `prepare_rag_request_from_components`, `generate_prepared_answer`, `astream_rag_answer`, `_resolve_active_version_ids`; `backend/app/rag/retriever.py::QdrantActiveVersionRetriever`. |
| RAG supporting modules | `backend/app/rag/loader.py::load_document`; `backend/app/rag/splitter.py::split_documents`; `backend/app/rag/embeddings.py::get_embeddings`; `backend/app/rag/llm.py::get_llm`; `backend/app/rag/prompt.py::SYSTEM_INSTRUCTION`, `format_context_blocks`, `get_history_aware_rag_prompt`. |
| History/rewrite/budget | `backend/app/history.py::ConversationHistoryLoader`; `backend/app/query_rewriting.py::QueryDependencyDetector`, `QueryRewriter`; `backend/app/context_budget.py::ContextBudgetBuilder`, `ApproximateTokenCounter`. |
| Citations/stream transport | `backend/app/citation_mapping.py::map_verified_citations`; `backend/app/sse_schema.py::encode_sse_event` and typed event classes; `backend/app/api/chat.py::_encode_provider_stream_impl`, `_encode_provider_stream`; `backend/app/stream_metrics.py::StreamMetricTracker`, `record_stream_metric`. |
| Attachments/Excel | `backend/app/attachments.py::resolve_version`, `resolve_attachments`, `preview_version`; `backend/app/excel.py::read_workbook`, `workbook_documents`, `workbook_preview`. |
| Alternate chain/migration | `backend/app/rag/chain.py::build_rag_chain` is an LCEL chain used by `backend/scripts/eval_cli.py::main`; HTTP handlers use pipeline wrappers instead (`backend/app/api/chat.py` imports). `backend/app/data_migration.py::DemoCorpusMigration` supports corpus migration. Do not assume the older evaluation chain exercises history-aware HTTP preparation. |

## 4. Frontend Module Map

All listed routes/components are `SOURCE_CONFIRMED`; browser behavior is `NOT_VERIFIED` in this phase.

| Route | Actual implementation |
| --- | --- |
| `/` | Redirects to `/chat`: `frontend/app/page.tsx::Home`; also configured in `frontend/next.config.ts::redirects`. |
| `/chat` | `frontend/app/chat/page.tsx::ChatPage` → `ChatPreview`, with configured API URL or null. |
| `/chat/[sessionId]` | `frontend/app/chat/[sessionId]/page.tsx::SessionChatContent` awaits route params → `SessionChat`. |
| `/documents` | `frontend/app/documents/page.tsx::DocumentsPage` → `DocumentsPreview`. |

Route-file enumeration found these four page files and no `frontend/app/**/route.*` API handlers. Browser clients build backend URLs directly (`frontend/lib/api/client.ts::createApiClient`, `frontend/lib/api/chat.ts::createChatStreamClient`); no Next API proxy was found in that route tree.

| Area | Source map |
| --- | --- |
| Layout/navigation | `frontend/app/layout.tsx::RootLayout`; `frontend/components/layout/app-shell.tsx`, `session-navigation.tsx`, `session-actions.tsx`, `service-health.tsx` (named exported components). |
| Chat lifecycle | `frontend/components/chat/chat-preview.tsx::ChatPreview`; `frontend/hooks/use-chat-stream.ts`; `frontend/lib/chat/controller.ts::ChatController`; `frontend/lib/chat/services.ts::createChatServices`; recovery/scroll/clipboard helpers under `frontend/lib/chat/`. |
| Chat rendering | `frontend/components/chat/chat-composer.tsx::ChatComposer`, `chat-message.tsx::ChatMessage`, `citation-content.tsx::CitationContent`, `code-block.tsx::CodeBlock`; `frontend/lib/chat/citation-markdown.ts::rehypeCitationMarkers`, `source-mapper.ts::resolveCitationOrdinal`, `citation-panel.ts::buildCitationPanel`. |
| Session/history | `frontend/hooks/use-sessions.ts`; `frontend/lib/sessions/controller.ts`, `history.ts::loadMessageHistory`, `HistoryController`, `historyMessageToViewMessage`, `invalidation.ts`; `frontend/components/chat/session-chat.tsx::SessionChat`. |
| Document management | `frontend/components/documents/documents-preview.tsx::DocumentsPreview`, `document-upload.tsx`, `document-actions.tsx`, `document-dialogs.tsx`; `frontend/hooks/use-documents.ts`; `frontend/lib/documents/controller.ts::DocumentsController`, `upload-controller.ts::UploadController`, `actions-controller.ts::DocumentActionsController`, `upload-validation.ts::validateUploadFile`. |
| Attachments/preview | `frontend/hooks/use-chat-attachments.ts::useChatAttachments`; `frontend/components/chat/attachment-chip.tsx`, `message-attachment.tsx::MessageAttachmentChip`, `document-preview.tsx::DocumentPreview`, `document-preview-sheet.tsx::DocumentPreviewSheetContent`; `frontend/lib/documents/text-preview.ts::readTextPreview`. |
| Transport/contracts | `frontend/lib/api/{client,chat,documents,sessions,health,error-ux}.ts`; `frontend/lib/sse/parser.ts::SSEParser`; `frontend/types/{api,chat,document,sessions}.ts`. |

## 5. Current API Inventory

All 17 application method/path pairs below are `SOURCE_CONFIRMED` from decorators and router prefixes. This excludes FastAPI-generated documentation/OpenAPI routes. HTTP behavior is `NOT_VERIFIED` against a running server.

| Method/path | Contract and evidence |
| --- | --- |
| GET `/health` | Process/config response including model; `backend/app/main.py::health`. |
| GET `/health/dependencies` | Reconnect/check MongoDB and Qdrant; 200 or 503; no LLM/embedding readiness check; `backend/app/main.py::dependency_health`, `backend/app/cloud_connections.py::CloudConnections.connect_all`. |
| POST `/documents/upload` | Multipart file; synchronous ingestion awaited through threadpool; 201 `DocumentIndexInfo`; `backend/app/api/documents.py::upload_document`. |
| GET `/documents` | Array `DocumentInfo[]`; include_deleted=false, offset=0, limit=100 (max 500); no total envelope; `backend/app/api/documents.py::get_documents`. |
| GET `/documents/{document_id}` | UUID path; detail plus version history; `backend/app/api/documents.py::get_document`. |
| PUT `/documents/{document_id}` | Multipart new immutable version; 201; `backend/app/api/documents.py::update_document`. |
| POST `/documents/{document_id}/re-index` | New version from active raw bytes; 201; `backend/app/api/documents.py::reindex_document`, `backend/app/document_service.py::DocumentService.reindex`. |
| DELETE `/documents/{document_id}` | Unpublish then vector cleanup; 202 if cleanup pending, otherwise default 200; `backend/app/api/documents.py::remove_document`. |
| GET `/documents/{document_id}/versions/{version_id}/preview` | Version-specific text/Excel/unsupported JSON; requires MongoDB and raw storage, not Qdrant; `backend/app/api/documents.py::document_preview`, `backend/app/attachments.py::preview_version`. |
| POST `/chat` | JSON `ChatRequest` → `ChatResponse`; optional session persistence; logical generation failure response 502; `backend/app/api/chat.py::chat`, `_failed_generation_response`. |
| POST `/chat/stream` | Same request DTO; SSE 200 after preparation; pre-header errors remain HTTP; `backend/app/api/chat.py::chat_stream`. |
| POST `/sessions` | Title-only creation request; 201; `backend/app/api/sessions.py::create_session`, `backend/app/conversation_schemas.py::CreateSessionRequest`. |
| GET `/sessions` | items/offset/limit/total, offset=0, limit=50 (max 200); `backend/app/api/sessions.py::list_sessions`. |
| GET `/sessions/{session_id}` | UUID session; missing 404, tombstone 410; `backend/app/api/sessions.py::get_session`, `_handle_error`. |
| PATCH `/sessions/{session_id}` | Title update only; `backend/app/api/sessions.py::update_session_title`. |
| GET `/sessions/{session_id}/messages` | items/offset/limit/total, offset=0, limit=100 (max 500), sequence ordering; `backend/app/api/sessions.py::list_session_messages`, `backend/app/conversation_repository.py::list_messages`. |
| DELETE `/sessions/{session_id}` | Session tombstone plus hard-delete messages, conflicts with active generation; `backend/app/api/sessions.py::delete_session`, `backend/app/conversation_repository.py::delete_session`. |

`ChatRequest` requires a nonblank question, accepts at most 20 unique document/version attachment references, and rejects attachments without session_id (`backend/app/schemas.py::ChatRequest`, `_validate_attachments`). Attachments resolve before RAG preparation (`backend/app/api/chat.py::_attachments`, `chat`, `chat_stream`). Public session-scope mutation and message edit/regenerate/delete routes are `NOT_IMPLEMENTED` in these registered routers (`backend/app/main.py:50–52`, `backend/app/api/sessions.py` decorators).

## 6. Database & Storage Responsibilities

All responsibilities are `SOURCE_CONFIRMED`; current stored records, indexes and collection compatibility are `NOT_VERIFIED`.

| Store | Responsibility and boundary |
| --- | --- |
| MongoDB `documents` | Identity, source_key, active_version_id, lifecycle/deletion/cleanup flags: `backend/app/document_models.py::DocumentRecord`; `backend/app/document_indexes.py::DOCUMENTS_COLLECTION`. |
| MongoDB `document_versions` | Version number, checksum, size, storage key, embedding model, chunk count, vector collection and status: `backend/app/document_models.py::DocumentVersionRecord`; `backend/app/document_indexes.py::DOCUMENT_VERSIONS_COLLECTION`. |
| MongoDB `ingestion_jobs` | Version ingestion attempt/status/error/timestamps: `backend/app/document_models.py::IngestionJobRecord`; `backend/app/document_indexes.py::INGESTION_JOBS_COLLECTION`. |
| MongoDB `sessions` | Title, retrieval scope, sequence allocation and active generation ownership: `backend/app/conversation_models.py::SessionRecord`; `backend/app/conversation_repository.py::begin_generation`. |
| MongoDB `messages` | Role/content/status, request linkage, citations, user attachment references, usage/model/error; stable per-session sequence unique index: `backend/app/conversation_models.py::MessageRecord`; `backend/app/conversation_indexes.py::MESSAGE_INDEXES`. Ordered retrieved sources are absent from this model. |
| Qdrant | Embeddings plus chunk text and document/version/chunk/page/sheet/row metadata; deterministic version/chunk point IDs; cosine collection dimension validation: `backend/app/vector_index.py::VectorRecord.payload`, `chunk_point_id`; `backend/app/qdrant_ingestion.py::ensure_collection`. Mongo active versions constrain retrieval via server-side MatchAny filter (`_to_qdrant_filter`). |
| Local raw files | UUID-derived `documents/{document_id}/{version_id}/original` keys, checksum and immutable save/path validation: `backend/app/storage.py::build_document_storage_key`, `LocalFileStorage._resolve`, `save`. Only local backend accepted: `create_file_storage`, `backend/app/config.py::Settings._validate_storage_backend`. |
| Browser state | Preview width preference in sessionStorage with memory fallback: `frontend/components/chat/document-preview-sheet.tsx::DocumentPreviewSheetContent`. Chat persistence reads backend history (`frontend/lib/chat/services.ts::createChatServices`); this preference is not conversation storage. |

Document deletion retains raw/version audit history while clearing publication and cleaning vectors (`backend/app/document_service.py::DocumentService.delete`, `backend/app/document_repository.py::unpublish`). Session deletion has a different policy: retain session tombstone, delete related messages (`backend/app/conversation_repository.py::delete_session`). No cross-store transaction is implied: ingestion activation and message-pair writes are multiple operations with compensation (`backend/app/document_repository.py::complete_and_activate`, `backend/app/conversation_repository.py::create_message_pair`).

## 7. Core Execution Flows

### Document upload → ingestion → Qdrant

`SOURCE_CONFIRMED`:

1. UI validates extension/file and uploads multipart via `UploadController` → `uploadDocument` (`frontend/lib/documents/upload-controller.ts`, `frontend/lib/documents/upload-validation.ts::validateUploadFile`, `frontend/lib/api/documents.ts::uploadDocument`). Backend accepts PDF, MD/Markdown, TXT, XLSX (`backend/app/rag/loader.py::SUPPORTED_EXTENSIONS`); `_read_upload` performs XLSX size/MIME/workbook validation before service ingestion (`backend/app/api/documents.py`). Non-XLSX upload reads are unbounded in that function; deployment-level limits are `NOT_VERIFIED`.
2. `IngestionService.ingest` allocates identity/version/job, saves raw content, then inserts Mongo metadata; failed metadata creation attempts raw cleanup (`backend/app/ingestion.py`). Upload is an awaited request, not an enqueued background-worker API (`backend/app/api/documents.py::upload_document`).
3. `_process` marks processing, materializes a temporary file, loads/splits, calls embed_documents, stores chunk plan, deletes candidate-version points for retry idempotency, upserts deterministic chunk records, and verifies point count (`backend/app/ingestion.py::_materialize_and_split`, `_process`). XLSX row documents preserve sheet/row metadata (`backend/app/excel.py::workbook_documents`).
4. `complete_and_activate` marks the version indexed, uses conditional document update to avoid replacing a newer active version/deleted document, and completes the job (`backend/app/document_repository.py::complete_and_activate`). Pre-activation failures attempt vector cleanup and FAILED metadata; post-vector finalization failure leaves reconciliation work (`backend/app/ingestion.py::_fail_before_activation`, `reconcile_processing`).

`NOT_VERIFIED`: actual provider embeddings, memory/resource behavior on large files, cloud write consistency and interruption recovery.

### Chat request → retrieval → generation

`SOURCE_CONFIRMED`:

1. `chat` resolves attachments/dependencies. Stateless runs `answer_question`; persistent wraps it in `ConversationService.answer_with_persistence`, which acquires a guard and creates user/assistant records before generation (`backend/app/api/chat.py::chat`, `backend/app/conversation_service.py`).
2. `prepare_rag_request` loads server session scope/history, snapshots allowed active versions and composes retriever (`backend/app/rag/pipeline.py`). `ConversationHistoryLoader` paginates all messages, pairs adjacent USER/ASSISTANT sequences with shared request_id and defaults to completed whole turns (`backend/app/history.py::_load_all_messages`, `_complete_turns`).
3. Budget recent history, conditionally rewrite retrieval query with fallback, embed query and retrieve top-k with version filter, then budget ranked context and original question (`backend/app/rag/pipeline.py::prepare_rag_request_from_components`, `backend/app/query_rewriting.py::QueryRewriter`, `backend/app/rag/retriever.py::_get_relevant_documents`). Empty allowed versions return no documents before embed_query.
4. `generate_prepared_answer` calls LLM ainvoke with prepared prompt and normalizes text/usage; wrapper `answer_question` runs the async pipeline from the worker thread. Citations map answer ordinals to eligible source metadata, not model-supplied IDs (`backend/app/rag/pipeline.py`, `backend/app/citation_mapping.py::map_verified_citations`).

`SOURCE_CONFIRMED` limits: token accounting is approximate (`backend/app/context_budget.py::ApproximateTokenCounter`); context scope is a preparation-time snapshot (`backend/app/rag/pipeline.py::_resolve_active_version_ids`). `NOT_VERIFIED`: grounding quality, model-specific token fit, relevance and rewrite quality on production inputs.

### SSE streaming → persistence

`SOURCE_CONFIRMED`: `chat_stream` prepares retrieval/prompt before `begin_streaming_turn` acquires the generation guard. The service saves user COMPLETED + assistant PENDING, then STREAMING, before returning StreamingResponse (`backend/app/api/chat.py::chat_stream`, `backend/app/conversation_service.py::begin_streaming_turn`). This differs from JSON's guard-before-generation/preparation ordering and merits concurrency review.

`_encode_provider_stream_impl` emits start → metadata → textual deltas → done/error, increments sequence, captures usage even from textless chunks, applies stream timeout and finalizes persistence before terminal SSE. Terminal classification uses meaningful stripped content while preserving exact emitted text; finalization maps citations and releases the owning guard (`backend/app/api/chat.py::_encode_provider_stream_impl`, `backend/app/conversation_service.py::finalize_streaming_turn`). Cancellation wrapper attempts shielded finalization with RAG_STREAM_CANCELLED (`backend/app/api/chat.py::_encode_provider_stream`).

Realtime citation event emission is `NOT_IMPLEMENTED` in this encoder: sources appear in metadata, but verified citations are computed at persistence finalization; typed citation events exist in the schema (`backend/app/api/chat.py::_encode_provider_stream_impl` comment after metadata; `backend/app/sse_schema.py::SSECitationEvent`). No automatic stream resume/replay is implemented by `frontend/lib/chat/controller.ts::ChatController.stop`, `dispose`, `submit`.

`NOT_VERIFIED`: socket disconnect behavior, process-kill recovery, reverse-proxy buffering/timeouts and durable writes under cloud outages.

### Session/history → frontend rendering

`SOURCE_CONFIRMED`: route params → `SessionChat` validates UUID/config, fetches session, then fetches full paginated history before rendering `ChatPreview` (`frontend/app/chat/[sessionId]/page.tsx`, `frontend/components/chat/session-chat.tsx`). `loadMessageHistory` enforces session identity, page progress/count, uniqueness and sequence ordering; `historyMessageToViewMessage` restores attachments/citations/status but initializes sources=[] (`frontend/lib/sessions/history.ts`).

New chat creates a session on first accepted submit; stream start binds persistent request/message IDs; deltas accumulate; terminal history is fetched once and compared with local content/status/model/usage/error/attachments before marking verified (`frontend/lib/chat/controller.ts::ChatController.submit`, `acceptEvent`; `frontend/lib/chat/services.ts::createChatServices`). Live ordered sources are retained during reconciliation, while a fresh route load has none. URL navigation is controlled by `frontend/components/chat/chat-preview.tsx::ChatPreview` and `frontend/lib/chat/recovery.ts`.

`NOT_VERIFIED`: real browser race behavior, history pagination under concurrent changes and live session isolation. Test presence is cataloged below, not treated as a fresh pass.

### Attachment → message → preview

`SOURCE_CONFIRMED`: selected files become per-file UploadControllers and start uploading immediately; send is gated on indexed/activated results (and max 20) (`frontend/hooks/use-chat-attachments.ts::useChatAttachments`, `frontend/components/chat/chat-composer.tsx::ChatComposer`). Removing a composer attachment aborts the client wait, not the server document. Submitted payloads carry only document_id/version_id; backend resolves trusted file names and checks indexed version ownership/non-deletion (`frontend/lib/chat/controller.ts::submit`, `backend/app/attachments.py::resolve_attachments`, `resolve_version`).

User messages persist `MessageAttachment` and history returns it (`backend/app/conversation_service.py::answer_with_persistence`, `begin_streaming_turn`; `backend/app/api/sessions.py::_message_response`). `ChatMessage` → `MessageAttachmentChip` → resizable sheet → `DocumentPreview` → preview API for immutable version (`frontend/components/chat/chat-message.tsx:75–76`, `message-attachment.tsx`, `document-preview.tsx::RemotePreview`, `frontend/lib/api/documents.ts::getDocumentPreview`).

Text preview supports TXT/MD/Markdown remotely, capped at 256 KiB with explicit encoding handling; XLSX renders bounded tables. Local pre-upload preview uses TXT File data. PDF content preview is `NOT_IMPLEMENTED`: backend returns kind=unsupported and UI displays that state (`backend/app/attachments.py::preview_version`, `frontend/components/chat/document-preview.tsx::DocumentPreview`). XLSX formulas remain literal, macros are rejected and parser budgets apply (`backend/app/excel.py::read_workbook`, `workbook_preview`).

Attachment-scoped retrieval is `NOT_IMPLEMENTED`: references do not enter `prepare_rag_request` or change stored scope; the retrieval snapshot uses session scope (`backend/app/api/chat.py::chat`, `chat_stream`; `backend/app/rag/pipeline.py::prepare_rag_request`; `frontend/components/chat/message-attachment.tsx` explicitly describes this). Since upload adds a library document, an ALL_ACTIVE session can retrieve it, but attaching it does not guarantee exclusive retrieval from it.

### Citation → source → document preview

`SOURCE_CONFIRMED`: answer [n] → message-local ordered sources[n-1] with UUID/page eligibility → source drawer grouped by document/version/page (`frontend/lib/chat/source-mapper.ts::resolveCitationOrdinal`, `mapMessageSources`; `frontend/lib/chat/citation-panel.ts::buildCitationPanel`; `frontend/components/chat/citation-content.tsx::CitationMarker`, `CitationContent`). PDF display pages add one to loader page metadata; source IDs remain unchanged.

Citation → document content preview is `NOT_IMPLEMENTED` in `CitationContent`/`SourceGroups`: drawer shows source identity and an unavailable-preview message; it does not invoke DocumentPreview or getDocumentPreview. Attachment preview is a separate implemented path. Restored citation identities display with ordinal=null rather than inventing [n] mappings (`frontend/lib/chat/citation-panel.ts::buildCitationPanel`; `frontend/lib/sessions/history.ts::historyMessageToViewMessage`).

## 8. Existing Tests & Evaluation

`SOURCE_CONFIRMED` test existence and setup; all execution outcomes in this discovery are `NOT_VERIFIED`. No suites, builds, lint, browser tests or evaluation commands were run. Environment probe: python was unavailable on PATH, and the existing .venv/Scripts/python.exe launcher failed because its configured Python310 interpreter was missing; this does not establish any application test failure. This preserves read-only discovery and avoids application startup/index writes or provider/cloud work. Catalogs below enumerate files and declaration lines without claiming assertion-by-assertion review.

| Suite/tool | Coverage indicated by source and limits |
| --- | --- |
| Backend unittest | Lifecycle/storage/vector/retrieval; DTO and citation validation; history/budget/rewrite; session concurrency/isolation; chat persistence/SSE/metrics/terminal parity; XLSX/message attachments. See backend test catalog. Representative inspected tests: `backend/tests/test_rag_integration.py::test_selected_scope_rewrite_and_prompt_keep_separate_queries` uses fake retriever/rewriter; `backend/tests/test_cloud_connections.py::FakeMongoClient`, `FakeQdrantClient`; `backend/tests/test_stream_terminal_parity.py::test_whitespace_only_normal_finish_is_failed_empty_with_exact_content` mocks provider; `backend/tests/test_message_attachments_excel.py::test_real_multisheet_upload_indexes_and_retrieves_correct_row_and_metadata` uses deterministic embeddings/local adapters, not paid providers. |
| Frontend Node tests | API DTOs, SSE parsing, chat/session/document controllers and isolation, citations, upload/reconciliation/actions/attachments/previews. `frontend/package.json::scripts.test` runs tests/*.test.mjs; see catalog. Test names alone do not prove full user-flow coverage. |
| Offline contract | `frontend/tests/verify-api-contract.mjs:7–24`: exports backend OpenAPI/SSE schemas using root Windows .venv, blocks socket connections and avoids lifespan; compares frontend contracts. Existence is not a pass result. |
| Browser E2E | `frontend/playwright.config.ts`: Chromium, one worker, no retries, production server 3100, retained failure artifacts. `frontend/e2e/fixtures.mts::test` creates per-test loopback mock, reroutes configured 4011 requests and blocks unexpected origins. These fixtures validate UI/mock behavior, not real provider/cloud integration. |
| Mock/demo tooling | `frontend/scripts/qa-mock-api.mjs::createQaMockServer`, `qa-document-lifecycle.mjs::createDocumentLifecycle`, `demo-smoke.mjs`; `build-e2e.mjs` and `run-e2e.mjs` wrap browser build/run. |
| Single-turn evaluation | `backend/scripts/eval_cli.py::main`, `_index_corpus`, `_run_case`: derives separate *_eval collection, optionally embeds/reindexes corpus, runs `build_rag_chain` with live adapters and writes reports. --no-reindex still does query embedding/generation. |
| History evaluation | `backend/scripts/eval_history_cli.py::_evaluate`, `_run_mode`, `main`: compares modes through `prepare_rag_request_from_components`; `backend/evaluation/history_eval.py::score_run`, `summarize`. Retrieval-only mode still uses embedding retrieval and can invoke rewriting; it is not an offline/no-provider guarantee. |
| Metrics/data | `backend/evaluation/metrics.py::answer_fact_coverage`, `retrieval_metrics`, `faithfulness_ratio`; `backend/evaluation/history_eval.py::score_run`. These are heuristic metrics, not independent proof of factual grounding. Golden sets/corpus and stored JSON reports are cataloged below; results were not rerun or accepted as current quality measurements. |
| Smoke/migration/live tools | Catalog below. Do not infer safety from smoke/verify naming. `backend/scripts/controlled_live_e2e.py::ProviderBudget`, `validate_backend_target`, `run_live` explicitly guard provider budget and temporary namespace; `frontend/scripts/controlled-live-browser.mjs` drives live UI. Migration/index-init/reconciliation tools can mutate stores. None were executed. |

### Enumerated test and tooling catalog

The generated catalog below records each file and its first relevant declaration/entry line. It is a source-location index, not a runtime report.

#### Backend tests (32 files)

All entries: SOURCE_CONFIRMED presence; execution: NOT_VERIFIED. This catalog indexes declarations; individual assertions and script bodies were not exhaustively reviewed.

| Source | First declaration or entry |
| --- | --- |
| [backend/tests/test_chat_persistence.py](backend/tests/test_chat_persistence.py#L22) | Line 22: class FakeMessageRepository: |
| [backend/tests/test_chat_response_schema.py](backend/tests/test_chat_response_schema.py#L19) | Line 19: class ChatResponseSchemaTests(unittest.TestCase): |
| [backend/tests/test_chat_stream.py](backend/tests/test_chat_stream.py#L22) | Line 22: class ChatStreamApiTests(unittest.TestCase): |
| [backend/tests/test_citation_mapping.py](backend/tests/test_citation_mapping.py#L12) | Line 12: class CitationMappingTests(unittest.TestCase): |
| [backend/tests/test_cloud_connections.py](backend/tests/test_cloud_connections.py#L29) | Line 29: class FakeMongoClient: |
| [backend/tests/test_context_budget.py](backend/tests/test_context_budget.py#L56) | Line 56: class ContextBudgetTests(unittest.TestCase): |
| [backend/tests/test_controlled_live_guards.py](backend/tests/test_controlled_live_guards.py#L18) | Line 18: class ControlledLiveGuardTests(unittest.TestCase): |
| [backend/tests/test_conversation_concurrency.py](backend/tests/test_conversation_concurrency.py#L12) | Line 12: class AtomicGuardRepository: |
| [backend/tests/test_conversation_models.py](backend/tests/test_conversation_models.py#L26) | Line 26: class ConversationModelTests(unittest.TestCase): |
| [backend/tests/test_cors.py](backend/tests/test_cors.py#L17) | Line 17: class CorsTests(unittest.TestCase): |
| [backend/tests/test_document_models.py](backend/tests/test_document_models.py#L25) | Line 25: class DocumentModelTests(unittest.TestCase): |
| [backend/tests/test_documents_api.py](backend/tests/test_documents_api.py#L21) | Line 21: class FakeDocumentService: |
| [backend/tests/test_evaluation_metrics.py](backend/tests/test_evaluation_metrics.py#L8) | Line 8: class EvaluationMetricTests(unittest.TestCase): |
| [backend/tests/test_history.py](backend/tests/test_history.py#L18) | Line 18: class FakeHistoryRepository: |
| [backend/tests/test_history_evaluation.py](backend/tests/test_history_evaluation.py#L9) | Line 9: class HistoryEvaluationTests(unittest.TestCase): |
| [backend/tests/test_ingestion.py](backend/tests/test_ingestion.py#L30) | Line 30: class DeterministicEmbeddings(Embeddings): |
| [backend/tests/test_llm.py](backend/tests/test_llm.py#L9) | Line 9: class LLMFactoryTests(unittest.TestCase): |
| [backend/tests/test_m06_verification.py](backend/tests/test_m06_verification.py#L14) | Line 14: class M06VerificationTests(unittest.TestCase): |
| [backend/tests/test_message_attachments_excel.py](backend/tests/test_message_attachments_excel.py#L62) | Line 62: class KeywordEmbeddings(DeterministicEmbeddings): |
| [backend/tests/test_multi_session_isolation.py](backend/tests/test_multi_session_isolation.py#L26) | Line 26: class Cursor(list): |
| [backend/tests/test_query_rewriting.py](backend/tests/test_query_rewriting.py#L42) | Line 42: class FakeProvider: |
| [backend/tests/test_rag_integration.py](backend/tests/test_rag_integration.py#L29) | Line 29: class FakeRetriever: |
| [backend/tests/test_retriever.py](backend/tests/test_retriever.py#L13) | Line 13: class FakeEmbeddings(Embeddings): |
| [backend/tests/test_session_actions.py](backend/tests/test_session_actions.py#L16) | Line 16: class SessionCollection: |
| [backend/tests/test_sessions_api.py](backend/tests/test_sessions_api.py#L27) | Line 27: class FakeConversationService: |
| [backend/tests/test_sse_schema.py](backend/tests/test_sse_schema.py#L28) | Line 28: class SSESchemaTests(unittest.TestCase): |
| [backend/tests/test_storage.py](backend/tests/test_storage.py#L21) | Line 21: class FailingStream(io.BytesIO): |
| [backend/tests/test_stream_metrics.py](backend/tests/test_stream_metrics.py#L8) | Line 8: class FakeClock: |
| [backend/tests/test_stream_terminal_parity.py](backend/tests/test_stream_terminal_parity.py#L15) | Line 15: class StreamTerminalParityTests(unittest.TestCase): |
| [backend/tests/test_streaming_pipeline.py](backend/tests/test_streaming_pipeline.py#L16) | Line 16: class FakeStreamingModel: |
| [backend/tests/test_vector_index.py](backend/tests/test_vector_index.py#L18) | Line 18: class QdrantVectorIndexTests(unittest.TestCase): |
| [backend/tests/test_xlsx_loader.py](backend/tests/test_xlsx_loader.py#L14) | Line 14: class XlsxLoaderTests(unittest.TestCase): |

#### Frontend Node tests and contract (27 files)

All entries: SOURCE_CONFIRMED presence; execution: NOT_VERIFIED. This catalog indexes declarations; individual assertions and script bodies were not exhaustively reviewed.

| Source | First declaration or entry |
| --- | --- |
| [frontend/tests/api-client.test.mjs](frontend/tests/api-client.test.mjs#L33) | Line 33: test("2xx JSON retains status, headers, defaults and request JSON", async () => { |
| [frontend/tests/chat-actions.test.mjs](frontend/tests/chat-actions.test.mjs#L14) | Line 14: function load(relative) { |
| [frontend/tests/chat-attachments.test.mjs](frontend/tests/chat-attachments.test.mjs#L14) | Line 14: function harness(upload) { |
| [frontend/tests/chat-controller.test.mjs](frontend/tests/chat-controller.test.mjs#L7) | Line 7: function loadTypescriptModule(relativePath) { |
| [frontend/tests/chat-stream-client.test.mjs](frontend/tests/chat-stream-client.test.mjs#L14) | Line 14: function transpile(filename) { |
| [frontend/tests/chat-workspace.test.mjs](frontend/tests/chat-workspace.test.mjs#L16) | Line 16: function load(relative) { |
| [frontend/tests/citation-ui.test.mjs](frontend/tests/citation-ui.test.mjs#L14) | Line 14: function load(relative) { |
| [frontend/tests/document-actions.test.mjs](frontend/tests/document-actions.test.mjs#L12) | Line 12: function load(relative) { |
| [frontend/tests/document-lifecycle.test.mjs](frontend/tests/document-lifecycle.test.mjs#L39) | Line 39: function load(relative) { |
| [frontend/tests/document-reconciliation.test.mjs](frontend/tests/document-reconciliation.test.mjs#L8) | Line 8: function load(relative) { |
| [frontend/tests/document-upload.test.mjs](frontend/tests/document-upload.test.mjs#L14) | Line 14: function load(relative) { |
| [frontend/tests/documents.test.mjs](frontend/tests/documents.test.mjs#L12) | Line 12: function load(relative) { |
| [frontend/tests/error-health.test.mjs](frontend/tests/error-health.test.mjs#L12) | Line 12: function load(relative) { |
| [frontend/tests/functional-regression.test.mjs](frontend/tests/functional-regression.test.mjs#L10) | Line 10: function load(relative) { |
| [frontend/tests/message-attachments.test.mjs](frontend/tests/message-attachments.test.mjs#L13) | Line 13: function load(relative) { |
| [frontend/tests/multi-session-isolation.test.mjs](frontend/tests/multi-session-isolation.test.mjs#L25) | Line 25: function load(relative) { |
| [frontend/tests/multi-turn.test.mjs](frontend/tests/multi-turn.test.mjs#L10) | Line 10: function load(relative) { |
| [frontend/tests/qa-mock-api.test.mjs](frontend/tests/qa-mock-api.test.mjs#L10) | Line 10: function load(relative) { |
| [frontend/tests/session-actions.test.mjs](frontend/tests/session-actions.test.mjs#L8) | Line 8: function load(relative) { |
| [frontend/tests/session-navigation-ui.test.mjs](frontend/tests/session-navigation-ui.test.mjs#L14) | Line 14: function load(relative) { |
| [frontend/tests/session-navigation.test.mjs](frontend/tests/session-navigation.test.mjs#L17) | Line 17: function load(relative) { |
| [frontend/tests/sessions.test.mjs](frontend/tests/sessions.test.mjs#L7) | Line 7: function loadTypescriptModule(relativePath) { |
| [frontend/tests/source-mapper.test.mjs](frontend/tests/source-mapper.test.mjs#L22) | Line 22: test("sparse markers use metadata positions, not chunk_index or citation order", () => { |
| [frontend/tests/sse-parser.test.mjs](frontend/tests/sse-parser.test.mjs#L54) | Line 54: test("parses the backend LF transcript and preserves exact delta whitespace", () => { |
| [frontend/tests/text-preview.test.mjs](frontend/tests/text-preview.test.mjs#L12) | Line 12: test("preview preserves Vietnamese, line breaks and literal untrusted markup", async () => { |
| [frontend/tests/ui-polish.test.mjs](frontend/tests/ui-polish.test.mjs#L14) | Line 14: function load(relative) { |
| [frontend/tests/verify-api-contract.mjs](frontend/tests/verify-api-contract.mjs#L62) | Line 62: function typeOf(schema) { |

#### Browser scenarios (8 files)

All entries: SOURCE_CONFIRMED presence; execution: NOT_VERIFIED. This catalog indexes declarations; individual assertions and script bodies were not exhaustively reviewed.

| Source | First declaration or entry |
| --- | --- |
| [frontend/e2e/chat-actions.spec.mts](frontend/e2e/chat-actions.spec.mts#L12) | Line 12: test("composer reconciles sidebar before terminal; new tab is a snapshot, intentional submit gets409, terminal canonicalizes", async ({ |
| [frontend/e2e/chat-attachments.spec.mts](frontend/e2e/chat-attachments.spec.mts#L11) | Line 11: async function mockUpload(page: Page) { |
| [frontend/e2e/document-actions.spec.mts](frontend/e2e/document-actions.spec.mts#L10) | Line 10: async function openDocument(page: Page) { |
| [frontend/e2e/functional-qa.spec.mts](frontend/e2e/functional-qa.spec.mts#L9) | Line 9: test(pre-header chat ${status} is safe, unlocks composer and never auto-replays, async ({ page }) => { |
| [frontend/e2e/message-attachments.spec.mts](frontend/e2e/message-attachments.spec.mts#L31) | Line 31: test("phuongtien.txt persists on its user message and previews after refresh/session switching", async ({ page, qa }) => { |
| [frontend/e2e/session-actions.spec.mts](frontend/e2e/session-actions.spec.mts#L8) | Line 8: test("desktop Space/arrows/Escape and rename Tab trap, validation, trim and focus return", async ({ page, qa }) => { |
| [frontend/e2e/welcome-preview-resize.spec.mts](frontend/e2e/welcome-preview-resize.spec.mts#L13) | Line 13: async function openPreview(page: Page) { |
| [frontend/e2e/workspace.spec.mts](frontend/e2e/workspace.spec.mts#L3) | Line 3: test("session keyboard rename, cancel, current deletion and focus fallback", async ({ page, qa }) => { |

#### Backend scripts (34 files)

All entries: SOURCE_CONFIRMED presence; execution: NOT_VERIFIED. This catalog indexes declarations; individual assertions and script bodies were not exhaustively reviewed.

| Source | First declaration or entry |
| --- | --- |
| [backend/scripts/check_cloud_connections.py](backend/scripts/check_cloud_connections.py#L19) | Line 19: def main() -> int: |
| [backend/scripts/controlled_live_e2e.py](backend/scripts/controlled_live_e2e.py#L30) | Line 30: class ProviderBudget: |
| [backend/scripts/eval_cli.py](backend/scripts/eval_cli.py#L57) | Line 57: class TokenUsageCallback(BaseCallbackHandler): |
| [backend/scripts/eval_history_cli.py](backend/scripts/eval_history_cli.py#L212) | Line 212: def main() -> None: |
| [backend/scripts/init_mongodb_indexes.py](backend/scripts/init_mongodb_indexes.py#L20) | Line 20: def main() -> int: |
| [backend/scripts/migrate_demo_corpus.py](backend/scripts/migrate_demo_corpus.py#L63) | Line 63: def main() -> int: |
| [backend/scripts/reconcile_ingestion.py](backend/scripts/reconcile_ingestion.py#L15) | Line 15: def main() -> int: |
| [backend/scripts/smoke_citation_mapping.py](backend/scripts/smoke_citation_mapping.py#L21) | Line 21: def main() -> int: |
| [backend/scripts/smoke_context_budget.py](backend/scripts/smoke_context_budget.py#L43) | Line 43: def main() -> int: |
| [backend/scripts/smoke_conversation_models.py](backend/scripts/smoke_conversation_models.py#L25) | Line 25: def main() -> int: |
| [backend/scripts/smoke_document_api.py](backend/scripts/smoke_document_api.py#L29) | Line 29: def main() -> int: |
| [backend/scripts/smoke_history_loader.py](backend/scripts/smoke_history_loader.py#L55) | Line 55: def main() -> int: |
| [backend/scripts/smoke_ingestion.py](backend/scripts/smoke_ingestion.py#L31) | Line 31: def main() -> int: |
| [backend/scripts/smoke_message_persistence.py](backend/scripts/smoke_message_persistence.py#L24) | Line 24: def main() -> int: |
| [backend/scripts/smoke_provider_stream.py](backend/scripts/smoke_provider_stream.py#L38) | Line 38: def main() -> int: |
| [backend/scripts/smoke_qdrant_ingestion.py](backend/scripts/smoke_qdrant_ingestion.py#L21) | Line 21: def main() -> int: |
| [backend/scripts/smoke_query_rewriting.py](backend/scripts/smoke_query_rewriting.py#L20) | Line 20: class Provider: |
| [backend/scripts/smoke_rag_integration.py](backend/scripts/smoke_rag_integration.py#L33) | Line 33: def main() -> int: |
| [backend/scripts/smoke_response_contract.py](backend/scripts/smoke_response_contract.py#L70) | Line 70: def main() -> int: |
| [backend/scripts/smoke_session_api.py](backend/scripts/smoke_session_api.py#L29) | Line 29: def main() -> int: |
| [backend/scripts/smoke_session_concurrency.py](backend/scripts/smoke_session_concurrency.py#L33) | Line 33: def main() -> int: |
| [backend/scripts/smoke_sse_schema.py](backend/scripts/smoke_sse_schema.py#L31) | Line 31: def main() -> int: |
| [backend/scripts/smoke_stream_endpoint.py](backend/scripts/smoke_stream_endpoint.py#L34) | Line 34: def main() -> int: |
| [backend/scripts/smoke_stream_errors.py](backend/scripts/smoke_stream_errors.py#L43) | Line 43: def main() -> int: |
| [backend/scripts/smoke_stream_lifecycle.py](backend/scripts/smoke_stream_lifecycle.py#L40) | Line 40: def main() -> int: |
| [backend/scripts/smoke_stream_metrics.py](backend/scripts/smoke_stream_metrics.py#L53) | Line 53: def main() -> int: |
| [backend/scripts/smoke_vector_adapter.py](backend/scripts/smoke_vector_adapter.py#L26) | Line 26: def main() -> int: |
| [backend/scripts/try_step.py](backend/scripts/try_step.py#L91) | Line 91: def main() -> None: |
| [backend/scripts/verify_cutover.py](backend/scripts/verify_cutover.py#L75) | Line 75: def main() -> int: |
| [backend/scripts/verify_frontend_functional_qa.py](backend/scripts/verify_frontend_functional_qa.py#L1) | Line 1: File presence indexed |
| [backend/scripts/verify_m06.py](backend/scripts/verify_m06.py#L48) | Line 48: class RecordingRewriter: |
| [backend/scripts/verify_multi_session_isolation.py](backend/scripts/verify_multi_session_isolation.py#L1) | Line 1: File presence indexed |
| [backend/scripts/verify_phase1.py](backend/scripts/verify_phase1.py#L37) | Line 37: class FailingEmbeddings(Embeddings): |
| [backend/scripts/verify_phase2.py](backend/scripts/verify_phase2.py#L49) | Line 49: def main() -> int: |

#### Frontend scripts (8 files)

All entries: SOURCE_CONFIRMED presence; execution: NOT_VERIFIED. This catalog indexes declarations; individual assertions and script bodies were not exhaustively reviewed.

| Source | First declaration or entry |
| --- | --- |
| [frontend/scripts/build-e2e.mjs](frontend/scripts/build-e2e.mjs#L1) | Line 1: File presence indexed |
| [frontend/scripts/controlled-live-browser.mjs](frontend/scripts/controlled-live-browser.mjs#L1) | Line 1: File presence indexed |
| [frontend/scripts/demo-smoke.mjs](frontend/scripts/demo-smoke.mjs#L17) | Line 17: async function requireFreePort(port) { |
| [frontend/scripts/qa-document-lifecycle.mjs](frontend/scripts/qa-document-lifecycle.mjs#L5) | Line 5: export function createDocumentLifecycle(fixtures, delayMs) { |
| [frontend/scripts/qa-mock-api.mjs](frontend/scripts/qa-mock-api.mjs#L24) | Line 24: function message(session_id, sequence, role, content, request_id = randomUUID()) { |
| [frontend/scripts/run-e2e.mjs](frontend/scripts/run-e2e.mjs#L1) | Line 1: File presence indexed |
| [frontend/scripts/verify-local-integration.mjs](frontend/scripts/verify-local-integration.mjs#L1) | Line 1: File presence indexed |
| [frontend/scripts/verify-production-delivery.mjs](frontend/scripts/verify-production-delivery.mjs#L1) | Line 1: File presence indexed |

#### Evaluation source, inputs and stored artifacts (15 files)

All entries: SOURCE_CONFIRMED presence; execution: NOT_VERIFIED. This catalog indexes declarations; individual assertions and script bodies were not exhaustively reviewed.

| Source | First declaration or entry |
| --- | --- |
| [backend/evaluation/corpus/chunking.md](backend/evaluation/corpus/chunking.md#L1) | Line 1: File presence indexed |
| [backend/evaluation/corpus/llm-embedding.md](backend/evaluation/corpus/llm-embedding.md#L1) | Line 1: File presence indexed |
| [backend/evaluation/corpus/qdrant.md](backend/evaluation/corpus/qdrant.md#L1) | Line 1: File presence indexed |
| [backend/evaluation/golden_set.json](backend/evaluation/golden_set.json#L1) | Line 1: File presence indexed |
| [backend/evaluation/history_eval.py](backend/evaluation/history_eval.py#L1) | Line 1: File presence indexed |
| [backend/evaluation/history_golden_set.json](backend/evaluation/history_golden_set.json#L1) | Line 1: File presence indexed |
| [backend/evaluation/metrics.py](backend/evaluation/metrics.py#L1) | Line 1: File presence indexed |
| [backend/evaluation/results/eval_20260924_164839.json](backend/evaluation/results/eval_20260924_164839.json#L1) | Line 1: File presence indexed |
| [backend/evaluation/results/eval_20260924_164925.json](backend/evaluation/results/eval_20260924_164925.json#L1) | Line 1: File presence indexed |
| [backend/evaluation/results/eval_20261011_150123.json](backend/evaluation/results/eval_20261011_150123.json#L1) | Line 1: File presence indexed |
| [backend/evaluation/results/m03_regression.json](backend/evaluation/results/m03_regression.json#L1) | Line 1: File presence indexed |
| [backend/evaluation/results/m04_regression.json](backend/evaluation/results/m04_regression.json#L1) | Line 1: File presence indexed |
| [backend/evaluation/results/m05_qdrant_eval.json](backend/evaluation/results/m05_qdrant_eval.json#L1) | Line 1: File presence indexed |
| [backend/evaluation/results/p5_history_eval.json](backend/evaluation/results/p5_history_eval.json#L1) | Line 1: File presence indexed |
| [backend/evaluation/results/p5_history_retrieval.json](backend/evaluation/results/p5_history_retrieval.json#L1) | Line 1: File presence indexed |


## 9. Preliminary README Discrepancies

| Status | Documentation claim/omission | Source comparison |
| --- | --- | --- |
| SOURCE_CONFIRMED | Root `README.md:592` says no frontend, despite linking frontend docs at :8. | Implemented Next pages and workspace UI (`frontend/app/{page,layout}.tsx`, `frontend/app/chat/page.tsx`, `frontend/app/chat/[sessionId]/page.tsx`, `frontend/app/documents/page.tsx`). Root limitation is stale. |
| SOURCE_CONFIRMED | Root backend run instructions change to backend/ (`README.md:121–122`); frontend instructions correctly require root CWD (`frontend/README.md:58`). | `backend/app/config.py::Settings.documents_dir` is relative; `backend/app/storage.py::LocalFileStorage.__init__` resolves storage root against CWD. This creates a raw-storage location ambiguity, even though config ENV_FILE itself is absolute. |
| SOURCE_CONFIRMED | Root API table (`README.md:136–155`) omits version preview. Both READMEs lack a description of message attachment DTOs/XLSX workflow. | Preview route: `backend/app/api/documents.py::document_preview`; request: `backend/app/schemas.py::ChatRequest`; XLSX extension: `backend/app/rag/loader.py::SUPPORTED_EXTENSIONS`; attachment UI: `frontend/components/chat/message-attachment.tsx`, `frontend/hooks/use-chat-attachments.ts`. |
| SOURCE_CONFIRMED | Root `README.md:247` calls sources all retrieved candidates. | `backend/app/rag/pipeline.py::prepare_rag_request_from_components` returns only documents selected by context budget (`documents[:len(budget.chunks)]`); candidates excluded by budget are absent. Clarify retrieval candidates versus prompt-selected sources. |
| SOURCE_CONFIRMED | Frontend `README.md:114` describes missing history ordinal metadata and no fake/PDF links. | Still matches `frontend/lib/sessions/history.ts::historyMessageToViewMessage`, `frontend/lib/chat/citation-panel.ts::buildCitationPanel`. But broad preview wording must distinguish implemented attachment text/Excel preview from absent citation/PDF preview (`frontend/components/chat/document-preview.tsx`, `citation-content.tsx`). |
| SOURCE_CONFIRMED | Root `README.md:611–617` describes selected-scope internal support/no public scope setter and absent live citation events. | Matches `backend/app/rag/pipeline.py::_resolve_active_version_ids`, `backend/app/conversation_schemas.py::CreateSessionRequest`, registered session handlers, `backend/app/api/chat.py::_encode_provider_stream_impl`. These are current limits, not discrepancies. |
| SOURCE_CONFIRMED | Frontend `README.md:3`, :75–77 describes routes/direct API and exact CORS. | Matches page files, `frontend/lib/api/client.ts::createApiClient`, `frontend/lib/api/chat.ts::createChatStreamClient`, `backend/app/main.py:42–48`. |
| DOCUMENTED_ONLY | Root restart/live-provider success (`README.md:34–35`, :592–594); frontend tested environment/previous demo and advisory counts (`frontend/README.md:7`, :114). | No fresh runtime verification; manifests support declared versions only (`frontend/package.json`, `backend/requirements.txt`). Historical QA claims were not revalidated. |
| NOT_VERIFIED | Root quality/evaluation success and production readiness implications (`README.md:632–635`; frontend deployment assumptions at `frontend/README.md:99`). | Evaluation scripts and reports exist, but provider availability, correctness, current metrics, hosting/proxy behavior and readiness remain untested in Phase 0A. |

Neither README was edited. Documentation alignment is deferred until owner approval.

## 10. Recommended Phase 0B Audit Targets

These priorities are discovery recommendations. Each concern is `NOT_VERIFIED` as a defect; cited implementation is `SOURCE_CONFIRMED`. No Phase 0B audit was performed.

| Priority | Target and evidence | Deeper audit question |
| --- | --- | --- |
| 1 | Streaming terminal durability/cancellation: `backend/app/api/chat.py::_encode_provider_stream_impl`, `_encode_provider_stream`; `backend/app/conversation_service.py::finalize_streaming_turn`; `backend/tests/test_stream_terminal_parity.py`. | Under repeated cancellation and write/release failures, do wire content/status, durable state and guard ownership converge? Check finalized flag on persistence exceptions, shielded task lifetime and failures before iterator/provider handling. |
| 1 | Guard timing/concurrency: `backend/app/api/chat.py::chat_stream`; `backend/app/conversation_repository.py::begin_generation`, `release_generation`, `create_message_pair`; `backend/app/conversation_service.py::answer_with_persistence`. | SSE preparation precedes guard acquisition, unlike JSON. Can preparation consume provider budget or use stale history before a 409? Audit crash recovery, sequence gaps, partial pair writes and stale guards; no lease/reaper appears in these lifecycle methods. |
| 1 | Document lifecycle consistency: `backend/app/ingestion.py::_process`, `_fail_before_activation`, `reconcile_processing`; `backend/app/document_repository.py::complete_and_activate`, `next_version_number`, `unpublish`; `backend/app/document_service.py::delete`. | Verify activation/delete/version races and compensations across local storage, MongoDB and Qdrant; count-only reconciliation and cleanup retry behavior after interrupted writes. |
| 1 | Retrieval scope/provenance: `backend/app/rag/pipeline.py::_resolve_active_version_ids`, `prepare_rag_request_from_components`; `backend/app/rag/retriever.py::_get_relevant_documents`; `backend/app/qdrant_ingestion.py::_to_qdrant_filter`; `backend/app/attachments.py::resolve_attachments`. | Verify snapshot boundaries during deletion/version switches, selected-document isolation, attachment expectations and point payload/document consistency. Validated attachment references do not narrow retrieval. |
| 2 | Preview/upload resource limits: `backend/app/api/documents.py::_read_upload`; `backend/app/excel.py::read_workbook`, `workbook_documents`, `workbook_preview`; `backend/app/attachments.py::preview_version`; `backend/app/storage.py::LocalFileStorage._resolve`. | Review non-XLSX unbounded reads, parsing/embedding memory, ZIP/XML limits and bounded preview allocations; immutable-version/deleted-document access semantics and text encoding differences. |
| 2 | Citation parity and missing preview connection: `backend/app/citation_mapping.py::map_verified_citations`; `frontend/lib/chat/source-mapper.ts::resolveCitationOrdinal`; `frontend/lib/chat/citation-panel.ts::buildCitationPanel`; `frontend/components/chat/citation-content.tsx::CitationContent`. | Check backend/frontend eligibility and Markdown-marker parity, persisted loss of ordinals/sheet-row identity, and distinguish drawer identity display from document content access. No preview integration should be assumed. |
| 2 | Frontend stream/history/navigation: `frontend/lib/chat/controller.ts::ChatController`; `frontend/lib/api/chat.ts::createChatStreamClient`; `frontend/lib/sse/parser.ts::SSEParser`; `frontend/lib/sessions/history.ts::loadMessageHistory`; `frontend/components/chat/chat-preview.tsx::ChatPreview`. | Audit abort/late callbacks, terminal verification, pagination during changes and preservation of unsent drafts/new attachments; test mocks may differ from actual wire/write timing. |
| 2 | Prompt budget/rewrite correctness: `backend/app/context_budget.py::ContextBudgetBuilder`; `backend/app/query_rewriting.py::QueryRewriter`; `backend/app/rag/prompt.py::SYSTEM_INSTRUCTION`; `backend/app/rag/pipeline.py::prepare_rag_request_from_components`. | Check multilingual approximate token limits, truncation/ordinal consistency, rewrite lexical guards, prompt-injection handling and unbounded history-read cost before budget selection. |
| 2 | Evaluation representativeness and operational safety: `backend/scripts/eval_cli.py::main`; `backend/scripts/eval_history_cli.py::_evaluate`; `backend/evaluation/metrics.py`; `backend/scripts/controlled_live_e2e.py::run_live`; `frontend/e2e/fixtures.mts`. | Separate old-chain and HTTP-pipeline coverage, mock tests from live evidence, heuristic metrics from human grounding review; ensure any future live run has explicit budget/namespace authorization. |

Completion boundary: major routes, modules, storage responsibilities and all six requested flows were traced with source references; both READMEs were compared; tests/scripts were inventoried. Runtime, provider, cloud, browser and production behavior remain `NOT_VERIFIED`. Phase 0A ends here. Phase 0B and README changes require owner approval.
