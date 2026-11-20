# Excel SQL Analytics (S3 + Parquet + DuckDB) — Implementation Change Log

Tài liệu này ghi nhận toàn bộ lịch sử thay đổi, quyết định thiết kế, danh sách file thêm mới/chỉnh sửa và kết quả kiểm thử qua từng giai đoạn khi triển khai kiến trúc lưu trữ S3 + Parquet + Catalog + DuckDB SQL cho file Excel trong RAG Workspace & HR Portal.

---

## Baseline (Pre-Phase 1) — Trạng thái trước khi bắt đầu
- **Thời điểm lập kế hoạch:** 2026-11-20 (nhánh hiện tại `feat/context-aware-hr-assistant` tại `9119114`, `master` tại `2c1e556`).
- **Hiện trạng luồng upload & xử lý Excel (`.xlsx`):**
  - **Validate:** Frontend (`frontend/lib/documents/upload-validation.ts`) và Backend (`backend/app/api/routes/documents.py::_read_upload` + `backend/app/documents/excel/validation.py::read_workbook`) giới hạn `≤ 10 MiB`, giải nén `≤ 64 MiB`, chặn macro/zip-bomb, tối đa `50` sheets, `20.000` hàng, `200` cột, `250.000` ô, mở ở chế độ `read_only=True, data_only=False, keep_links=False`.
  - **Storage & Metadata:** `backend/app/documents/ports.py` định nghĩa `FileStorage` + key `documents/{doc_id}/{ver_id}/original`; `backend/app/infrastructure/storage.py` chỉ hỗ trợ `LocalFileStorage` (`STORAGE_BACKEND=local`); MongoDB lưu `documents`, `document_versions`, `ingestion_jobs` (chưa có `tenant_id` và chưa có collection catalog bảng).
  - **Ingestion & Indexing:** `IngestionService` chạy sync (`201`) hoặc async qua ARQ (`202`, theo `ASYNC_INGESTION_ENABLED`); `backend/app/rag/loaders/excel.py::workbook_documents` biến từng hàng Excel thành text `Document` → splitter → Gemini embedding (`gemini-embedding-001`) → Qdrant; hiện bắt buộc `len(chunks) > 0` ở cả `_process` và `reconcile_processing`.
  - **Truy vấn hiện hữu:** Preview cắt giới hạn `50` hàng/sheet (`backend/app/documents/excel/preview.py`); truy vấn bảng trong `agent_tools.py` mới có `query_excel_table` đọc on-demand bằng `openpyxl` (`backend/app/documents/excel/query.py`), chưa có Parquet, chưa có DuckDB SQL và chưa có phân quyền theo user/tenant trong `ChatOrchestrator`.
- **Trạng thái kế hoạch:** Đã lưu lộ trình 4 giai đoạn vào `task/excel-sql-duckdb/Task.md`, đang chờ xét duyệt (`APPROVE`) và chốt các câu hỏi thiết kế trước khi bắt đầu Giai đoạn 1.

---

## Giai đoạn 1 — `StorageBackend` (Local & S3) và chuyển lưu file gốc lên S3
> **Trạng thái**: Hoàn thành  
> **Phạm vi**: `StorageBackend Protocol` · `LocalFileStorage` · `S3FileStorage` · `Versioned Key {tenant}/{doc_id}/v{n}/original.xlsx` · `Per-version storage_backend routing`

### Thay đổi đã thực hiện
- **T1.1 (`8789a8a`)**:
  - Khai báo `StorageBackend(Protocol)` (`put`, `get`, `exists`, `delete_prefix`) và hàm `build_versioned_storage_key(tenant_id, document_id, version, file_name)` sinh key `{tenant}/{doc_id}/v{n}/original{ext}` (Excel là `original.xlsx`) trong `backend/app/documents/ports.py`.
  - Thêm `tenant_id: str = "default"` vào `DocumentRecord` và `UserContext`/`UserRecord`; thêm `storage_backend: Literal["local", "s3"] = "local"` vào `DocumentVersionRecord` (bản ghi cũ mặc định `"local"`).
  - Mở rộng `backend/app/shared/config.py` và `.env.example` hỗ trợ `STORAGE_BACKEND=local|s3`, `DEFAULT_TENANT_ID="default"`, `S3_BUCKET`, `S3_REGION`, `S3_ENDPOINT_URL`, `S3_INGEST_ACCESS_KEY_ID`, `S3_INGEST_SECRET_ACCESS_KEY`, `S3_USE_IF_NONE_MATCH=true`.
