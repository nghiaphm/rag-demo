# RAG Workspace Readiness — Implementation Change Log

Tài liệu này lưu lại toàn bộ lịch sử thực thi, quyết định thiết kế, danh sách file thêm mới/chỉnh sửa/di chuyển, mã commit và bằng chứng kiểm thử thực tế qua từng Phase theo kế hoạch đã được phê duyệt tại [`Task.md`](Task.md) và báo cáo kiểm toán gốc [`BASELINE_AUDIT.md`](../../BASELINE_AUDIT.md).

---

## Quy ước Ghi chép (Logging Rules)
1. **Bằng chứng thực chứng:** Chỉ ghi nhận kết quả kiểm thử sau khi đã chạy lệnh thực tế; ghi rõ câu lệnh và con số quan sát được (`X/Y PASS`), không suy diễn từ các lượt chạy cũ.
2. **Phân biệt mức độ hoàn thiện:** Ghi rõ từng hạng mục sau khi làm xong đạt mức **`Verified`** (đã chạy xác nhận hành vi thực tế), **`Tested`** (đã pass kiểm thử tự động với mock/isolated fixture), hay **`Deferred`** (chuyển hoãn có chủ đích).
3. **Truy vết Commit:** Cập nhật mã commit (`short SHA`) tương ứng với từng task sau khi người dùng xác nhận/chốt commit.

---

## Nhật ký Khởi tạo & Phê duyệt Kế hoạch (Pre-Execution History)
- **2026-11-27 — Baseline Audit (`BASELINE_AUDIT.md`):** Kiểm toán toàn diện mã nguồn, cấu hình, tài liệu và chạy bộ test offline trên nhánh `feat/hr-dashboard-analytics-chat` (`31f2bf8`). Phát hiện khoảng cách nối dây ở Agentic Mode, Corrective RAG, Healthcheck pool teardown, Test config isolation (111 backend tests lỗi khi `.env` local bật flags), Observability và tài liệu.
- **2026-11-27 — Lập & Tinh chỉnh Kế hoạch (`Task.md`):** Chốt lộ trình **6 Phase / 19 Tasks (`T0.1` – `T5.2`)** theo hướng thực dụng, tránh overengineering:
  - Thống nhất 1 công cụ phân tích bảng Excel duy nhất (`run_sql`) cho cả `STORAGE_BACKEND=local` và `s3`.
  - Chuyển sang **Deferred**: Authentication/JWT/RBAC/IDOR, Semantic Cache, Web Search fallback, Backend Structural Refactoring, Inline PDF Viewer, và cụm hạ tầng `docker-compose.prod.yml`.
  - **Trạng thái phê duyệt:** Nội dung `Task.md` đã được chấp thuận; khởi tạo `change-log.md` chờ duyệt trước khi bắt tay vào **Phase 0**.

---

## Baseline (Pre-Phase 0) — Trạng thái trước khi bắt đầu
- **Thời điểm ghi nhận:** 2026-11-27 (Nhánh `feat/hr-dashboard-analytics-chat` tại commit `31f2bf8`).
- **Trạng thái Working Tree ban đầu:**
  - *Staged:* `.gitattributes`, `.githooks/commit-msg`, `.githooks/pre-commit`.
  - *Modified (Unstaged):* `GEMINI.md`, `backend/app/documents/excel/sql_service.py` (sửa `DocumentRepository` → `MongoDocumentRepository`), `backend/tests/integration/test_chat_sql_routing.py`.
  - *Untracked:* `BASELINE_AUDIT.md`, `task/rag-workspace-readiness/Task.md`, `task/rag-workspace-readiness/change-log.md`.
- **Trạng thái Kiểm thử Baseline:**
  - **Backend Architecture AST:** `9/9 PASS` (`tests/architecture/test_dependency_rules.py`).
  - **Backend Unit Tests:** `332/332 PASS` (với biến môi trường mặc định CI); `40 FAIL/ERROR` trên `test_chat_orchestration.py` khi đọc trực tiếp `.env` local đang bật flags.
  - **Backend Integration Tests:** `181/181 PASS` trên 20 file `test_*.py` (với mặc định CI); `71 FAIL/ERROR` khi đọc `.env` local; còn 16 file `smoke_*.py` chưa phân loại trong `tests/integration/`.
  - **Backend Offline Smoke & Integrity:** `smoke_sse_schema.py`, `smoke_context_budget.py`, `smoke_query_rewriting.py` (`3/3 PASS`); `pip check` & `compileall` (`PASS`).
  - **Frontend Suites:** `npm.cmd run test:contract` (`63 schemas PASS`), `npm.cmd run typecheck` (`PASS`), `npm.cmd run lint` (`PASS`), `npm.cmd test` (`237/237 PASS`).

---

## Bảng Theo dõi Tổng hợp Tiến độ (Execution Ledger)

| Phase | Phạm vi Tasks | Trạng thái | Commits | Tóm tắt Kiểm chứng |
| :--- | :--- | :--- | :--- | :--- |
| **Phase 0** — Pre-Stage Stabilization | `T0.1` – `T0.4` | **Hoàn thành & Merged** (`3166c27`) | `78c400c`..`fa404fd` | Arch `9/9`, Unit `338/338`, Integration `183/183`, Smoke `3/3`, OpenAPI `63` schemas PASS |
| **Phase 1** — Reliability *(No Auth/Cache)* | `T1.1` – `T1.3` | **Hoàn thành & Merged** (`6c3a512`) | `2dd3002`..`af74ed9` | Arch `9/9`, Unit `344/344`, Integration `185/185`, FE `238/238`, OpenAPI `64` schemas PASS |
| **Phase 2** — Observability | `T2.1` – `T2.4` | **Hoàn thành** (`T2.1`–`T2.3` `Verified`, `T2.4` `Deferred`) | `f32243e`, `e0ea92f`, `01a874a` | `pip check` OK, Arch `9/9`, Unit `350/350`, Integration `186/186`, OpenAPI `64` schemas PASS |
| **Phase 3** — RAG & Agent Evaluation | `T3.1` – `T3.4` | Chưa bắt đầu | *(chờ thực thi)* | *(chờ cập nhật)* |
| **Phase 4** — Deployment & Testing | `T4.1` – `T4.4` | Chưa bắt đầu | *(chờ thực thi)* | *(chờ cập nhật)* |
| **Phase 5** — Documentation & Demo | `T5.1` – `T5.2` | Chưa bắt đầu | *(chờ thực thi)* | *(chờ cập nhật)* |

---

## Phase 0 — Pre-Stage Stabilization
> **Trạng thái:** **Hoàn thành & Đã Commit (2026-11-27)** trên nhánh `fix/pre-stage-stabilization` (tách từ `master` `af816df`)  
> **Phạm vi:** `T0.1 Working Tree Diff Review` · `T0.2 unittest Config Isolation` · `T0.3 Unified run_sql (Local/S3) & Agentic Wiring` · `T0.4 Corrective RAG (Grade/Retry/Safe Fallback)`

### Truy vết Chuỗi Commit (Theo `GEMINI.md` §6)
1. `78c400c` — `chore(git-hooks): add pre-commit and commit-msg validation hooks`
2. `76689e4` — `docs: add execution protocol and git workflow rules to GEMINI.md`
3. `23cd072` — `test(config): isolate backend unittest settings from local dotenv`
4. `911ac10` — `fix(excel-sql): use MongoDocumentRepository in create_excel_sql_service`
5. `841b1dd` — `feat(duckdb): support local Parquet storage in Excel SQL executor`
6. `113ea17` — `fix(chat): enforce session scope and schema parity in agentic mode`
7. `0e7ab32` — `feat(corrective-rag): wire grader LLM into runner with safe fallback`
8. *(Commit hiện tại)* — `docs(task): add readiness roadmap and Phase 0 changelog` *(giữ `BASELINE_AUDIT.md` ở local không đưa lên Git theo xác nhận của người dùng)*

