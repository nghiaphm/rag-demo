# RAG Workspace — Implementation Change Log

Tài liệu này lưu lại toàn bộ lịch sử thay đổi, quyết định kỹ thuật, các file được thêm/chỉnh sửa và kết quả kiểm thử qua từng Phase nâng cấp để phục vụ review và đối chiếu.

---

## Baseline (Pre-Phase 1) — Trạng thái trước khi bắt đầu nâng cấp
- **Thời điểm**: 2026-11-15 (Nhánh `refactor/architecture`, commit `6b26dd7`)
- **Kiến trúc hiện hữu**:
  - Backend FastAPI **Modular Monolith** theo **Ports & Adapters (Hexagonal Architecture)** với AST dependency rules (`tests/architecture/test_dependency_rules.py`).
  - **Advanced RAG** đã hoàn thành:
    - Post-retrieval Reranker (`backend/app/rag/reranker.py` — FlashRank ONNX, Cohere, PassThrough).
    - Hybrid Search Dense + BM25 Keyword với Reciprocal Rank Fusion (`backend/app/infrastructure/qdrant_vector_index.py`).
    - Parent-Child Hierarchical Chunking (`backend/app/rag/splitter.py`, `backend/app/rag/retriever.py`).
    - Multi-Query Expansion (`backend/app/chat/multi_query.py`, `backend/app/chat/pipeline.py`).
  - **Tool Use**: Groq Selector (`tool_choice="auto"`) + `ToolExecutor` (`count_documents`, `list_documents`) trong `backend/app/tool_use/` và `backend/app/documents/tool_handlers.py`.
  - **Frontend**: Next.js 16 (App Router) + React 19 + Tailwind CSS v4 + SSE streaming + Mock API server.
  - **Documentation**: Đã chuẩn hóa 3 file `README.md` (`README.md`, `backend/README.md`, `frontend/README.md`) bằng tiếng Anh.
- **Trạng thái kiểm thử Baseline**:
  - Backend: 251 unit tests PASS + Architecture AST tests PASS.
  - Frontend: 210 Node unit tests PASS + `typecheck` PASS + `lint` PASS.

---

## Phase 1 – Evaluation & Observability
> **Trạng thái**: Hoàn thành  
> **Phạm vi**: `RAGAS` · `Langfuse` · `Evaluation Dataset` · `Docker Compose` (+ Redis)

### Thay đổi đã thực hiện
- **RAGAS Evaluation & Baseline Runner**:
  - Xây dựng module tính 4 chỉ số RAGAS (`Context Precision`, `Context Recall`, `Faithfulness`, `Answer Relevancy`) hỗ trợ cả chế độ deterministic offline và hook `llm_judge`, kèm hàm tính `compute_latency_percentiles` (`p50`, `p95`, `mean`, `ttft_p50`, `ttft_p95`).
  - Tạo CLI `baseline_eval.py` chạy đánh giá trên `golden_set.json` (9 cases) + `corpus/`, đo latency và token usage, xuất báo cáo JSON & Markdown vào `backend/evaluation/results/`.
- **Observability (Ports & Adapters)**:
  - Định nghĩa `Tracer`, `TraceContext`, `SpanContext` và fallback `NoOpTracer` tại `backend/app/shared/observability.py` (không phụ thuộc SDK bên ngoài).
  - Triển khai `LangfuseTracer` (lazy import `langfuse`, safe error swallowing) và `get_tracer()` tại `backend/app/infrastructure/observability.py`.
  - Bổ sung cấu hình `langfuse_enabled`, `langfuse_public_key`, `langfuse_secret_key`, `langfuse_host` vào `config.py` và `.env.example`.
  - Gắn trace spans cho `query_rewrite`, `multi_query`, `retrieval`, `rerank`, `context_budget` trong `chat/pipeline.py` và `chat_turn` / `llm_generation` trong `chat/orchestrator.py`, inject từ `app.state.tracer` tại `main.py` và `api/routes/chat.py`.
- **Containerization**:
  - Tạo `backend/Dockerfile`, `frontend/Dockerfile` và `docker-compose.yml` (gồm `backend`, `frontend`, `redis:7-alpine`, và profile `local-infra` cho `qdrant` & `mongo`).