- **T1.2 (`fab6b8b`)**:
  - Tạo `backend/app/infrastructure/s3_storage.py` (`S3FileStorage`): hỗ trợ `put` bất biến với `IfNoneMatch="*"` hoặc fallback `head_object` theo cấu hình `S3_USE_IF_NONE_MATCH`, `get`, `open`, `exists`, `delete`, `delete_prefix` phân trang theo batch 1000; chuẩn hóa thông báo lỗi an toàn không lộ access key/secret hay endpoint.
  - Bổ sung `delete_prefix` cho `LocalFileStorage` và cập nhật factory `create_file_storage(config, *, backend=..., s3_client=...)` trong `backend/app/infrastructure/storage.py`.
  - Pin `boto3>=1.35.4,<2.0.0` trong `backend/requirements.txt`.
- **T1.3 (`1413e08`)**:
  - Cập nhật `IngestionService._prepare_upload` sinh key `{tenant}/{doc_id}/v{n}/original{ext}`, gắn `tenant_id` qua `UserContext.tenant_id`, ghi nhận `version.storage_backend` và rollback xóa object nếu ghi MongoDB lỗi.
  - Cập nhật `IngestionService._materialize_and_split`, `DocumentService.reindex` và `attachments.py::preview_version` tự động chọn đúng backend theo `version.storage_backend` thông qua `resolve_storage`.
- **T1.4**:
  - Thêm unit tests `backend/tests/unit/test_storage_backends.py` và integration tests `backend/tests/integration/test_s3_upload_flow.py`.

### Files thêm mới / chỉnh sửa
- **Thêm mới:** `backend/app/infrastructure/s3_storage.py`, `backend/tests/unit/test_storage_backends.py`, `backend/tests/integration/test_s3_upload_flow.py`.
- **Chỉnh sửa:** `.env.example`, `backend/requirements.txt`, `backend/app/shared/config.py`, `backend/app/shared/auth.py`, `backend/app/api/dependencies/auth.py`, `backend/app/documents/models.py`, `backend/app/documents/ports.py`, `backend/app/documents/ingestion.py`, `backend/app/documents/service.py`, `backend/app/documents/attachments.py`, `backend/app/api/routes/documents.py`, `backend/app/infrastructure/storage.py`.

### Kết quả kiểm thử
- `python -m unittest tests/architecture/test_dependency_rules.py -v`: **9/9 PASS**
- `python -m unittest tests/unit/test_storage.py tests/unit/test_storage_backends.py tests/unit/test_document_models.py -v`: **29/29 PASS** (`test_storage`: 10, `test_storage_backends`: 9, `test_document_models`: 10)
- `python -m unittest tests/integration/test_s3_upload_flow.py tests/integration/test_ingestion.py tests/integration/test_documents_api.py tests/integration/test_message_attachments_excel.py -v`: **35/35 PASS** (`test_s3_upload_flow`: 4, `test_ingestion`: 13, `test_documents_api`: 4, `test_message_attachments_excel`: 14)

---

## Giai đoạn 2 — Ingest Excel thành Parquet trên S3 + Table Catalog MongoDB
> **Trạng thái**: Hoàn thành  
> **Phạm vi**: `Sheet Normalization` · `PyArrow Parquet` · `S3 tables/*.parquet` · `MongoDB Table Catalog` · `EXCEL_PARQUET_INGESTION_ENABLED`