### Quyết định thiết kế & Thay đổi thực hiện
- **T0.1 (Working Tree Diff Review & Commit Classification — Không tự ý commit):**
  - Rà soát chi tiết toàn bộ 6 file đang dirty sẵn trên working tree trước khi triển khai Phase 0; xác nhận **0 secret**, **0 debug code**, tuân thủ quy ước bảo mật & kiến trúc:
    1. **Nhóm Pre-1 (Git Hooks & Repo Guardrails):** `.gitattributes` (ép `eol=lf` cho `.githooks/*` và `*.sh`), `.githooks/commit-msg` (kiểm tra Conventional Commits hoặc prefix milestone `T0.x — ...`, chặn `feat(phase-N)`), `.githooks/pre-commit` (chặn `.env`/private keys/hardcoded API keys, kiểm tra JSON, chạy `py_compile`/AST `tests/architecture` và ESLint/`tsc`), `GEMINI.md` (chuẩn hóa `<repo-root>` và bổ sung Mục 6 Execution Protocol).
    2. **Nhóm Pre-2 + T0.3 (Excel SQL Service Fix & Unified Local/S3 Agentic SQL):** Bản sửa `DocumentRepository` → `MongoDocumentRepository` trong `backend/app/documents/excel/sql_service.py` (dòng 844–852) và regression test khởi tạo lười `create_excel_sql_service` tại `backend/tests/integration/test_chat_sql_routing.py` đã được xác nhận `PASS` và tích hợp liền mạch cùng bộ thay đổi `T0.3`.
- **T0.2 (`unittest` Test Config Isolation):**
  - Tạo `backend/tests/_test_env.py` cung cấp `install_test_environment()` (vô hiệu hóa `Settings.model_config["env_file"]`, nạp lại `Settings(_env_file=None)` với mặc định chuẩn CI nhưng vẫn tôn trọng biến môi trường tiến trình nếu truyền tường minh, đồng thời xóa cache `get_llm` / `get_grader_llm` / `get_embeddings`) và context manager `override_settings(**overrides)`.
  - Gắn `install_test_environment()` idempotent ở đầu cả 4 file `__init__.py` (`tests/`, `tests/unit/`, `tests/integration/`, `tests/architecture/`) để hoạt động bất kể chạy `unittest discover` từ `backend/` hay từ `<repo-root>`.
  - Triệt tiêu hoàn toàn 111 lỗi test (`40` unit + `71` integration) từng xảy ra khi file `.env` cá nhân bật `AGENTIC_MODE_ENABLED=true`, `EXCEL_SQL_ENABLED=true`, `STORAGE_BACKEND=s3`.
- **T0.3 (Chuẩn hóa Agentic Orchestrator & Thống nhất `run_sql` cho cả Local & S3):**
  - Sửa `backend/app/shared/config.py` và `ChatOrchestrator.__init__`: cho phép `EXCEL_SQL_ENABLED=true` hoạt động trên cả `STORAGE_BACKEND=local` và `STORAGE_BACKEND=s3` (vẫn bắt buộc `AGENTIC_MODE_ENABLED=true` + `EXCEL_PARQUET_INGESTION_ENABLED=true`).
  - Mở rộng `DuckDBSqlExecutor` (`backend/app/infrastructure/duckdb_executor.py`): bổ sung `local_parquet_loader` đọc bytes Parquet đã qua RBAC/scope check từ `LocalFileStorage`, dựng bảng `pyarrow.parquet.read_table(io.BytesIO(...))` và đăng ký `TEMP VIEW` **trước khi** gọi `_apply_security_lockdown(conn)` — bảo toàn tuyệt đối `disabled_filesystems='LocalFileSystem'` và `lock_configuration=true` để SQL do LLM sinh không thể truy cập đĩa máy chủ; ở chế độ `local` không nạp `httpfs`.
  - Sửa `ChatOrchestrator.prepare_plan` (`backend/app/chat/orchestrator.py`): đọc đúng `getattr(loaded, "scope", None)` thay vì `"retrieval_scope"`, và phân giải `active_version_ids` qua `_resolve_active_version_ids(MongoDocumentRepository(database), effective_scope)` cho nhánh `AGENTIC` để `rag_search` tôn trọng `SessionScopeMode.SELECTED_DOCUMENTS` tương đương `run_sql`.
  - Đồng bộ 1-1 giữa tool schemas và handlers: thêm `agent_tool_schemas_for_registry(registry)` trong `backend/app/chat/agent_tools.py`, cập nhật `AGENT_SYSTEM_INSTRUCTION` trong `backend/app/chat/agent.py` sang `run_sql`, loại bỏ hoàn toàn tình trạng quảng bá thừa `query_excel_table` khi không đăng ký handler.
- **T0.4 (Corrective RAG Gọn Nhẹ — Grading + Query Retry + Safe Fallback):**
  - Thêm `@lru_cache def get_grader_llm()` tại `backend/app/rag/llm.py` sử dụng `settings.corrective_grader_model` với `temperature=0.0`.
  - Thêm factory `create_corrective_runner(llm=..., max_retries=..., timeout_seconds=...)` tại `backend/app/chat/corrective.py` nối `llm` vào cả `RetrievalGrader` và `QueryCorrector`, cố định `web_search_provider=None` (theo quyết định Deferred Web Search).
  - Cập nhật `prepare_rag_request_from_components` tại `backend/app/chat/pipeline.py` gọi `create_corrective_runner(llm=get_grader_llm(), max_retries=settings.corrective_max_retries)` khi `settings.corrective_rag_enabled=True`; tự động kích hoạt **Strict Safe Fallback** (context rỗng + prompt từ chối an toàn `(không có tài liệu liên quan)`) khi hết lượt retry mà tài liệu vẫn `IRRELEVANT`. Không chặn runtime bằng `EvidenceEvaluator`.

### Files thêm mới / chỉnh sửa
- **Thêm mới:**
  - `backend/tests/_test_env.py`
  - `backend/tests/unit/test_config_isolation.py`
  - *(Có sẵn trên index từ trước Phase 0, đã rà soát ở T0.1):* `.gitattributes`, `.githooks/commit-msg`, `.githooks/pre-commit`, `task/rag-workspace-readiness/Task.md`, `task/rag-workspace-readiness/change-log.md` *(riêng `BASELINE_AUDIT.md` giữ ở local không commit lên Git)*.
- **Chỉnh sửa:**
  - `backend/tests/__init__.py`, `backend/tests/unit/__init__.py`, `backend/tests/integration/__init__.py`, `backend/tests/architecture/__init__.py`
  - `backend/app/shared/config.py`
  - `backend/app/infrastructure/duckdb_executor.py`
  - `backend/app/chat/agent.py`
  - `backend/app/chat/agent_tools.py`
  - `backend/app/chat/orchestrator.py`
  - `backend/app/rag/llm.py`
  - `backend/app/chat/corrective.py`
  - `backend/app/chat/pipeline.py`
  - `backend/tests/unit/test_duckdb_executor.py`
  - `backend/tests/unit/test_excel_selective_embedding.py`
  - `backend/tests/unit/test_agentic_orchestrator.py`
  - `backend/tests/unit/test_corrective_rag.py`
  - `backend/tests/integration/test_chat_sql_routing.py`
  - `backend/tests/integration/test_rag_integration.py`
  - *(Có sẵn từ trước Phase 0, đã rà soát ở T0.1):* `GEMINI.md`, `backend/app/documents/excel/sql_service.py`.

### Kết quả kiểm thử & Phân loại trạng thái
- **`Verified` (Hành vi hạ tầng test & bảo vệ kiến trúc chạy trực tiếp không mock):**
  - `.\.venv\Scripts\python.exe -m unittest discover -s backend/tests/architecture -t backend -v` → **`9/9 PASS` (`0.200s`)**.
  - `.\.venv\Scripts\python.exe -m compileall -q backend/app backend/tests` → **`PASS` (0 lỗi cú pháp)**.
  - `npm.cmd --prefix frontend run test:contract` → **`PASS` (63 REST/SSE/health schemas đồng bộ 1-1)**.
  - Giữ nguyên `.env` cá nhân đang bật flags, chạy trực tiếp không truyền biến môi trường ghi đè:
    - `.\.venv\Scripts\python.exe -m unittest discover -s backend/tests/unit -t backend -v` → **`338/338 PASS` (`12.952s`)** *(tăng +6 unit tests mới so với baseline 332)*.
    - `.\.venv\Scripts\python.exe -m unittest discover -s backend/tests/integration -t backend -v` → **`183/183 PASS` (`12.451s`)** *(tăng +2 integration tests mới so với baseline 181)*.