### Files thêm mới / chỉnh sửa
- **Thêm mới**:
  - `backend/app/shared/observability.py`
  - `backend/app/infrastructure/observability.py`
  - `backend/evaluation/scoring/ragas_metrics.py`
  - `backend/evaluation/runner/baseline_eval.py`
  - `backend/evaluation/results/phase1_baseline.json`
  - `backend/evaluation/results/phase1_baseline.md`
  - `backend/tests/unit/test_observability.py`
  - `backend/tests/unit/test_ragas_metrics.py`
  - `backend/Dockerfile`
  - `frontend/Dockerfile`
  - `docker-compose.yml`
- **Chỉnh sửa**:
  - `backend/app/shared/config.py`
  - `.env.example`
  - `backend/app/main.py`
  - `backend/app/chat/pipeline.py`
  - `backend/app/chat/orchestrator.py`
  - `backend/app/api/routes/chat.py`

### Kết quả kiểm thử & Baseline Metrics
- **Architecture AST tests**: `9/9 PASS` (`tests/architecture`).
- **Backend Unit tests**: `258/258 PASS` (`tests/unit`, gồm `test_observability.py` & `test_ragas_metrics.py`).
- **Backend Integration tests**: `153/153 PASS` (`tests/integration`).
- **Docker Compose**: `docker compose config --quiet` exited `0` (hợp lệ).
- **Offline Baseline (`golden_set.json`, 9 cases)**:
  - `Context Precision`: `1.0000`
  - `Context Recall`: `0.7778`
  - `Faithfulness`: `0.7778`
  - `Answer Relevancy`: `0.7722`
  - `Overall Score`: `0.8319`

---

## Phase 2 – Self-corrective Retrieval
> **Trạng thái**: Hoàn thành  
> **Phạm vi**: `Retrieval Grader` · `Fallback` · `Query Correction` · `Evidence Evaluation`

### Thay đổi đã thực hiện
- **Self-corrective Retrieval (`backend/app/chat/corrective.py`)**:
  - `RetrievalGrader`: Đánh giá độ liên quan (`RELEVANT` / `AMBIGUOUS` / `IRRELEVANT`) của chunks sau rerank (hỗ trợ cả LLM JSON grader có timeout fallback lẫn deterministic lexical grader offline).
  - `QueryCorrector`: Viết lại câu truy vấn khi kết quả retrieval không đạt, đảm bảo không lặp lại các query đã thử trong `tried_queries`.
  - `CorrectiveRagRunner`: Điều phối vòng lặp grade $\rightarrow$ correct $\rightarrow$ re-retrieve trong giới hạn `corrective_max_retries` và `deadline`, phát Langfuse spans (`retrieval_grade`, `query_correction`, `retrieval_grade_retry`, `web_search_fallback`) và `on_status` callback.
  - `EvidenceEvaluator`: Kiểm tra post-generation groundedness giữa câu trả lời và chunks.
- **Fallback Strategy & Web Search Port**:
  - Định nghĩa port `WebSearchProvider` + `NoOpWebSearchProvider` tại `backend/app/rag/web_search.py` và adapter `TavilyWebSearchProvider` tại `backend/app/infrastructure/web_search.py` (bật qua `WEB_SEARCH_FALLBACK_ENABLED`).
  - Khi hết retry và không bật web fallback, trả về strict grounded empty context để tránh hallucination.
- **Pipeline & SSE Status Extension**:
  - Tích hợp `CorrectiveRagRunner` vào `prepare_rag_request_from_components` trong `backend/app/chat/pipeline.py` (bật qua `CORRECTIVE_RAG_ENABLED`).
  - Thêm `ChatStatusEvent` (`chat/events.py`), `SSEStatusEvent` (`api/streaming/sse_schema.py`), và `status_frame` (`api/streaming/event_adapter.py`) hoàn toàn tương thích ngược.

### Files thêm mới / chỉnh sửa
- **Thêm mới**:
  - `backend/app/chat/corrective.py`
  - `backend/app/rag/web_search.py`
  - `backend/app/infrastructure/web_search.py`
  - `backend/tests/unit/test_corrective_rag.py`
