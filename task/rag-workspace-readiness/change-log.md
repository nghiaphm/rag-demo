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
| **Phase 0** — Pre-Stage Stabilization | `T0.1` – `T0.4` | **Hoàn thành** (`Tested` & `Verified` offline) | `78c400c`, `76689e4`, `23cd072`, `911ac10`, `841b1dd`, `113ea17`, `0e7ab32` | Arch `9/9`, Unit `338/338`, Integration `183/183`, Smoke `3/3`, OpenAPI `63` schemas PASS |
| **Phase 1** — Reliability *(No Auth/Cache)* | `T1.1` – `T1.3` | Chưa bắt đầu | *(chờ thực thi)* | *(chờ cập nhật)* |
| **Phase 2** — Observability | `T2.1` – `T2.4` | Chưa bắt đầu | *(chờ thực thi)* | *(chờ cập nhật)* |
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
> **Trạng thái:** Chưa bắt đầu  
> **Phạm vi:** `T1.1 Non-destructive Health (Required vs Optional)` · `T1.2 Upload Size Cap, Redis Failure Policy & Trusted Proxy IP` · `T1.3 Provider Timeouts, SecretStr, Dynamic CORS, Security Headers & Startup Guard`

### Quyết định thiết kế & Thay đổi thực hiện
- **T1.1:** *(chờ cập nhật)*
- **T1.2:** *(chờ cập nhật)*
- **T1.3:** *(chờ cập nhật)*

### Files thêm mới / chỉnh sửa
- **Thêm mới:** *(chờ cập nhật)*
- **Chỉnh sửa:** *(chờ cập nhật)*

### Kết quả kiểm thử & Phân loại trạng thái
- *(chờ cập nhật)*

---

## Phase 2 — Observability
> **Trạng thái:** Chưa bắt đầu  
> **Phạm vi:** `T2.1 JSON Logging & Validated X-Request-ID` · `T2.2 Langfuse SDK Compatibility & Redaction` · `T2.3 prometheus-client Low-Cardinality /metrics` · `T2.4 Conditional SSE Status Events Gate`

### Quyết định thiết kế & Thay đổi thực hiện
- **T2.1:** *(chờ cập nhật)*
- **T2.2:** *(chờ cập nhật)*
- **T2.3:** *(chờ cập nhật)*
- **T2.4:** *(Ghi rõ kết quả Decision Gate: đã tích hợp additive hay chuyển sang Deferred kèm lý do)*

### Files thêm mới / chỉnh sửa
- **Thêm mới:** *(chờ cập nhật)*
- **Chỉnh sửa:** *(chờ cập nhật)*

### Kết quả kiểm thử & Phân loại trạng thái
- *(chờ cập nhật)*

---

## Phase 3 — RAG & Agent Evaluation
> **Trạng thái:** Chưa bắt đầu  
> **Phạm vi:** `T3.1 Verifiable Golden Datasets` · `T3.2 Separate Correct Refusal & CustomLlmJudge` · `T3.3 Agent/SQL Evaluator (Offline vs Live)` · `T3.4 Benchmark Matrix (Config A / B / C)`

### Quyết định thiết kế & Thay đổi thực hiện
- **T3.1:** *(chờ cập nhật)*
- **T3.2:** *(chờ cập nhật)*
- **T3.3:** *(chờ cập nhật)*
- **T3.4:** *(chờ cập nhật)*

### Files thêm mới / chỉnh sửa
- **Thêm mới:** *(chờ cập nhật)*
- **Chỉnh sửa:** *(chờ cập nhật)*

### Kết quả kiểm thử & Phân loại trạng thái
- *(Ghi rõ kết quả Offline Plumbing Check tách biệt với Live Evaluation sau khi được duyệt chạy)*

---

## Phase 4 — Deployment & Testing
> **Trạng thái:** Chưa bắt đầu  
> **Phạm vi:** `T4.1 Hardened Dockerfiles & .dockerignore` · `T4.2 Unified Local/Demo docker-compose & ARQ Worker` · `T4.3 Classify 16 smoke_*.py & Playwright E2E (/hr, Scope Selector)` · `T4.4 CI Upgrade & Dependency Advisory Review`

### Quyết định thiết kế & Thay đổi thực hiện
- **T4.1:** *(chờ cập nhật)*
- **T4.2:** *(chờ cập nhật)*
- **T4.3:** *(Đính kèm bảng phân loại 16 file `smoke_*.py` vào Offline / Cloud-dependent / Live-provider và kết quả E2E)*
- **T4.4:** *(Đính kèm tóm tắt review `pip-audit` & `npm audit --omit=dev`)*

### Files thêm mới / chỉnh sửa / di chuyển
- **Thêm mới:** *(chờ cập nhật)*
- **Chỉnh sửa / Di chuyển:** *(chờ cập nhật)*

### Kết quả kiểm thử & Phân loại trạng thái
- *(chờ cập nhật)*

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