- **`Tested` (Logic nghiệp vụ Agentic, DuckDB Local/S3 Sandbox & Corrective RAG với offline fakes/fixtures):**
  - DuckDB in-memory + real PyArrow Parquet bytes (`STORAGE_BACKEND=local`) thực thi truy vấn `SUM`/`GROUP BY` thành công và chặn `read_parquet('/etc/passwd')` ở cả `sql_guard` lẫn DuckDB `Permission Error: File system LocalFileSystem has been disabled by configuration`.
  - Agentic `SELECTED_DOCUMENTS` scope áp dụng đồng nhất cho cả `rag_search` và `run_sql`; `schemas` khớp 100% với `registry.keys()`.
  - Corrective RAG nối `get_grader_llm()` vào `RetrievalGrader` + `QueryCorrector`, retry tối đa `corrective_max_retries` và kích hoạt safe fallback khi không tìm thấy tài liệu phù hợp *(chờ Live Evaluation với Groq thật ở Phase 3 để nâng lên `Verified` end-to-end)*.
  - Offline smoke scripts (`PYTHONPATH=backend`): `smoke_sse_schema.py`, `smoke_context_budget.py`, `smoke_query_rewriting.py` → **`3/3 PASS`**.

---

## Phase 1 — Reliability (Tạm hoãn Authentication/RBAC & Semantic Cache)
> **Trạng thái:** **Hoàn thành & Đã Commit (2026-11-27)** trên nhánh `fix/reliability-hardening` (tách từ `master` `3166c27`)  
> **Phạm vi:** `T1.1 Non-destructive Health (Required vs Optional)` · `T1.2 Upload Size Cap (413), Redis Failure Policy & Trusted Proxy IP` · `T1.3 Provider Timeouts, SecretStr, Dynamic CORS, Security Headers & Startup Guard`

### Truy vết Chuỗi Commit (Theo `GEMINI.md` §6)
1. `2dd3002` — `fix(health): avoid closing active pools and separate optional checks`
2. `ceb0f41` — `feat(security): harden provider timeouts, SecretStr, CORS, and headers`
3. `08fa055` — `fix(rate-limit): add atomic Redis Lua script, fallback, and proxy IP`
4. `a0adae0` — `feat(documents): enforce 413 upload size caps across API and frontend`
5. *(Commit hiện tại)* — `docs(task): update readiness roadmap and Phase 1 changelog` *(giữ `BASELINE_AUDIT.md` ở local)*

### Quyết định thiết kế & Thay đổi thực hiện
- **T1.1 (Non-destructive `/health/dependencies` & Required vs Optional Dependencies):**
  - Bổ sung `threading.RLock()` và tách phương thức `check_health()` khỏi `connect()` trên `MongoDBConnection` (`backend/app/infrastructure/mongo.py`) và `QdrantConnection` (`backend/app/infrastructure/qdrant.py`): kiểm tra trực tiếp trên client đang sống (`admin.command("ping")` / `get_collections()`), tuyệt đối **không gọi `self.close()`** kể cả khi ping gặp lỗi mạng tạm thời.
  - Bổ sung `check_redis_health`, `check_s3_health`, `is_readiness_ok` và `CloudConnections.check_health_all()` (`backend/app/infrastructure/connections.py`):
    - **Required (`mongodb`, `qdrant`):** Luôn kiểm tra; lỗi → HTTP `503` (`status="degraded"`).
    - **Conditional Blocking (`s3` khi `STORAGE_BACKEND=s3`, `redis` khi `ASYNC_INGESTION_ENABLED=true`):** Lỗi → HTTP `503` (`status="degraded"`).
    - **Optional Non-blocking (`redis` khi chỉ bật `RATE_LIMIT_ENABLED=true`):** Báo trạng thái lỗi trong `dependencies.redis` để giám sát nhưng tổng thể vẫn giữ HTTP `200` (`status="ok"`), khớp với cơ chế fallback bộ nhớ ở `T1.2`.
  - Đồng bộ kiểu `DependencyHealthResponse` (`redis?`, `s3?`) tại `frontend/types/api.ts`, `frontend/lib/api/health.ts` và `frontend/tests/verify-api-contract.mjs`.
- **T1.2 (HTTP `413 Content Too Large`, Atomic Redis Lua Rate Limiter & Trusted Proxy IP):**
  - Thêm `max_upload_bytes: int = 25 * 1024 * 1024` (`25 MiB`) và `trusted_proxy_ips: tuple[str, ...] = ()` vào `Settings` (`backend/app/shared/config.py`) + `.env.example`.
  - Thống nhất trả **HTTP `413 Content Too Large`** trong `_read_upload()` (`backend/app/api/routes/documents.py`) khi vượt `MAX_UPLOAD_BYTES` (`25 MiB`) đối với `.pdf`/`.txt`/`.md`/`.markdown` hoặc vượt `min(MAX_XLSX_BYTES, MAX_UPLOAD_BYTES)` (`10 MiB`) đối với `.xlsx` (chỉ đọc tối đa `max_bytes + 1` bytes vào RAM); giữ nguyên HTTP `400` cho file rỗng, sai phần mở rộng, sai MIME hoặc hỏng cấu trúc workbook.
  - Khai báo `413: {"model": HTTPErrorResponse, "description": "Content Too Large"}` trên `POST /documents/upload` và `PUT /documents/{document_id}` (`backend/app/api/schemas/chat_documents.py`), đồng thời bổ sung thông báo lỗi `413` an toàn vào `safeApiErrorMessage` (`frontend/lib/api/error-ux.ts`).
  - Nâng cấp `RedisRateLimiter` (`backend/app/infrastructure/semantic_cache.py`): dùng Lua script atomic (`INCR` + `EXPIRE` khi `count == 1` hoặc `TTL < 0`); khi Redis gặp sự cố kết nối, ghi log `WARNING` có tiết lưu (`30s`, không lộ thông tin nhạy cảm) và chuyển sang bộ đếm in-memory cục bộ có giới hạn kích thước (`max_memory_keys=10_000`).
  - Tạo `resolve_client_ip(request, trusted_proxy_ips)` (`backend/app/api/dependencies/client_ip.py`): chỉ tin cậy IP hợp lệ đầu tiên trong `X-Forwarded-For` khi `request.client.host` thuộc `trusted_proxy_ips` (hỗ trợ cả IP đơn và dải CIDR), áp dụng cho cả `/chat`, `/chat/stream` và upload/update tài liệu.
- **T1.3 (Provider Timeouts/Retries, `SecretStr`, Dynamic CORS, Security Headers & Startup Guard):**
  - Chuyển `embedding_api_key` sang `SecretStr` trong `Settings` và cập nhật `backend/app/rag/embeddings.py` + `backend/scripts/controlled_live_e2e.py` dùng `.get_secret_value()`.
  - Bổ sung `llm_request_timeout_seconds: float = 60.0`, `llm_max_retries: int = 2`, `embedding_timeout_seconds: float = 30.0` và nối vào `get_llm()`, `get_grader_llm()` (`backend/app/rag/llm.py`) và `get_embeddings()` (`request_options={"timeout": ...}`).
  - Bổ sung cấu hình động `cors_origins`, middleware thuần ASGI `SecurityHeadersMiddleware` (không buffer luồng SSE, tự động gắn `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`) qua hàm `configure_middlewares()` tại `backend/app/main.py`.
  - Bổ sung startup guard trong `Settings`: từ chối khởi động ngay lập tức (`ValidationError`) nếu `auth_enabled=True` nhưng `jwt_secret_key` ngắn dưới 32 ký tự hoặc dùng giá trị mặc định yếu.