- **Chỉnh sửa**:
  - `backend/app/shared/config.py`
  - `.env.example`
  - `backend/app/chat/pipeline.py`
  - `backend/app/chat/events.py`
  - `backend/app/api/streaming/sse_schema.py`
  - `backend/app/api/streaming/event_adapter.py`

### Kết quả kiểm thử
- **Architecture AST tests**: `9/9 PASS` (`tests/architecture`).
- **Backend Unit tests**: `269/269 PASS` (`tests/unit`, gồm 11 tests mới trong `test_corrective_rag.py`).
- **Backend Integration tests**: `153/153 PASS` (`tests/integration`).

---

## Phase 3 – Agentic Orchestration
> **Trạng thái**: Hoàn thành  
> **Phạm vi**: `Single Agent` · `Tool Calling` · `Planning` · `Stateful Workflow` · `Iterative Retrieval`

### Thay đổi đã thực hiện
- **Agent Tool Registry & `rag_search`**:
  - Mở rộng `backend/app/tool_use/contracts.py` với `rag_search` (`RagSearchArguments`) trong `ToolName`, `ALLOWED_TOOL_NAMES` và `validate_arguments`.
  - Tạo `backend/app/chat/agent_tools.py` cung cấp `rag_search_tool_definition()`, `query_excel_table_tool_definition()`, `agent_tool_schemas()`, synchronous `create_rag_search_handler()` và `create_query_excel_handler()`.
  - Tạo `backend/app/documents/excel/query.py` (`query_workbook_bytes`) hỗ trợ lọc theo cột và tổng hợp (`rows`, `count`, `sum`, `avg`, `min`, `max`) trên file `.xlsx` qua `read_workbook`.
- **Stateful Iterative Agent Loop**:
  - Tạo `backend/app/chat/agent.py` với `AgentState` (`messages`, `step_count`, `max_steps`, `collected_sources`, `tool_history`, `deadline`) và `AgenticRunner` thực thi vòng lặp **Plan $\rightarrow$ Tool Execution $\rightarrow$ Observe $\rightarrow$ Re-plan / Final Answer** (giới hạn `max_agent_steps`, tổng hợp cuối khi chạm trần bước, ghi trace spans & usage ledger).
  - Nâng cấp `backend/app/chat/orchestrator.py` hỗ trợ `AGENTIC_MODE_ENABLED` và `MAX_AGENT_STEPS` (bảo toàn 100% hành vi legacy 1-round khi tắt cờ).
  - Bổ sung `agentic_mode_enabled` và `max_agent_steps` vào `config.py` và `.env.example`.

### Files thêm mới / chỉnh sửa
- **Thêm mới**:
  - `backend/app/chat/agent.py`
  - `backend/app/chat/agent_tools.py`
  - `backend/app/documents/excel/query.py`
  - `backend/tests/unit/test_agentic_orchestrator.py`
  - `backend/tests/unit/test_query_excel_table.py`
- **Chỉnh sửa**:
  - `backend/app/shared/config.py`
  - `.env.example`
  - `backend/app/tool_use/contracts.py`
  - `backend/app/chat/orchestrator.py`

### Kết quả kiểm thử
- **Architecture AST tests**: `9/9 PASS` (`tests/architecture`).
- **Backend Unit tests**: `276/276 PASS` (`tests/unit`, gồm `test_agentic_orchestrator.py` & `test_query_excel_table.py`).
- **Backend Integration tests**: `153/153 PASS` (`tests/integration`).

---

## Phase 4 – Performance & Security
> **Trạng thái**: Hoàn thành  
> **Phạm vi**: `Semantic Cache` · `Auth/RBAC` · `Access-aware Retrieval` · `Bounded Execution`