### Thay đổi đã thực hiện
- **T2.1 (`90a0d85`)**:
  - Tạo `backend/app/documents/excel/tabular.py` (`extract_workbook_tables`, `normalize_table_name`, `normalize_column_name`):
    - Tái sử dụng `read_workbook()` để giữ nguyên 100% giới hạn an toàn (10 MiB, 64 MiB expanded, 50 sheet, 20.000 dòng, 200 cột, 250.000 ô, 32.767 ký tự/ô, chặn macro/zip-bomb).
    - Đọc cached value cho ô công thức (`data_only=True, read_only=True, keep_links=False`); ô công thức không có cached value hoặc lỗi công thức được gán `NULL` và bật cờ `has_formula_values=True` trên cả cột và bảng.
    - Dò dòng header tự động (bỏ dòng trống/tiêu đề đơn lẻ, chọn dòng đầu tiên có ≥ 2 ô text khác nhau; bỏ qua sheet không có dữ liệu).
    - Chuẩn hóa tên bảng và tên cột về `snake_case` ASCII duy nhất khớp `[a-z][a-z0-9_]{0,62}` (cột trống -> `col_{index}`), lưu `sheet_name` và `original_name`.
    - Suy luận kiểu dữ liệu theo cột (`INT64`, `DOUBLE`, `BOOLEAN`, `DATE`, `TIMESTAMP`, `VARCHAR`), bảo toàn mã bắt đầu bằng số 0 (`"00123"`), số nguyên lớn và định dạng số kiểu VN (`"1.250.000,5"`) khi nhất quán 100%.
    - Sinh mô tả cột theo rule, cắt `sample_rows` theo giới hạn (mỗi ô ≤ 100 ký tự) và xuất Parquet bytes bằng `pyarrow`.
  - Thêm `pyarrow>=17.0.0` vào `backend/requirements.txt`.
- **T2.2 (`a60e2cc`)**:
  - Thêm `TableColumnSchema` và `DocumentTableCatalogRecord` (collection `document_table_catalogs`) vào `backend/app/documents/models.py`.
  - Thêm index unique `(version_id, table_name)` và index `(tenant_id, document_id, version_id)` vào `backend/app/documents/indexes.py`.
  - Thêm `replace_version_tables`, `list_tables_for_versions`, `delete_tables_for_version` vào `backend/app/documents/repository.py`.
- **T2.3 (`0f6f002`)**:
  - Thêm cờ `EXCEL_PARQUET_INGESTION_ENABLED=false` và `EXCEL_CATALOG_SAMPLE_ROWS=3` vào `backend/app/shared/config.py` và `.env.example`.
  - Thêm `build_version_tables_prefix` và `build_version_table_parquet_key` vào `backend/app/documents/ports.py`.
  - Tích hợp `_ingest_excel_parquet_and_catalog` và `_cleanup_version_parquet_and_catalog` vào `IngestionService._process` & `_fail_before_activation` (đảm bảo idempotent khi retry, thứ tự `sinh bảng -> ghi Parquet -> lưu catalog -> verify số Parquet == số bảng catalog`, cleanup an toàn khi lỗi mà không chạm version đang active, và hỗ trợ `reindex`).
- **T2.4**:
  - Thêm unit tests `backend/tests/unit/test_excel_tabular.py` và integration tests `backend/tests/integration/test_excel_parquet_ingestion.py`.

### Files thêm mới / chỉnh sửa
- **Thêm mới:** `backend/app/documents/excel/tabular.py`, `backend/tests/unit/test_excel_tabular.py`, `backend/tests/integration/test_excel_parquet_ingestion.py`.
- **Chỉnh sửa:** `.env.example`, `backend/requirements.txt`, `backend/app/shared/config.py`, `backend/app/documents/models.py`, `backend/app/documents/indexes.py`, `backend/app/documents/repository.py`, `backend/app/documents/ports.py`, `backend/app/documents/ingestion.py`.