### Files thêm mới / chỉnh sửa
- **Thêm mới:**
  - `backend/app/api/dependencies/client_ip.py`
- **Chỉnh sửa:**
  - `.env.example`
  - `backend/app/shared/config.py`
  - `backend/app/infrastructure/mongo.py`
  - `backend/app/infrastructure/qdrant.py`
  - `backend/app/infrastructure/connections.py`
  - `backend/app/infrastructure/semantic_cache.py`
  - `backend/app/api/schemas/chat_documents.py`
  - `backend/app/api/routes/documents.py`
  - `backend/app/api/routes/chat.py`
  - `backend/app/rag/llm.py`
  - `backend/app/rag/embeddings.py`
  - `backend/app/main.py`
  - `backend/scripts/controlled_live_e2e.py`
  - `backend/tests/unit/test_cloud_connections.py`
  - `backend/tests/unit/test_rbac_and_cache.py`
  - `backend/tests/unit/test_llm.py`
  - `backend/tests/integration/test_documents_api.py`
  - `backend/tests/integration/test_cors.py`
  - `frontend/types/api.ts`
  - `frontend/lib/api/health.ts`
  - `frontend/lib/api/error-ux.ts`
  - `frontend/tests/verify-api-contract.mjs`
  - `frontend/tests/error-health.test.mjs`
  - `frontend/tests/document-upload.test.mjs`

### Kết quả kiểm thử & Phân loại trạng thái
- **`Verified` (Kiến trúc, hợp đồng OpenAPI, cấu hình bảo mật & hành vi HTTP middleware thực tế):**
  - `.\.venv\Scripts\python.exe -m unittest discover -s backend/tests/architecture -t backend -v` → **`9/9 PASS` (`0.222s`)**.
  - `.\.venv\Scripts\python.exe -m compileall -q backend/app backend/tests backend/scripts` → **`PASS` (0 lỗi cú pháp)**.
  - `npm.cmd --prefix frontend run test:contract` → **`PASS: 64 REST/SSE/health schemas`** *(bao gồm `HTTPErrorResponse` cho mã `413` và `DependencyHealthResponse` mở rộng)*.
  - `npm.cmd --prefix frontend run typecheck` → **`PASS` (`tsc --noEmit`)**.
  - `npm.cmd --prefix frontend run lint` → **`PASS` (`eslint`)**.
  - `npm.cmd --prefix frontend test` → **`238/238 PASS` (`11.46s`)**.
- **`Tested` (Toàn bộ bộ kiểm thử Backend Unit & Integration không phụ thuộc cloud/provider thật):**
  - `.\.venv\Scripts\python.exe -m unittest discover -s backend/tests/unit -t backend -v` → **`344/344 PASS` (`4.186s`)** *(tăng +6 unit tests mới so với Phase 0)*.
  - `.\.venv\Scripts\python.exe -m unittest discover -s backend/tests/integration -t backend -v` → **`185/185 PASS` (`5.908s`)** *(tăng +2 integration tests mới so với Phase 0)*.

---

## Phase 2 — Observability
> **Trạng thái:** **Hoàn thành, Đã Push & Đã Merge vào `master` (`1984d65`, 2026-11-27)** từ nhánh `feat/observability-hardening` (tách từ `master` `6c3a512`)  
> **Phạm vi:** `T2.1 JSON Logging & Validated X-Request-ID` · `T2.2 Langfuse SDK v2 Compatibility & Redaction` · `T2.3 prometheus-client Low-Cardinality /metrics` · `T2.4 Conditional SSE Status Events Gate (Deferred)`

### Truy vết Chuỗi Commit (Theo `GEMINI.md` §6)
1. `f32243e` — `feat(logging): add JSON formatter, secret redaction, and request ID`
2. `e0ea92f` — `feat(tracing): pin Langfuse v2 SDK, redact payloads, and wire chat`
3. `01a874a` — `feat(metrics): add Prometheus low-cardinality metrics and HTTP wiring`
4. `0a09bf0` — `docs(task): update readiness roadmap and Phase 2 changelog` *(giữ `BASELINE_AUDIT.md` ở local; merged vào `master` tại `1984d65`)*

### Quyết định thiết kế & Thay đổi thực hiện
- **T2.1 (Structured JSON Logging, Validate `X-Request-ID` & Secret Redaction):**
  - Thêm cấu hình `log_level: str = "INFO"` và `log_format: str = "json"` (`json` | `text`) vào `Settings` (`backend/app/shared/config.py`) và `.env.example`.
  - Bổ sung `request_id_var` (`ContextVar`), `validate_or_generate_request_id` (regex nghiêm ngặt `\A[A-Za-z0-9._-]{1,64}\Z`, từ chối ký tự điều khiển `\r`/`\n`/khoảng trắng/chuỗi > 64 ký tự và thay bằng UUIDv4 sạch) cùng hàm `redact_secrets` che các mẫu khóa bí mật (`gsk_`, `AIza`, `pk-lf-`/`sk-lf-`, `tvly-`, `sk-`, `mongodb(+srv)://user:pass@`, `redis(s)://:pass@`, `Bearer ...`) trong `backend/app/shared/observability.py`.
  - Tạo `backend/app/infrastructure/logging_config.py` (`RequestIdLogFilter`, `RedactingJsonFormatter`, `RedactingTextFormatter`, `configure_logging`) đảm bảo xuất 1 dòng JSON hợp lệ kèm `request_id` và tự động che khóa bí mật cả trong nội dung log lẫn stack trace ngoại lệ.
  - Bổ sung middleware thuần ASGI `RequestObservabilityMiddleware` trong `backend/app/main.py` (không buffer luồng SSE) gắn `request_id` vào `contextvars` và trả lại header `X-Request-ID` trên mọi HTTP response; trong `backend/app/api/routes/chat.py`, hàm `_resolve_turn_uuid()` tái sử dụng `request_id` nếu là UUID hợp lệ và tự sinh UUID riêng cho `SSEStartData`/`ChatResponse` nếu gateway gửi `X-Request-ID` dạng chuỗi ASCII phi-UUID.
- **T2.2 (Tương thích Langfuse v2 SDK, Nối Đủ Luồng Chat & Redaction Mặc định):**
  - Pin `langfuse>=2.50.0,<3.0.0` (đã cài và xác nhận `langfuse==2.60.10`, `pip check` PASS 0 xung đột với toàn bộ `backend/requirements.txt`).
  - Thêm `langfuse_trace_content_enabled: bool = False` (`LANGFUSE_TRACE_CONTENT_ENABLED=false` mặc định): khi ở mức mặc định `false`, `_sanitize_trace_payload` trong `backend/app/infrastructure/observability.py` tự động chuyển các trường văn bản nhạy cảm (`question`, `query`, `retrieval_query`, `answer`, `prompt`, `sql`, `queries`, `chunks`...) sang chỉ số định lượng an toàn (`*_chars`, `*_count`) và quét `redact_secrets` trước khi gửi tới `sdk_client.trace` / `sdk_trace.span` / `sdk_span.end`.
  - Sửa `prepare_rag_request_from_components` trong `backend/app/chat/pipeline.py` quản lý đúng context manager `with active_trace:` khi sở hữu trace, đồng thời truyền `request.app.state.tracer` đầy đủ vào tất cả các nhánh stateless/persistent của `/chat` và `/chat/stream` trong `backend/app/api/routes/chat.py`.