### Thay đổi đã thực hiện
- **Authentication & RBAC (`auth_enabled` flag)**: Triển khai `UserRole`, `UserContext`, `UserRecord`, pure-stdlib PBKDF2 password hashing, HS256 JWT access/refresh token, endpoint `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/me`, và FastAPI dependencies `get_current_user`, `require_roles`. Gắn `owner_id` và `allowed_roles` vào `DocumentRecord`, `SessionRecord`, `VectorRecord`.
- **Access-aware Retrieval & IDOR Protection**: Mở rộng `VectorFilter` và `QdrantVectorIndex._to_qdrant_filter` để lọc theo `owner_id` / `allowed_roles` ở mức Qdrant query; bảo vệ `/documents`, `/sessions`, `/chat` khỏi truy cập chéo (IDOR).
- **RBAC-aware Semantic Cache**: Định nghĩa port `SemanticCache` và adapter `RedisSemanticCache` (hỗ trợ in-memory fallback), phân vùng theo `permission_scope` và `active_version_snapshot` để chống rò rỉ dữ liệu khác quyền; tự động `invalidate_all()` khi upload, update, re-index hoặc xóa tài liệu.
- **Bounded Execution Hardening**: Bổ sung `max_tokens_per_turn` vào `ContextBudgetConfig` và `RateLimiter` (`RedisRateLimiter`) cho `/chat` và `/chat/stream` (gated bởi `rate_limit_enabled`).

### Files thêm mới / chỉnh sửa
- Thêm mới: `backend/app/shared/auth.py`, `backend/app/shared/cache.py`, `backend/app/infrastructure/semantic_cache.py`, `backend/app/api/dependencies/auth.py`, `backend/app/api/routes/auth.py`, `backend/tests/unit/test_rbac_and_cache.py`.
- Chỉnh sửa: `backend/app/shared/config.py`, `.env.example`, `backend/app/documents/models.py`, `backend/app/conversations/models.py`, `backend/app/rag/vector_index.py`, `backend/app/infrastructure/qdrant_vector_index.py`, `backend/app/chat/context_budget.py`, `backend/app/api/routes/documents.py`, `backend/app/api/routes/sessions.py`, `backend/app/api/routes/chat.py`, `backend/app/main.py`.

### Kết quả kiểm thử
- `tests/architecture`: **9/9 PASS**
- `tests/unit`: **283/283 PASS** (bao gồm `test_rbac_and_cache.py`)
- `tests/integration`: **153/153 PASS**

---

## Phase 5 – Production Workflow
> **Trạng thái**: Đang thực hiện (Hoàn thành 5.1 Async Ingestion Worker & 5.2 Document Scope Selector)  
> **Phạm vi**: `ARQ Worker` · `Redis` · `Document Scope Selector` · `PDF Viewer` · `Deployment`

### Thay đổi đã thực hiện
- **5.1 Async Ingestion Worker (Redis + ARQ)**:
  - Thêm `redis>=5.0.0,<6.0.0` và `arq>=0.26.0` vào `backend/requirements.txt`; bổ sung cờ `ASYNC_INGESTION_ENABLED=false` vào `backend/app/shared/config.py` và `.env.example`.
  - Định nghĩa port `IngestionQueue` / `IngestionQueueError` (`backend/app/documents/ports.py`), thêm `get_job` (`backend/app/documents/repository.py`), tách `_prepare_upload` + bổ sung `prepare_ingest` / `process_version` (`backend/app/documents/ingestion.py`) và `prepare_update` / `mark_enqueue_failed` (`backend/app/documents/service.py`).
  - Triển khai `ArqIngestionQueue`, `NoOpIngestionQueue`, `get_ingestion_queue` (`backend/app/infrastructure/ingestion_queue.py`) và ARQ worker `process_ingestion_job` / `WorkerSettings` (`backend/app/workers/ingestion_worker.py`) tự động `invalidate_all()` semantic cache sau khi index xong.
  - Cập nhật `POST /documents/upload` và `PUT /documents/{document_id}` trả HTTP `202 Accepted` kèm `job_id` khi `async_ingestion_enabled=True` (`backend/app/api/routes/documents.py`, wiring queue trong `backend/app/main.py`).
  - Cập nhật Frontend `/documents` chấp nhận HTTP `202` (`frontend/lib/api/documents.ts`), hiển thị thông báo job hàng đợi (`frontend/components/documents/document-upload.tsx`), và thêm silent background polling `DocumentsController.refresh()` + `hasPendingIngestion` (`frontend/lib/documents/controller.ts`, `frontend/hooks/use-documents.ts`, `frontend/components/documents/documents-preview.tsx`).