### Kết quả kiểm thử
- `python -m unittest tests/architecture/test_dependency_rules.py -v`: **9/9 PASS**
- `python -m unittest tests/unit/test_excel_tabular.py -v`: **6/6 PASS**
- `python -m unittest tests/integration/test_excel_parquet_ingestion.py -v`: **6/6 PASS**

---

## Giai đoạn 3 — Tool `run_sql` (DuckDB In-Memory + `sqlglot` + RBAC + S3 Read-Only)
> **Trạng thái**: Hoàn thành  
> **Phạm vi**: `sqlglot AST Guard` · `DuckDB In-Memory Sandbox` · `S3 Read-Only Secret` · `RBAC Catalog Scoping` · `Structured Audit Log`

### Thay đổi đã thực hiện
- **T3.1 (`9e2d5bd`)**:
  - Thêm `"run_sql"` vào `ToolName` & `ALLOWED_TOOL_NAMES` và khai báo `RunSqlArguments(sql: str)` (tối đa 5000 ký tự, cấm mọi trường định danh phụ) trong `backend/app/tool_use/contracts.py`.
  - Thêm cấu hình `S3_QUERY_ACCESS_KEY_ID`, `S3_QUERY_SECRET_ACCESS_KEY`, `DUCKDB_MEMORY_LIMIT=512MB`, `DUCKDB_THREADS=2`, `DUCKDB_QUERY_TIMEOUT_SECONDS=15.0`, `DUCKDB_MAX_ROWS=200` vào `backend/app/shared/config.py` và `.env.example`.
  - Thêm `duckdb>=1.1.0` (`2.0.0`) và `sqlglot>=25.0.0` (`30.33.0`) vào `backend/requirements.txt`.
- **T3.2 (`e98daff`)**:
  - Tạo `backend/app/documents/excel/sql_guard.py` (`validate_and_rewrite_sql`): parse dialect `duckdb`, ép đúng 1 statement `SELECT`/`UNION`/`INTERSECT`/`EXCEPT` (+ CTE `WITH`), whitelist tuyệt đối bảng trong `FROM`/`JOIN`, chặn `schema.table`, chuỗi đường dẫn, mọi table-valued function và CTE trùng tên che giấu bảng; blocklist bổ sung các hàm `getenv`, `current_setting`, `duckdb_*`, `pragma_*`, `read_*`, `parquet_*`; tự chèn/hạ `LIMIT <= max_rows` ở mức AST (bọc `SELECT * FROM (...) LIMIT n` cho `UNION`/`INTERSECT`/`EXCEPT`) và sinh SQL đã lọc bỏ comment từ AST.
- **T3.3 (`aec696a`)**:
  - Thêm port `SqlQueryExecutor`, `AuthorizedSqlTable`, `SqlExecutionResult` và các exception domain vào `backend/app/documents/ports.py`.
  - Tạo `backend/app/infrastructure/duckdb_executor.py` (`DuckDBSqlExecutor`, `create_duckdb_sql_executor`): chỉ hoạt động khi `STORAGE_BACKEND=s3`, kiểm tra `S3_QUERY_ACCESS_KEY_ID != S3_INGEST_ACCESS_KEY_ID`; giữ đúng thứ tự khởi tạo: mở `:memory:` → `LOAD httpfs` → tạo `SECRET` chỉ đọc (`SCOPE 's3://{bucket}/{tenant_id}/'`) → `CREATE TEMP VIEW` → `SET memory_limit/threads` → tắt spill đĩa (`temp_directory=''`, `max_temp_directory_size='0B'`) → `SET disabled_filesystems='LocalFileSystem'` → `SET autoinstall_known_extensions=false`, `autoload_known_extensions=false` → `SET lock_configuration=true` → thực thi SQL kèm watchdog `threading.Timer` (`conn.interrupt()`), lấy `max_rows + 1` hàng phát hiện `truncated`, cắt chuỗi > 1000 ký tự và làm sạch lỗi kèm danh sách cột hợp lệ.
  - Cập nhật `backend/Dockerfile` cài sẵn extension `httpfs` lúc build image; tạo script `backend/scripts/smoke_run_sql_s3.py`.