- **T2.3 (`prometheus-client` Operational Metrics với Low-Cardinality Labels):**
  - Thêm `prometheus-client>=0.21.0,<1.0.0` (`prometheus-client==0.26.0`) và cờ `metrics_enabled: bool = True` (`METRICS_ENABLED=true`).
  - Định nghĩa port `MetricsRecorder` trong `backend/app/shared/observability.py` (giữ sạch ranh giới Hexagonal `api`/`chat`/`documents` -> `shared`) và triển khai adapter `PrometheusMetricsRecorder` trong `backend/app/infrastructure/metrics.py` với 6 metrics chuẩn low-cardinality:
    - `rag_http_requests_total` & `rag_http_request_duration_seconds` (`method`, `route` lấy từ `scope["route"].path` hoặc `"unmatched"` cho 404, `status_code`).
    - `rag_chat_turns_total` (`transport`, `mode`, `route_type`, `outcome`).
    - `rag_chat_ttft_seconds` (nối từ `record_stream_metric` trong `stream_metrics.py`).
    - `rag_stage_duration_seconds` (`stage`: `rewrite`, `multi_query`, `retrieval`, `rerank`, `corrective`, `sql`, `generation`).
    - `rag_llm_tokens_total` (`direction`: `input`, `output`).
  - Mở `GET /metrics` (`include_in_schema=False`) trong `backend/app/main.py`, giữ nguyên 64 OpenAPI schemas cho Frontend.
- **T2.4 (Kết quả Cổng Quyết Định SSE `status` Events → Chuyển sang `[-]` Deferred):**
  - Qua kiểm tra mã nguồn thực tế tại `backend/app/api/routes/chat.py:585-625` (quyết định kiến trúc `C05`) và bộ test Frontend (`verify-api-contract.mjs:126-150`, `sse-parser.test.mjs:156-162`, `chat-stream-client.test.mjs`), toàn bộ bước `prepare_rag_stream` (bao gồm Corrective RAG) bắt buộc hoàn tất **trước** khi mở `StreamingResponse` để đảm bảo lỗi phiên/hạ tầng trả đúng mã HTTP `404`/`409`/`410`/`502`/`503` pre-header thay vì mở stream `200` trước. Việc chèn `event: status` thời gian thực đòi hỏi đảo ngược vòng đời pre-header và sửa đổi union/exhaustive switch trên Frontend; theo đúng quy tắc chống phức tạp hóa của `T2.4`, hạng mục này được chuyển sang **Deferred**, bảo toàn 100% hợp đồng SSE hiện hữu.

### Files thêm mới / chỉnh sửa
- **Thêm mới:**
  - `backend/app/infrastructure/logging_config.py`
  - `backend/app/infrastructure/metrics.py`
- **Chỉnh sửa:**
  - `.env.example`
  - `backend/requirements.txt`
  - `backend/app/shared/config.py`
  - `backend/app/shared/observability.py`
  - `backend/app/infrastructure/observability.py`
  - `backend/app/api/streaming/stream_metrics.py`
  - `backend/app/api/routes/chat.py`
  - `backend/app/chat/pipeline.py`
  - `backend/app/documents/excel/sql_service.py`
  - `backend/app/main.py`
  - `backend/tests/unit/test_observability.py`
  - `backend/tests/unit/test_stream_metrics.py`
  - `backend/tests/integration/test_chat_stream.py`

### Kết quả kiểm thử & Phân loại trạng thái
- **`Verified` (Kiểm chứng trực tiếp với gói `langfuse==2.60.10` & `prometheus-client==0.26.0` thật trong `.venv`):**
  - `.\.venv\Scripts\python.exe -m pip check` → **`No broken requirements found.`**
  - `.\.venv\Scripts\python.exe -m compileall -q backend/app backend/tests` → **`PASS` (0 lỗi cú pháp)**.
  - `.\.venv\Scripts\python.exe -m unittest discover -s backend/tests/architecture -t backend -v` → **`9/9 PASS` (`0.244s`)**.
  - `$env:PYTHONPATH = "backend"; .\.venv\Scripts\python.exe backend/tests/smoke/smoke_sse_schema.py` → **`PASS`**.
  - `npm.cmd --prefix frontend run test:contract` → **`PASS: 64 REST/SSE/health schemas`**.
- **`Tested` (Toàn bộ bộ kiểm thử Backend Unit & Integration):**
  - `.\.venv\Scripts\python.exe -m unittest discover -s backend/tests/unit -t backend -v` → **`350/350 PASS` (`5.822s`)** *(tăng +6 unit tests mới so với Phase 1)*.
  - `.\.venv\Scripts\python.exe -m unittest discover -s backend/tests/integration -t backend -v` → **`186/186 PASS` (`6.241s`)** *(tăng +1 integration test đa kịch bản `X-Request-ID` & `/metrics` 404 cardinality so với Phase 1)*.

---

## Phase 3 — RAG & Agent Evaluation
> **Trạng thái:** **Hoàn thành, Đã Push & Đã Merge vào `master` (`a2e541d`, 2026-11-28)** từ nhánh `feat/rag-agent-evaluation` (tách từ `master` `1984d65`) — *Đã duyệt Phương án A: Offline Plumbing Verified 100%, giữ `--live` chạy on-demand*  
> **Phạm vi:** `T3.1 Verifiable Golden Datasets` · `T3.2 Separate Correct Refusal & CustomLlmJudge` · `T3.3 Agent/SQL Evaluator (Offline vs Live)` · `T3.4 Benchmark Matrix (Config A / B / C)`

### Truy vết Chuỗi Commit (Theo `GEMINI.md` §6)
1. `197e019` — `feat(eval): add verifiable v2 RAG and Excel SQL golden datasets`
2. `c32c77f` — `feat(eval): separate refusal rate and add strict CustomLlmJudge`
3. `b812063` — `feat(eval): add agent SQL trajectory evaluator and benchmark matrix`
4. `dc8abdd` — `docs(task): update readiness roadmap and Phase 3 changelog` *(giữ `BASELINE_AUDIT.md` ở local; merged vào `master` tại `a2e541d`)*

### Quyết định thiết kế & Thay đổi thực hiện
- **T3.1 (Golden Datasets Mở Rộng & Synthetic Corpus Kiểm chứng được bằng DuckDB):**
  - Tạo 2 tài liệu mẫu giả lập 100% (không chứa dữ liệu cá nhân thật) trong `backend/evaluation/datasets/corpus/`: `hr-leave-policy.md` (12 ngày phép năm, chuyển tối đa 5 ngày trước `31/03`, thử việc 60 ngày hưởng `85%` lương) và `security-incident-sop.txt` (SLA P1 `15` phút, leo thang `30` phút, mật khẩu `12` ký tự + `MFA`, xoay vòng khóa API `90` ngày / thu hồi `5` phút).
  - Tạo `backend/evaluation/datasets/golden_set_v2.json` (**14 cases**: 10 `in_scope` đơn lượt & đa lượt `history`, 4 `out_of_scope` `expect_refusal: true`) và giữ nguyên 100% `golden_set.json` cũ cho regression test.
  - Tạo `backend/evaluation/datasets/agent_sql_golden_set.json` (**9 cases**: 2 kiểm kê kho `count_documents`/`list_documents`, 5 câu thống kê/lọc SQL trên `data/hr_employees_mock.xlsx` (`nhansu`) & `data/prompt/enterprise_it_knowledge_base.xlsx` (`knowledge_base`), và 2 câu hybrid kết hợp `run_sql` + `rag_search`), mọi đáp án số học (`10`, `234`, `23.4`, `90`, `7`, `50`, `5`) được unit test đối chiếu trực tiếp qua `extract_workbook_tables` + DuckDB `:memory:`.
- **T3.2 (Tách `correct_refusal_rate` khỏi `faithfulness`, `CustomLlmJudge` & Cấm Trộn Phương Pháp Chấm):**
  - Cập nhật `backend/evaluation/scoring/ragas_metrics.py` làm rõ thuật ngữ **RAGAS-inspired custom metrics** (không mạo nhận thư viện `ragas` PyPI chính thức), giữ nguyên tên hàm/lớp cũ cho Phase 1 tests, bổ sung `is_correct_refusal`, chỉ số bổ trợ `evaluate_groundedness_supplement` (tích hợp `EvidenceEvaluator` từ `app.chat.corrective`), và hàm `evaluate_dataset_samples` tách rạch ròi tập `in_scope` (`expect_refusal=False`) khỏi `out_of_scope` (`expect_refusal=True` → `correct_refusal_rate`).
  - Tạo `backend/evaluation/scoring/llm_judge.py` (`CustomLlmJudge`, `LlmJudgeError`): khi một mẫu bị lỗi API/timeout/JSON sau `max_retries`, `evaluate_dataset_samples(..., scoring_method="custom_llm_judge")` ghi nhận `scores=None` vào `judge_errors` (`judge_error_count`), tuyệt đối không lấy điểm heuristic điền thế vào bảng điểm LLM Judge.
