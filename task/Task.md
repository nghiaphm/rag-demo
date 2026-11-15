# RAG Workspace — Upgrade Roadmap & Task Tracking

> **Trạng thái ký hiệu:** `[ ]` Chưa làm · `[/]` Đang thực hiện · `[x]` Hoàn thành · `[!]` Bị chặn

---

## Nguyên tắc kỹ thuật xuyên suốt (Architectural Guardrails)

Mọi thay đổi trong 6 Phase bắt buộc tuân thủ các ràng buộc sau của hệ thống:
1. **Hexagonal Dependency Rules**: Port/Interface đặt ở `shared/`, `rag/`, hoặc `documents/`; Adapter/SDK cụ thể (Langfuse, Redis, ARQ, Tavily...) đặt ở `infrastructure/`. Đảm bảo `tests/architecture/test_dependency_rules.py` luôn PASS.
2. **Offline Test Integrity**: Không làm gãy 251+ Backend unit tests, 210+ Frontend unit tests và `test:contract`. Mọi tích hợp cloud/LLM mới phải có mock/offline fixture.
3. **Feature Flags**: Mỗi tính năng nâng cao đều phải có cờ bật/tắt trong `backend/app/shared/config.py` và `.env.example` để phục vụ so sánh đối chứng ở Phase 6.
4. **SSE Contract Compatibility**: Giữ tương thích ngược với `frontend/lib/sse/parser.ts` (bổ sung event `status`/`step` một cách additive khi chạy multi-step).

---

## Phase 1 – Evaluation & Observability
**Mục tiêu**: Có baseline định lượng của **Advanced RAG** (Hybrid + Rerank + Parent-Child + Multi-Query) và hệ thống tracing/container hoàn chỉnh.

### 1.1 Evaluation Dataset & RAGAS Pipeline
- [x] Chuẩn hóa tập dữ liệu đánh giá (Golden Dataset: cặp `question`, `ground_truth`, `expected_sources`) trong `backend/evaluation/datasets/` dựa trên corpus mẫu (`golden_set.json` + local `corpus/`).
- [x] Tích hợp thư viện `ragas` (hoặc scorer tương đương tương thích LangChain/Groq) vào `backend/evaluation/scoring/` để tính 4 chỉ số:
  - `Context Precision`
  - `Context Recall`
  - `Faithfulness`
  - `Answer Relevancy`
- [x] Cập nhật `backend/evaluation/runner/` để đo thêm **Latency (p50, p95, TTFT)** và **Token Usage** cho mỗi lượt chạy, xuất báo cáo JSON/Markdown lưu vào `backend/evaluation/results/`.
- [x] Chạy và lưu kết quả **Baseline Advanced RAG** làm mốc chuẩn cho Phase 6.