- **T3.4 (`5f4f231`)**:
  - Tạo `backend/app/documents/excel/sql_service.py` (`ExcelSqlService`, `create_run_sql_handler`, `run_sql_tool_definition`): lọc document `INDEXED` (không `DELETED`), kiểm tra `tenant_id`, `can_access_resource`, `SessionScope`, chỉ lấy catalog của `active_version_id`; cấp alias view xác định không đụng độ giữa nhiều file trùng tên sheet; chuyển đổi kết quả JSON-safe; ghi structured audit log (`OK` / `GUARD_REJECTED` / `TIMEOUT` / `ERROR`) cho mỗi truy vấn mà không lộ dữ liệu hàng hay credential.
- **T3.5**:
  - Thêm unit tests `backend/tests/unit/test_sql_guard.py`, `backend/tests/unit/test_duckdb_executor.py` và integration tests `backend/tests/integration/test_run_sql_rbac.py`.

### Files thêm mới / chỉnh sửa
- **Thêm mới:** `backend/app/documents/excel/sql_guard.py`, `backend/app/infrastructure/duckdb_executor.py`, `backend/app/documents/excel/sql_service.py`, `backend/scripts/smoke_run_sql_s3.py`, `backend/tests/unit/test_sql_guard.py`, `backend/tests/unit/test_duckdb_executor.py`, `backend/tests/integration/test_run_sql_rbac.py`.
- **Chỉnh sửa:** `.env.example`, `backend/requirements.txt`, `backend/Dockerfile`, `backend/app/shared/config.py`, `backend/app/tool_use/contracts.py`, `backend/app/documents/ports.py`.

### Kết quả kiểm thử
- `python -m unittest tests/architecture/test_dependency_rules.py -v`: **9/9 PASS**
- `python -m unittest tests/unit/test_sql_guard.py -v`: **11/11 PASS**
- `python -m unittest tests/unit/test_duckdb_executor.py -v`: **6/6 PASS**
- `python -m unittest tests/integration/test_run_sql_rbac.py -v`: **4/4 PASS**
- `npm.cmd run test:contract` (Frontend): **PASS** (`58 REST/SSE/health schemas`)

---

## Giai đoạn 4 — Tích hợp Chat Flow (`run_sql` + `rag_search`) & Tối ưu Embedding
> **Trạng thái**: Hoàn thành  
> **Phạm vi**: `ChatOrchestrator (JSON & SSE)` · `Catalog Prompt Budgeting` · `Sensitive Column Masking` · `Free-Text Selective Embedding` · `Zero-Chunk Support`

### Thay đổi đã thực hiện
- **T4.1 (`12f4d5b`)**:
  - Thêm cờ `EXCEL_SQL_ENABLED=false`, `EXCEL_TEXT_ONLY_EMBEDDING_ENABLED=false` và `EXCEL_SENSITIVE_COLUMN_PATTERNS` vào `backend/app/shared/config.py` và `.env.example`, kèm `@model_validator` kiểm tra phụ thuộc giữa các cờ lúc khởi động (`EXCEL_SQL_ENABLED=true` bắt buộc `AGENTIC_MODE_ENABLED=true`, `STORAGE_BACKEND=s3`, `EXCEL_PARQUET_INGESTION_ENABLED=true`; `EXCEL_TEXT_ONLY_EMBEDDING_ENABLED=true` bắt buộc `EXCEL_PARQUET_INGESTION_ENABLED=true`).
  - Thêm `is_sensitive_column`, `format_catalog_summary_for_prompt`, `create_excel_sql_service` và gắn nguồn citation (`file_name`, `sheet_name`, `document_id`, `version_id`, `source="sql:<view> | <sql>"`) trong `create_run_sql_handler` tại `backend/app/documents/excel/sql_service.py`.
  - Thêm `EXCEL_SQL_AGENT_GUIDANCE` tiếng Việt trong `backend/app/chat/prompts.py`.
  - Cập nhật `backend/app/chat/agent_tools.py`, `backend/app/chat/orchestrator.py`, `backend/app/chat/agent.py` và `backend/app/api/routes/chat.py`: chỉ đăng ký `run_sql` và chèn tóm tắt Table Catalog (đã che giá trị mẫu cột nhạy cảm và cắt gọn trong `RAG_SYSTEM_MAX_TOKENS`) khi phiên có ≥ 1 bảng được phép; hỗ trợ `AGENTIC` trên cả `generate_json` (`/chat`) và `stream_final` (`/chat/stream`) đảm bảo parity 100% giữa JSON và SSE.