- **T3.3 (Agent & Excel SQL Trajectory Evaluator — Phân tách Rõ `offline_smoke` vs `live_eval`):**
  - Tạo `backend/evaluation/scoring/agent_eval.py` (`AgentEvalCase`, `AgentTurnObservation`, `AgentTrajectoryReport`, `evaluate_agent_trajectory`) đo đủ `route_accuracy`, `tool_selection_precision`/`recall`, `sql_guard_pass_rate` (`validate_and_rewrite_sql`), `sql_execution_accuracy`, `citation_validity_rate`, `avg_agent_steps`, `p50_ms`/`p95_ms`/`ttft_p50_ms` và `total_tokens`.
  - Tạo `backend/evaluation/runner/eval_agent_cli.py`: chế độ `--mode offline_smoke` chạy luồng thật `ChatOrchestrator` + `ExcelSqlService` + `sql_guard` + `DuckDBSqlExecutor` + `DocumentQueries` trên Parquet tạm với scripted model (không mở socket mạng, đóng dấu rõ `OFFLINE_PLUMBING_CHECK — NOT VALID FOR MODEL QUALITY CLAIMS` và `valid_for_model_quality=False`); chế độ `--mode live_eval` có `validate_live_eval_collection()` chặn cứng `rag_documents` của ứng dụng chính.
- **T3.4 (Benchmark Matrix Config A / B / C & Ước tính Lượt Gọi Provider trước Live):**
  - Cập nhật docstring & tiêu đề báo cáo tại `backend/evaluation/runner/baseline_eval.py` làm rõ bản chất *Offline Deterministic Baseline (RAGAS-Inspired Custom Heuristic Metrics)*.
  - Tạo `backend/evaluation/runner/benchmark_matrix.py` định nghĩa đúng 3 cấu hình (`Config A` Advanced RAG, `Config B` + Corrective RAG, `Config C` Agentic + Excel SQL; khóa `semantic_cache_enabled=False` trên cả 3), phân bổ bảng ngang (`A`, `B`, `C`) trên `golden_set_v2.json` và bảng chuyên biệt (`C`) trên `agent_sql_golden_set.json`, kèm hàm `estimate_live_provider_calls()` (**138 lượt gọi Groq** có `CustomLlmJudge` / **96 lượt** không Judge, và **83 lượt gọi Gemini Embedding** trên `rag_documents_eval`) cùng renderer `render_final_evaluation_markdown()` từ chối xuất `FINAL-EVALUATION-REPORT.md` từ dữ liệu offline giả lập.

### Files thêm mới / chỉnh sửa
- **Thêm mới:**
  - `backend/evaluation/datasets/corpus/hr-leave-policy.md`
  - `backend/evaluation/datasets/corpus/security-incident-sop.txt`
  - `backend/evaluation/datasets/golden_set_v2.json`
  - `backend/evaluation/datasets/agent_sql_golden_set.json`
  - `backend/evaluation/scoring/llm_judge.py`
  - `backend/evaluation/scoring/agent_eval.py`
  - `backend/evaluation/runner/eval_agent_cli.py`
  - `backend/evaluation/runner/benchmark_matrix.py`
  - `backend/tests/unit/test_agent_evaluation.py`
- **Chỉnh sửa:**
  - `backend/evaluation/scoring/ragas_metrics.py`
  - `backend/evaluation/runner/baseline_eval.py`
  - `backend/tests/unit/test_ragas_metrics.py`

### Kết quả kiểm thử & Phân loại trạng thái
- **`Verified` (Kiểm chứng đường ống kỹ thuật Offline Plumbing Check — Không thay thế Live LLM Quality):**
  - `$env:PYTHONPATH = "backend"; .\.venv\Scripts\python.exe -m evaluation.runner.eval_agent_cli --mode offline_smoke` → **`PASS`** (`[OFFLINE_PLUMBING_CHECK — NOT VALID FOR MODEL QUALITY CLAIMS]`, `9/9 cases`, `route_accuracy=1.0`, `tool_selection_precision=1.0`, `tool_selection_recall=1.0`, `sql_guard_pass_rate=1.0`, `sql_execution_accuracy=1.0`, `citation_validity_rate=1.0`).
  - `$env:PYTHONPATH = "backend"; .\.venv\Scripts\python.exe -m evaluation.runner.benchmark_matrix --offline-check` → **`PASS`** (`valid_for_model_quality=false`, `text_rag_correct_refusal_rate=1.0`, `horizontal_dataset_configs=["A","B","C"]`, `specialized_sql_configs=["C"]`).
  - `.\.venv\Scripts\python.exe -m pip check` → **`No broken requirements found.`**
  - `.\.venv\Scripts\python.exe -m compileall -q backend/app backend/evaluation backend/tests` → **`PASS` (0 lỗi cú pháp)**.
  - `.\.venv\Scripts\python.exe -m unittest backend/tests/architecture/test_dependency_rules.py -v` → **`9/9 PASS`**.
  - `npm.cmd --prefix frontend run test:contract` → **`PASS: 64 REST/SSE/health schemas`**.
- **`Tested` (Toàn bộ bộ kiểm thử Backend Unit & Integration không gọi mạng):**
  - `Set-Location backend; ..\.venv\Scripts\python.exe -m unittest discover -s tests/unit -v` → **`357/357 PASS` (`7.184s`)** *(tăng +7 unit tests mới cho Phase 3 so với 350 ở Phase 2)*.
  - `Set-Location backend; ..\.venv\Scripts\python.exe -m unittest discover -s tests/integration -v` → **`186/186 PASS` (`6.409s`)**.
- **`On-Demand Live Gate` (Phương án A đã phê duyệt cho `T3.4`):**
  - Người dùng đã chốt không gọi live Groq/Gemini ở giai đoạn này để tiết kiệm quota. Khi cần xuất báo cáo thực chứng tại `docs/evaluation/FINAL-EVALUATION-REPORT.md`, chạy `python -m evaluation.runner.benchmark_matrix --live --approve-live --qdrant-collection rag_documents_eval` (ước tính **138 lượt gọi Groq** có `CustomLlmJudge` / **96 lượt** không Judge, và **83 lượt gọi Gemini Embedding**).

---

## Phase 4 — Deployment & Testing
> **Trạng thái:** **Hoàn thành & Đã Commit (2026-11-28)** trên nhánh `chore/deployment-and-testing` (tách từ `master` `a2e541d`)  
> **Phạm vi:** `T4.1 Hardened Dockerfiles & .dockerignore` · `T4.2 Unified Local/Demo docker-compose & ARQ Worker` · `T4.3 Classify 16 smoke_*.py & Playwright E2E (/hr, Scope Selector)` · `T4.4 CI Upgrade & Dependency Advisory Review`

### Truy vết Chuỗi Commit (Theo `GEMINI.md` §6)
1. `512bd7b` — `build(docker): harden multi-stage Dockerfiles and enable Next.js standalone`
2. `2969aa0` — `chore(compose): add ARQ worker, localhost binds, and local Qdrant HTTP flag`
3. `eeda989` — `test(e2e): move 16 cloud smoke scripts and add HR Portal and scope E2E`
4. `9aedf71` — `ci(workflows): add advanced flags, Playwright E2E, Docker, and audits`
5. *(Commit hiện tại)* — `docs(task): update readiness roadmap and Phase 4 changelog` *(giữ `BASELINE_AUDIT.md` ở local)*