- **5.2 Document Scope Selector (Backend API + Frontend UI)**:
  - Thêm `UpdateSessionScopeRequest` (`backend/app/api/schemas/conversations.py`), `MongoConversationRepository.update_scope` (`backend/app/conversations/repository.py` — atomic check `deleted_at=None` & `active_generation_id=None`), `ConversationService.update_scope` (`backend/app/conversations/service.py`), và endpoint `PATCH /sessions/{session_id}/scope` với kiểm tra RBAC/IDOR trên cả session lẫn tài liệu được chọn (`backend/app/api/routes/sessions.py`).
  - Thêm DTO `UpdateSessionScopeRequest` (`frontend/types/sessions.ts`), validator `validateSessionScope` và client `updateSessionScope` (`frontend/lib/api/sessions.ts`), cùng `ChatController.setPendingScope` / `services.updateScope` (`frontend/lib/chat/controller.ts`, `frontend/lib/chat/services.ts`) để áp dụng scope ngay khi tạo session mới trước turn đầu tiên.
  - Xây dựng UI `DocumentScopeSelector` (`frontend/components/chat/document-scope-selector.tsx`) cho phép tìm kiếm, tick chọn các tài liệu `INDEXED`, đặt lại `ALL_ACTIVE`, và đồng bộ hai chiều với `ChatPreview` / `SessionChat` (`frontend/components/chat/chat-preview.tsx`, `frontend/components/chat/session-chat.tsx`) + QA mock route (`frontend/scripts/qa-mock-api.mjs`).

### Files thêm mới / chỉnh sửa
- **Thêm mới (5.1)**: `backend/app/infrastructure/ingestion_queue.py`, `backend/app/workers/__init__.py`, `backend/app/workers/ingestion_worker.py`, `backend/tests/unit/test_async_ingestion.py`.
- **Chỉnh sửa (5.1)**: `backend/requirements.txt`, `backend/app/shared/config.py`, `.env.example`, `backend/app/documents/ports.py`, `backend/app/documents/repository.py`, `backend/app/documents/ingestion.py`, `backend/app/documents/service.py`, `backend/app/main.py`, `backend/app/api/routes/documents.py`, `frontend/lib/api/documents.ts`, `frontend/lib/documents/controller.ts`, `frontend/hooks/use-documents.ts`, `frontend/components/documents/document-upload.tsx`, `frontend/components/documents/documents-preview.tsx`, `frontend/tests/document-upload.test.mjs`, `frontend/tests/documents.test.mjs`.
- **Thêm mới (5.2)**: `frontend/components/chat/document-scope-selector.tsx`.
- **Chỉnh sửa (5.2)**: `backend/app/api/schemas/conversations.py`, `backend/app/conversations/repository.py`, `backend/app/conversations/service.py`, `backend/app/api/routes/sessions.py`, `backend/tests/unit/test_session_actions.py`, `backend/tests/integration/test_sessions_api.py`, `frontend/types/sessions.ts`, `frontend/lib/api/sessions.ts`, `frontend/lib/chat/controller.ts`, `frontend/lib/chat/services.ts`, `frontend/components/chat/chat-preview.tsx`, `frontend/components/chat/session-chat.tsx`, `frontend/scripts/qa-mock-api.mjs`, `frontend/tests/session-actions.test.mjs`.

### Kết quả kiểm thử
- Backend: `tests/architecture` **9/9 PASS**, `tests/unit` **287/287 PASS**, `tests/integration` **154/154 PASS**
- Frontend: `test:contract` **PASS**, `typecheck` **PASS**, `lint` **PASS**, `npm.cmd test` **214/214 PASS**

---

## Phase 6 – Final Evaluation
> **Trạng thái**: Chưa bắt đầu  
> **Phạm vi**: `Advanced RAG vs Corrective RAG vs Agentic RAG`

### Thay đổi đã thực hiện
- *(Chưa có cập nhật)*

### Kết quả Benchmark định lượng
- *(Chưa có cập nhật)*