- **T4.2 (`0a86caf`)**:
  - Thêm các hằng số ngưỡng có tên và hàm `classify_free_text_column`, `is_sensitive_column_name`, `extract_free_text_row_entries` trong `backend/app/documents/excel/tabular.py`; lưu `is_free_text: bool = False` vào `NormalizedColumnSchema` và `TableColumnSchema` (`backend/app/documents/models.py`).
  - Cập nhật `backend/app/rag/loaders/excel.py`: khi `EXCEL_TEXT_ONLY_EMBEDDING_ENABLED=true`, chỉ tạo `Document` cho các dòng có ít nhất một cột `is_free_text=True` khác rỗng (kèm sheet, row_index và cột định danh dòng không nhạy cảm nếu có).
  - Cập nhật `backend/app/documents/ingestion.py`, `backend/app/documents/service.py` và `backend/app/documents/repository.py`: chấp nhận `chunk_count == 0` (không gọi `embed_chunks`, không upsert Qdrant, vẫn kích hoạt `INDEXED` và hỗ trợ `reconcile_processing`) khi và chỉ khi file là `.xlsx`, bật cả `EXCEL_TEXT_ONLY_EMBEDDING_ENABLED=true` và `EXCEL_PARQUET_INGESTION_ENABLED=true`, và version có ≥ 1 bảng Parquet + catalog hợp lệ; dọn sạch vector Qdrant cũ khi retry/reindex.
- **T4.3**:
  - Thêm unit tests `backend/tests/unit/test_excel_selective_embedding.py` (6/6 PASS) và integration tests `backend/tests/integration/test_chat_sql_routing.py` (7/7 PASS); cập nhật `backend/tests/integration/test_chat_json_tools.py`.

### Files thêm mới / chỉnh sửa
- **Thêm mới:** `backend/tests/unit/test_excel_selective_embedding.py`, `backend/tests/integration/test_chat_sql_routing.py`.
- **Chỉnh sửa:** `.env.example`, `backend/app/shared/config.py`, `backend/app/documents/excel/sql_service.py`, `backend/app/documents/excel/tabular.py`, `backend/app/documents/models.py`, `backend/app/documents/repository.py`, `backend/app/documents/ingestion.py`, `backend/app/documents/service.py`, `backend/app/rag/loaders/excel.py`, `backend/app/chat/prompts.py`, `backend/app/chat/agent_tools.py`, `backend/app/chat/agent.py`, `backend/app/chat/orchestrator.py`, `backend/app/api/routes/chat.py`, `backend/tests/integration/test_chat_json_tools.py`, `task/excel-sql-duckdb/Task.md`, `task/excel-sql-duckdb/change-log.md`.

### Kết quả kiểm thử
- `python -m unittest discover -s tests/architecture -v`: **9/9 PASS**
- `python -m unittest discover -s tests/unit -v`: **331/331 PASS** (bao gồm `test_excel_selective_embedding.py` 6/6 PASS)
- `python -m unittest discover -s tests/integration -v`: **179/179 PASS** (bao gồm `test_chat_sql_routing.py` 7/7 PASS, `test_chat_json_tools.py` 28/28 PASS, `test_chat_stream_tools.py` 29/29 PASS)
- `npm.cmd run test:contract` (Frontend): **PASS** (`58 REST/SSE/health schemas`)