### Quyết định thiết kế & Thay đổi thực hiện
- **T4.1 (Hardening `backend/Dockerfile`, `frontend/Dockerfile`, `next.config.ts` & `.dockerignore`):**
  - **`backend/Dockerfile`:** Chuyển sang multi-stage build (`builder` trên `python:3.12-slim` cài `build-essential`, tạo `/opt/venv` và tải sẵn extension DuckDB `httpfs` vào `/opt/duckdb-home/.duckdb`; `runner` trên `python:3.12-slim` sạch không còn `build-essential`, chạy dưới user non-root `appuser`, copy `.duckdb` sang `/home/appuser/.duckdb`, xác thực ngay lúc build `SET autoinstall_known_extensions=false; LOAD httpfs;` dưới quyền `appuser`, kèm `HEALTHCHECK` gọi `/health`).
  - **`frontend/next.config.ts` & `frontend/Dockerfile`:** Bật `output: "standalone"` theo tài liệu đi kèm của Next.js 16 (`output.md`); stage `runner` trên `node:20-alpine` chỉ copy `public`, `.next/standalone`, `.next/static`, chạy dưới non-root `nextjs` (`uid=1001`), loại bỏ toàn bộ `devDependencies` (Playwright, ESLint, TypeScript), kèm `HEALTHCHECK` kiểm tra `http://127.0.0.1:3000/chat` và khởi chạy `node server.js`. Cập nhật `frontend/scripts/build-e2e.mjs` (tự động copy `.next/static` & `public` vào `.next/standalone/`) và `frontend/playwright.config.ts` chạy `node .next/standalone/server.js` để kiểm chứng trực tiếp Next.js standalone trên cả `/chat` và `/hr/*`.
  - Tạo `.dockerignore` ở root và `frontend/.dockerignore` loại trừ `.git`, `.venv`, `node_modules`, `.next`, `.env*`, `data/documents/*`, `BASELINE_AUDIT.md`, `docs/`, `task/`.
- **T4.2 (Một Bộ `docker-compose.yml` Duy Nhất cho Local & Demo + `QDRANT_ALLOW_INSECURE_HTTP`):**
  - Hoàn thiện `docker-compose.yml` (không tạo `docker-compose.prod.yml`): bổ sung service `worker` (`python -m arq app.workers.ingestion_worker.WorkerSettings`, dùng chung image `backend`), ghim tag cố định `qdrant/qdrant:v1.13.6` (thay cho `:latest`), bind toàn bộ cổng hạ tầng nội bộ (`6379`, `6333`, `27017`) vào `127.0.0.1`, bổ sung `restart: unless-stopped` và `healthcheck` cho cả 6 services (`backend`, `worker`, `frontend`, `redis`, `qdrant`, `mongo`).
  - Bổ sung `qdrant_allow_insecure_http: bool = False` trong `backend/app/shared/config.py` và `.env.example`, giữ mặc định bắt buộc `https://` cho Qdrant Cloud và chỉ cho phép `http://qdrant:6333` khi bật tường minh cho `local-infra`; thêm unit test `test_qdrant_url_validator_blocks_http_unless_insecure_flag_enabled` tại `backend/tests/unit/test_cloud_connections.py`.
- **T4.3 (Kiểm toán & Phân loại 16 Legacy `smoke_*.py` + Bổ sung 2 Playwright E2E Specs):**
  - Toàn bộ **16/16** file `smoke_*.py` trong `backend/tests/integration/` đã được kiểm toán AST/import thực tế và phân loại minh bạch: **0/16** là Offline thuần túy (mọi kịch bản offline tương đương đã nằm trong 20 file `test_*.py`), **10/16** thuộc **Nhóm (B) Cloud-dependent** (cần MongoDB Atlas / Qdrant Cloud thật, mock LLM) và **6/16** thuộc **Nhóm (C) Live-provider** (gọi thật Google Gemini Embedding / Groq LLM + Cloud DB). Toàn bộ 16 file đã được `git mv` sang `backend/tests/smoke/` kèm docstring cảnh báo rõ điều kiện chạy (`DO NOT RUN IN OFFLINE CI`), đưa `backend/tests/integration/` về 100% test offline chuẩn cho `unittest discover`:

| File | Nhóm | Phụ thuộc thực tế | Hành động |
| :--- | :---: | :--- | :--- |
| `smoke_conversation_models.py` | **(B) Cloud-dependent** | MongoDB Atlas (`MongoDBConnection`) | Chuyển → `backend/tests/smoke/` + warning docstring |
| `smoke_history_loader.py` | **(B) Cloud-dependent** | MongoDB Atlas (`MongoDBConnection`) | Chuyển → `backend/tests/smoke/` + warning docstring |
| `smoke_message_persistence.py` | **(B) Cloud-dependent** | `TestClient(app)` + Atlas lifespan (mock LLM) | Chuyển → `backend/tests/smoke/` + warning docstring |
| `smoke_response_contract.py` | **(B) Cloud-dependent** | `TestClient(app)` + Atlas lifespan (mock LLM) | Chuyển → `backend/tests/smoke/` + warning docstring |
| `smoke_session_api.py` | **(B) Cloud-dependent** | `TestClient(app)` + Atlas lifespan (mock LLM) | Chuyển → `backend/tests/smoke/` + warning docstring |
| `smoke_session_concurrency.py` | **(B) Cloud-dependent** | `TestClient(app)` + Atlas concurrency guard | Chuyển → `backend/tests/smoke/` + warning docstring |
| `smoke_stream_endpoint.py` | **(B) Cloud-dependent** | `TestClient(app)` + Cloud readiness (mock stream) | Chuyển → `backend/tests/smoke/` + warning docstring |
| `smoke_stream_errors.py` | **(B) Cloud-dependent** | `TestClient(app)` + Atlas lifespan (mock stream) | Chuyển → `backend/tests/smoke/` + warning docstring |
| `smoke_stream_lifecycle.py` | **(B) Cloud-dependent** | `TestClient(app)` + Atlas lifespan (mock stream) | Chuyển → `backend/tests/smoke/` + warning docstring |
| `smoke_stream_metrics.py` | **(B) Cloud-dependent** | `TestClient(app)` + Atlas lifespan (mock stream) | Chuyển → `backend/tests/smoke/` + warning docstring |
| `smoke_citation_mapping.py` | **(C) Live-provider** | MongoDB Atlas + Qdrant Cloud + Gemini Embedding | Chuyển → `backend/tests/smoke/` + warning docstring |
| `smoke_document_api.py` | **(C) Live-provider** | `TestClient(app)` + Atlas + Qdrant + Gemini Embedding | Chuyển → `backend/tests/smoke/` + warning docstring |
| `smoke_ingestion.py` | **(C) Live-provider** | `create_ingestion_service` + Atlas + Qdrant + Gemini | Chuyển → `backend/tests/smoke/` + warning docstring |
| `smoke_qdrant_ingestion.py` | **(C) Live-provider** | Qdrant Cloud + `get_embeddings().embed_documents()` | Chuyển → `backend/tests/smoke/` + warning docstring |
| `smoke_rag_integration.py` | **(C) Live-provider** | Atlas + Qdrant + `prepare_rag_stream` (Gemini/Groq) | Chuyển → `backend/tests/smoke/` + warning docstring |
| `smoke_vector_adapter.py` | **(C) Live-provider** | Qdrant Cloud + `get_embeddings()` (`embed_documents`/`query`) | Chuyển → `backend/tests/smoke/` + warning docstring |

  - Bổ sung 2 Playwright E2E specs mới chạy trên Next.js standalone `server.js`:
    - `frontend/e2e/hr-portal.spec.mts`: kiểm thử `/hr` (theme `.hr-theme` + Live KB), mở `HrChatbotWidget` hội thoại đa lượt xuyên trang `/hr` → `/hr/documents` (lọc tab danh mục, tìm kiếm, xem trước preview) → `/hr/guide` trên cùng 1 `surface: "hr"` session, và xác nhận tách biệt hoàn toàn khi chuyển về `/chat`.
    - `frontend/e2e/document-scope.spec.mts`: kiểm thử chuyển đổi `ALL_ACTIVE` → `SELECTED_DOCUMENTS` (`PATCH /sessions/:id/scope`), reload giữ nguyên scope, và đặt lại về `ALL_ACTIVE`.