### 1.2 Observability (Langfuse / Tracing Port)
- [x] Định nghĩa port interface `Tracer` / `SpanContext` tại `backend/app/shared/observability.py` (không phụ thuộc SDK bên ngoài).
- [x] Triển khai adapter `LangfuseTracer` tại `backend/app/infrastructure/observability.py` (kèm `NoOpTracer` mặc định khi tắt hoặc chạy offline test).
- [x] Gắn trace span cho từng bước: `prepare_plan` $\rightarrow$ `query_rewrite` $\rightarrow$ `multi_query` $\rightarrow$ `retrieval` $\rightarrow$ `rerank` $\rightarrow$ `context_budget` $\rightarrow$ `llm_generation`.
- [x] Thêm cấu hình `LANGFUSE_ENABLED`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` vào `config.py` và `.env.example`.

### 1.3 Docker Compose (Bao gồm Redis sẵn cho Phase 4–5)
- [x] Tạo `backend/Dockerfile` (Python 3.12-slim, cài `requirements.txt`, chạy uvicorn).
- [x] Tạo `frontend/Dockerfile` (Node 20-alpine, multi-stage build Next.js 16).
- [x] Tạo `docker-compose.yml` tại root gồm các service: `backend`, `frontend`, `redis` (Redis 7-alpine), kèm profile tùy chọn cho `qdrant` / `mongo` local nếu không dùng Cloud.

**Definition of Done (Phase 1)**:
- [x] `docker compose config` hợp lệ; cấu trúc sẵn sàng chạy toàn bộ stack local.
- [x] Có file kết quả baseline RAGAS của Advanced RAG trong `backend/evaluation/results/`.
- [x] Trace span đầy đủ từng bước và AST dependency tests PASS.

---

## Phase 2 – Self-corrective Retrieval (Corrective RAG)
**Mục tiêu**: Hệ thống tự phát hiện kết quả retrieval kém chất lượng và chủ động sửa truy vấn hoặc dùng fallback an toàn trước khi sinh câu trả lời.

### 2.1 Retrieval Grader & Query Correction
- [x] Thêm cờ cấu hình: `CORRECTIVE_RAG_ENABLED`, `CORRECTIVE_MAX_RETRIES` (mặc định `1`), `CORRECTIVE_GRADER_MODEL` (`llama-3.1-8b-instant`).
- [x] Xây dựng module `backend/app/chat/corrective.py`:
  - `RetrievalGrader`: Chấm điểm mức độ liên quan (`RELEVANT` / `AMBIGUOUS` / `IRRELEVANT`) của top-k chunks sau Reranker đối với câu hỏi.
  - `QueryCorrector`: Khi kết quả bị đánh giá `IRRELEVANT` hoặc rỗng, tự động phân tích nguyên nhân và viết lại câu truy vấn tối ưu hơn (tránh lặp lại query cũ), sau đó chạy lại retrieval (tôn trọng `turn_deadline`).

### 2.2 Fallback & Evidence Evaluation
- [x] Xây dựng cơ chế **Fallback Strategy** khi hết số lần retry mà vẫn không đủ tài liệu:
  - Chế độ mặc định (Strict Grounded): Trả về thông báo an toàn không tìm thấy bằng chứng trong thư viện, tuyệt đối không hallucinate.
  - Chế độ mở rộng (Optional): Interface `WebSearchProvider` tại `rag/web_search.py` + adapter `TavilyWebSearchProvider` tại `infrastructure/web_search.py` bật qua cờ `WEB_SEARCH_FALLBACK_ENABLED`.
- [x] Xây dựng **Evidence Evaluation** (`EvidenceEvaluator` - Post-generation Groundedness Check) kiểm tra xem câu trả lời dự kiến có bám sát chunks hay không trước khi chốt `COMPLETED`.

### 2.3 Streaming Status & Unit Tests
- [x] Mở rộng `chat/events.py` (`ChatStatusEvent`) và `api/streaming/sse_schema.py` (`SSEStatusEvent`) + `event_adapter.py` (`status_frame`) hỗ trợ event `status`.
- [x] Viết unit tests offline trong `backend/tests/unit/test_corrective_rag.py` (test grader pass, retry loop, max retries fallback, web fallback, evidence evaluation, timeout bound).

**Definition of Done (Phase 2)**:
- [x] Hệ thống tự động retry query khi tài liệu không khớp và không bị lặp vô hạn.
- [x] Toàn bộ test cũ + mới PASS 100%.

---

## Phase 3 – Agentic Orchestration
**Mục tiêu**: Nâng cấp `ChatOrchestrator` từ bộ định tuyến 1 vòng (Tool HOẶC RAG) thành Single Agent có khả năng lập kế hoạch, gọi đa công cụ lặp lại (Iterative Retrieval) và tự điều chỉnh trạng thái.

### 3.1 Mở rộng Tool Registry cho Agent
- [x] Bổ sung **`rag_search`** thành một Tool chính thức (`tool_use/contracts.py` + `chat/agent_tools.py`) để Agent có thể chủ động gọi tìm kiếm tài liệu nhiều lần với các từ khóa khác nhau trong cùng 1 lượt chat.
- [x] Bổ sung **`query_excel_table`** cho phép Agent lọc/tổng hợp dữ liệu có cấu trúc (`rows`, `count`, `sum`, `avg`, `min`, `max`) trên file `.xlsx` đã upload thay vì chỉ tìm text thuần.

### 3.2 Stateful Iterative Agent Loop
- [x] Nâng cấp `backend/app/chat/orchestrator.py` (hỗ trợ cờ `AGENTIC_MODE_ENABLED` & `MAX_AGENT_STEPS = 4`):
  - Chuyển từ 1-shot selector sang **AgentState** (`messages`, `step_count`, `collected_sources`, `tool_history`, `deadline`) tại `backend/app/chat/agent.py`.
  - Cho phép vòng lặp **Plan $\rightarrow$ Tool Execution $\rightarrow$ Observe $\rightarrow$ Re-plan / Final Answer** (tối đa `MAX_AGENT_STEPS = 4` vòng, có forced final synthesis khi chạm ngưỡng).
  - Cho phép kết hợp cả Tool Metadata (`count_documents`, `list_documents`) + `rag_search` trong cùng một câu hỏi phức hợp.
- [x] Cập nhật `ToolExecutor` giữ nguyên cơ chế sandbox threadpool, 8KB/16KB byte cap và kiểm soát `turn_deadline` tổng.
- [x] Viết unit tests offline trong `backend/tests/unit/test_agentic_orchestrator.py` (test multi-step tool + RAG, max steps guard, backward compatibility khi `AGENTIC_MODE_ENABLED=false`).

**Definition of Done (Phase 3)**:
- [x] Agent giải quyết được câu hỏi đa bước cần kết hợp metadata tool và nhiều lần gọi `rag_search`.
- [x] Khi tắt `AGENTIC_MODE_ENABLED`, hành vi legacy (1-round tool use & direct RAG) được bảo toàn 100%.

---

## Phase 4 – Performance & Security
**Mục tiêu**: Tăng tốc độ phản hồi bằng Semantic Cache và bảo mật dữ liệu doanh nghiệp bằng Auth/RBAC + Access-aware Retrieval + Bounded Execution.

### 4.1 Authentication & RBAC
- [x] Thêm model `User` & `Role` (`admin`, `editor`, `viewer` hoặc `department` tags) vào MongoDB (`backend/app/auth/` hoặc `conversations/`/`documents/`).
- [x] Xây dựng JWT Authentication (Login/Register/Refresh) và FastAPI dependency `get_current_user` (có `AUTH_ENABLED` flag hoặc override hook để không làm vỡ 460+ offline tests).
- [x] Gắn `owner_id` và `allowed_roles` vào `DocumentRecord`, `SessionRecord`, và Qdrant point payload.

### 4.2 Access-aware Retrieval
- [x] Mở rộng `VectorFilter` trong `backend/app/rag/vector_index.py` và `_to_qdrant_filter` trong `qdrant_vector_index.py` để bắt buộc lọc theo `allowed_roles` / `owner_id` của user hiện tại ở mức Qdrant query.
- [x] Bảo vệ toàn bộ endpoints `/documents`, `/sessions`, `/chat` chống truy cập chéo (IDOR protection).

### 4.3 RBAC-aware Semantic Cache
- [x] Định nghĩa port `SemanticCache` và triển khai adapter dùng **Redis** (hoặc Qdrant cache collection) tại `backend/app/infrastructure/semantic_cache.py`.
- [x] **Bảo mật Cache**: Cache key/filter bắt buộc phải phân vùng theo `permission_scope` (`allowed_roles`) và `active_version_snapshot` để tuyệt đối không rò rỉ câu trả lời giữa các user khác quyền (tránh Cache Poisoning).
- [x] Invalidate cache tự động khi có tài liệu mới được `INDEXED` hoặc bị `DELETE`.

### 4.4 Bounded Execution Hardening
- [x] Bổ sung giới hạn cứng: `MAX_AGENT_STEPS`, `MAX_TOKENS_PER_TURN` trong `ContextBudgetConfig` và Rate Limiting per-user trên Redis.
- [x] Viết test bảo mật & cache trong `backend/tests/unit/test_rbac_and_cache.py`.

**Definition of Done (Phase 4)**:
- [x] User không thể retrieve hoặc preview tài liệu ngoài phân quyền RBAC.
- [x] Câu hỏi lặp lại (cùng quyền, cùng ngữ nghĩa $\ge 0.95$) trả về từ Semantic Cache trong `< 100ms`.

---

## Phase 5 – Production Workflow
**Mục tiêu**: Hoàn thiện luồng bất đồng bộ thực tế trên Backend và nâng cấp đầy đủ tính năng UX/UI trên Frontend, sẵn sàng triển khai.

### 5.1 Async Ingestion Worker (Redis + ARQ)
- [ ] Thêm `arq` và `redis` vào `backend/requirements.txt`.
- [ ] Xây dựng ARQ worker (`backend/app/workers/ingestion_worker.py`) xử lý tác vụ `parse -> chunk -> embed -> upsert Qdrant -> activate` bất đồng bộ ngoài HTTP request.
- [ ] Cập nhật `POST /documents/upload` và `PUT /documents/{id}` trả về HTTP `202 Accepted` kèm `job_id` ngay lập tức (khi `ASYNC_INGESTION_ENABLED=true`).
- [ ] Frontend `/documents` tự động polling hoặc cập nhật trạng thái real-time (`PENDING` $\rightarrow$ `PROCESSING` $\rightarrow$ `INDEXED`).

### 5.2 Document Scope Selector (Backend API + Frontend UI)
- [ ] Mở API `PATCH /sessions/{session_id}/scope` hỗ trợ chuyển đổi giữa `ALL_ACTIVE` và `SELECTED_DOCUMENTS` (danh sách `document_ids` đã có sẵn ở `conversations/models.py`).
- [ ] Xây dựng UI Scope Selector trên `frontend/components/chat/` cho phép người dùng tick chọn tài liệu cụ thể cho phiên chat hiện tại.

### 5.3 Inline PDF Viewer & Citation Highlighting
- [ ] Thêm Backend endpoint `GET /documents/{document_id}/versions/{version_id}/file` stream file PDF gốc an toàn (kiểm tra quyền RBAC từ Phase 4).
- [ ] Tích hợp PDF Viewer trên Frontend (`react-pdf` / `pdf.js`) trong `DocumentPreviewSheet`: khi click citation `[n]`, mở đúng file PDF và cuộn tới trang `page + 1` *(lưu ý backend lưu zero-based page)*.

### 5.4 Frontend Auth UI & Deployment Readiness
- [ ] Bổ sung màn hình Login / Token handling trên Frontend (tương thích chế độ mock offline).
- [ ] Cấu hình Nginx / Reverse Proxy mẫu (tắt buffering cho `/chat/stream` SSE), cập nhật CORS `allow_origins` từ biến môi trường, hoàn thiện `docker-compose.prod.yml`.

**Definition of Done (Phase 5)**:
- [ ] Upload PDF dung lượng lớn không bị timeout HTTP; tiến độ cập nhật mượt trên UI.
- [ ] Chọn Document Scope và click Citation mở đúng trang PDF hoạt động end-to-end.

---

## Phase 6 – Final Evaluation
**Mục tiêu**: So sánh định lượng toàn diện 3 thế hệ kiến trúc trên cùng một bộ dữ liệu chuẩn để xuất báo cáo tổng kết.

### 6.1 Benchmark Matrix
Chạy tự động qua `backend/evaluation/runner/` trên 3 cấu hình Feature Flags:
1. **Config A — Advanced RAG**: (`CORRECTIVE_RAG_ENABLED=false`, `AGENTIC_MODE_ENABLED=false`)
2. **Config B — Corrective RAG**: (`CORRECTIVE_RAG_ENABLED=true`, `AGENTIC_MODE_ENABLED=false`)
3. **Config C — Agentic RAG**: (`AGENTIC_MODE_ENABLED=true`, `SEMANTIC_CACHE_ENABLED=true/false`)

### 6.2 Tổng hợp & Xuất Báo cáo
- [ ] Thu thập bảng so sánh đầy đủ cho 3 cấu hình:
  - **Chất lượng (RAGAS)**: `Context Precision`, `Context Recall`, `Faithfulness`, `Answer Relevancy`.
  - **Hiệu năng (Langfuse / Metrics)**: `Latency p50`, `Latency p95`, `TTFT`, `Cache Hit Latency`.
  - **Chi phí**: `Avg Tokens / Query`, `LLM Calls / Query`, `Estimated Cost / 1000 Queries`.
- [ ] Lưu báo cáo chính thức tại `docs/evaluation/FINAL-EVALUATION-REPORT.md` và cập nhật kết quả benchmark nổi bật vào `README.md`.

**Definition of Done (Phase 6)**:
- [ ] Có số liệu đối chứng định lượng rõ ràng giữa Advanced RAG vs Corrective RAG vs Agentic RAG.
- [ ] Toàn bộ CI (Backend + Frontend + Docker build) xanh 100%.