- **T4.4 (Nâng cấp GitHub Actions CI & Biên bản Review Dependency Security Audit):**
  - **`.github/workflows/backend-ci.yml`:** Bổ sung bước chạy kiểm thử dưới tổ hợp feature flags nâng cao (`TOOL_USE_ENABLED=true`, `AGENTIC_MODE_ENABLED=true`, `CORRECTIVE_RAG_ENABLED=true`, `EXCEL_PARQUET_INGESTION_ENABLED=true`, `EXCEL_SQL_ENABLED=true`, `HYBRID_SEARCH_ENABLED=true`, `RERANKER_ENABLED=true`) cùng `eval_agent_cli --mode offline_smoke` và `benchmark_matrix --offline-check`, bước `docker compose config` (`default` & `local-infra`), bước `docker build` Backend + kiểm tra `id -u != 0`, và bước `pip-audit` xuất báo cáo advisory vào `$GITHUB_STEP_SUMMARY`.
  - **`.github/workflows/frontend-ci.yml`:** Bổ sung `npm audit --omit=dev`, Playwright Chromium E2E (`npm run build:e2e && npm run test:e2e`), và `docker build` Frontend + kiểm tra `id -u != 0` (giữ nguyên tên job để khớp Branch Protection).
  - **Biên bản Review Dependency Security Audit (Không tự ý chạy `npm audit fix --force` hay ép nâng cấp phá vỡ ràng buộc):**
    - **Frontend (`npm.cmd --prefix frontend audit --omit=dev`):** **`0 vulnerabilities`** (`package-lock.json` đã khóa `next@16.4.6`; lưu ý `node_modules/next` cục bộ trên máy phát triển cũ hơn `16.4.0`, chạy `npm.cmd ci` sẽ đồng bộ lên `16.4.6`).
    - **Backend (Quét toàn bộ `165` gói Python đang cài qua OSV.dev):** Phát hiện **2 gói** có cảnh báo:
      1. `unstructured==0.21.5`: `GHSA-4mvj-m6j5-pmf7` / `PYSEC-2026-3930` (**CRITICAL**, SSRF ở hàm `partition(url=...)`, bản vá `0.24.0`) và `GHSA-v5mq-3xhg-98m9` (**MODERATE**, Stored XSS trong xuất HTML, bản vá `0.24.1`). *Đánh giá rủi ro thực tế:* Mã nguồn `backend/app/rag/loaders/` chỉ đọc file cục bộ đã tải lên (không bao giờ truyền URL từ người dùng vào `unstructured`, không render HTML xuất từ `unstructured`). Bản vá `0.24.1` hiện đòi `wrapt>=2.1.1`, xung đột với `langfuse<3.0.0` (`wrapt<2.0.0`) đang dùng; giữ nguyên có kiểm soát và đề xuất theo dõi để nâng cấp khi chuyển `langfuse>=3` hoặc thay thế `unstructured`.
      2. `filelock==3.32.7` (transitive, **LOW**, `GHSA-567q-5qvw-pf92` và nhóm cảnh báo SoftFileLock Windows oplock, bản vá `4.2.1`): Không nằm trên hot-path request; có thể nâng cấp ở đợt làm mới dependency riêng.

### Files thêm mới / chỉnh sửa / di chuyển
- **Thêm mới:**
  - `.dockerignore`
  - `frontend/.dockerignore`
  - `frontend/e2e/hr-portal.spec.mts`
  - `frontend/e2e/document-scope.spec.mts`
- **Chỉnh sửa:**
  - `backend/Dockerfile`
  - `frontend/Dockerfile`
  - `frontend/next.config.ts`
  - `frontend/scripts/build-e2e.mjs`
  - `frontend/playwright.config.ts`
  - `docker-compose.yml`
  - `.env.example`
  - `backend/app/shared/config.py`
  - `backend/tests/unit/test_cloud_connections.py`
  - `.github/workflows/backend-ci.yml`
  - `.github/workflows/frontend-ci.yml`
- **Di chuyển (16 legacy cloud/live smoke scripts):**
  - `backend/tests/integration/smoke_*.py` (16 files) → `backend/tests/smoke/smoke_*.py` (kèm docstring phân loại & cảnh báo)

### Kết quả kiểm thử & Phân loại trạng thái
- **`Verified` (Chạy thực tế không gọi cloud/provider):**
  - `docker compose config --quiet` & `docker compose --profile local-infra config --quiet` → **`PASS`** (`6 services`: `backend`, `worker`, `frontend`, `redis`, `qdrant`, `mongo`). *(Lưu ý: Docker Desktop daemon không bật trên máy local nên `docker build` thực thi trong GitHub Actions CI).*
  - `.\.venv\Scripts\python.exe -m unittest discover -s backend/tests/architecture -t backend -v` → **`9/9 PASS` (`0.234s`)**.
  - `.\.venv\Scripts\python.exe -m compileall -q backend/app backend/tests backend/evaluation backend/scripts` & `pip check` → **`PASS`** (`No broken requirements found.`).
  - 3 Offline Smoke Scripts (`smoke_sse_schema.py`, `smoke_context_budget.py`, `smoke_query_rewriting.py`) → **`3/3 PASS`**.
  - Advanced Feature Flags CI Matrix (`TOOL_USE_ENABLED`, `AGENTIC_MODE_ENABLED`, `CORRECTIVE_RAG_ENABLED`, `EXCEL_PARQUET_INGESTION_ENABLED`, `EXCEL_SQL_ENABLED`, `HYBRID_SEARCH_ENABLED`, `RERANKER_ENABLED` = `true`) → **`55/55 PASS` (`4.259s`)**.
  - YAML syntax validation cho `.github/workflows/{backend-ci,frontend-ci}.yml` → **`PASS`**.
  - `npm.cmd --prefix frontend audit --omit=dev` → **`found 0 vulnerabilities`**.
  - `npm.cmd --prefix frontend run typecheck` & `npm.cmd --prefix frontend run lint` → **`PASS`**.
  - `npm.cmd --prefix frontend run test:contract` → **`PASS: 64 REST/SSE/health schemas`**.
  - `npm.cmd --prefix frontend test` → **`238/238 PASS` (`11.09s`)**.
  - `npm.cmd --prefix frontend run build:e2e` → **`PASS`** (`output: "standalone"` sinh `.next/standalone/server.js`, prerender `10/10` routes bao gồm `/chat`, `/hr`, `/hr/documents`, `/hr/guide`).
  - Playwright Chromium E2E trên **Next.js standalone `server.js`** (`npm.cmd --prefix frontend run test:e2e`): **`71/71 PASS`** trên đủ 10 specs (`69/69` tests cũ + `document-scope.spec.mts` + `hr-portal.spec.mts`).
- **`Tested` (Toàn bộ bộ kiểm thử Backend Unit & Integration):**
  - `Set-Location backend; ..\.venv\Scripts\python.exe -m unittest discover -s tests/unit -v` → **`358/358 PASS` (`9.778s`)** *(tăng +1 unit test mới cho `QDRANT_ALLOW_INSECURE_HTTP` so với 357 ở Phase 3)*.
  - `Set-Location backend; ..\.venv\Scripts\python.exe -m unittest discover -s tests/integration -v` → **`186/186 PASS` (`8.280s`)** *(100% 20 file offline `test_*.py`, không còn `smoke_*.py` lẫn trong `integration/`)*.

---

## Phase 5 — Documentation & Demo
> **Trạng thái:** Chưa bắt đầu  
> **Phạm vi:** `T5.1 Verified-Only Documentation Sync` · `T5.2 Safe Demo Seed Script (--dry-run, Isolated Collection, Zero PII) & Demo Runbook`

### Quyết định thiết kế & Thay đổi thực hiện
- **T5.1:** *(chờ cập nhật)*
- **T5.2:** *(chờ cập nhật)*

### Files thêm mới / chỉnh sửa
- **Thêm mới:** *(chờ cập nhật)*
- **Chỉnh sửa:** *(chờ cập nhật)*

### Kết quả kiểm thử & Nghiệm thu Cuối cùng
- *(chờ cập nhật)*
