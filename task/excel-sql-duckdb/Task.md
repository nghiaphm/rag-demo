# Excel SQL Analytics (S3 + Parquet + DuckDB) — Implementation Roadmap & Task Tracking

> **Trạng thái ký hiệu:** `[ ]` Chưa làm · `[/]` Đang thực hiện · `[x]` Hoàn thành · `[!]` Bị chặn

---

## Nguyên tắc kỹ thuật xuyên suốt (Architectural Guardrails)

Mọi thay đổi trong lộ trình hỗ trợ truy vấn tính toán SQL trên Excel bằng DuckDB + Parquet + S3 bắt buộc tuân thủ các ràng buộc kiến trúc sau:
1. **Hexagonal Architecture Boundaries**: Tuân thủ nghiêm AST rules trong `backend/tests/architecture/test_dependency_rules.py` — `documents/`, `chat/`, `api/` không import trực tiếp `infrastructure/`; `tool_use/` chỉ import `shared/` và chính nó. Concrete adapters (`S3StorageBackend`, `DuckDBSqlExecutor`) đặt tại `backend/app/infrastructure/` và inject qua ports tại `backend/app/documents/ports.py`.
2. **Backward Compatibility & Independent Rollback**: Giữ nguyên REST/SSE API contract, Frontend DTO parity (`npm.cmd run test:contract`), và cờ `ASYNC_INGESTION_ENABLED`. Mỗi giai đoạn merge độc lập, có feature flag và rollback an toàn mà không phá luồng hiện có.
3. **Immutable Versioning & Idempotent Ingestion**: Job ingestion phải idempotent khi retry; phiên bản mới chỉ active khi `INDEXED`; tuyệt đối không ghi đè hoặc xóa phiên bản đang active nếu xử lý phiên bản mới thất bại.
4. **Zero-Trust Security & Credential Separation**: `user_id` và `tenant_id` do Backend gắn từ `UserContext`/config, không nhận từ LLM. Tách hoàn toàn credential S3 cho ingestion (ghi) và credential S3 cho query DuckDB (chỉ đọc `s3:GetObject`).
5. **Safe Workbook Limits**: Giữ nguyên toàn bộ giới hạn an toàn hiện có của `read_workbook()` (`10 MiB`, `64 MiB` expanded, `50` sheets, `20.000` hàng, `200` cột, `250.000` ô, `32.767` ký tự/ô, chặn macro & zip-bomb).

---

## Giai đoạn 1 — `StorageBackend` (Local & S3) và chuyển lưu file gốc lên S3
**Mục tiêu**: Thêm abstraction `StorageBackend` (`put` / `get` / `exists` / `delete_prefix`) với bản Local và S3 chọn theo config; chuyển bước `_prepare_upload` sang lưu key `{tenant}/{doc_id}/v{n}/original.xlsx` trên S3 mà chưa đụng DuckDB, hệ thống cũ vẫn chạy bình thường.

### Danh sách task
- [x] **T1.1 — Mở rộng config & storage port (`StorageBackend` Protocol)**
  - **File dự kiến sửa:** `backend/app/shared/config.py`, `backend/app/documents/ports.py`, `backend/app/documents/models.py`, `backend/app/shared/auth.py`, `.env.example`
  - **Phụ thuộc:** Không.
  - **Nội dung:** Khai báo `StorageBackend(Protocol)` (`put`, `get`, `exists`, `delete_prefix`), giữ tương thích `FileStorage` cũ; thêm `build_versioned_storage_key(tenant_id, document_id, version, filename)` sinh `{tenant}/{doc_id}/v{n}/original{ext}`; thêm `tenant_id: str = "default"` vào `DocumentRecord` và `UserContext`; thêm `storage_backend: Literal["local", "s3"] = "local"` vào `DocumentVersionRecord`; mở rộng `config.py` cho `STORAGE_BACKEND=local|s3`, `DEFAULT_TENANT_ID="default"`, `S3_USE_IF_NONE_MATCH=true` và nhóm biến S3 ingestion (`S3_BUCKET`, `S3_REGION`, `S3_ENDPOINT_URL`, `S3_INGEST_ACCESS_KEY_ID`, `S3_INGEST_SECRET_ACCESS_KEY`).

- [x] **T1.2 — Triển khai `LocalStorageBackend` & `S3StorageBackend` + factory**
  - **File dự kiến tạo:** `backend/app/infrastructure/s3_storage.py`
  - **File dự kiến sửa:** `backend/app/infrastructure/storage.py`, `backend/requirements.txt` (`boto3>=1.35.4,<2.0.0`)
  - **Phụ thuộc:** T1.1.
  - **Nội dung:** Bổ sung `delete_prefix` & adapter `StorageBackend` cho `LocalFileStorage` (giữ chặn path traversal); triển khai `S3FileStorage` dùng `boto3` (chặn ghi đè bản gốc bằng conditional put `IfNoneMatch="*"` hoặc fallback `head_object` theo `s3_use_if_none_match`, batch delete 1000 objects cho `delete_prefix`, tính SHA-256 + `size_bytes`, thông báo lỗi an toàn không lộ credential); cập nhật `create_file_storage(config)` chọn adapter theo `STORAGE_BACKEND`.

- [x] **T1.3 — Chuyển bước `_prepare_upload` sang key mới & kiểm chứng sync/async**
  - **File dự kiến sửa:** `backend/app/documents/ingestion.py`, `backend/app/documents/service.py`, `backend/app/documents/attachments.py`, `backend/app/api/routes/documents.py`, `backend/app/api/dependencies/auth.py`, `backend/app/shared/auth.py`
  - **Phụ thuộc:** T1.2.
  - **Nội dung:** `IngestionService._prepare_upload` ghi object với key `{tenant}/{doc_id}/v{n}/original{ext}` (Excel là `original.xlsx`), lưu `storage_backend` (`"local" | "s3"`) trên `DocumentVersionRecord`, truyền `tenant_id` qua `UserContext.tenant_id`, rollback xóa object nếu ghi MongoDB lỗi; khi đọc file ở `preview_version`, `DocumentService.reindex` và `_materialize_and_split` tự chọn đúng backend theo `version.storage_backend` (mặc định `"local"` cho bản ghi cũ).

- [x] **T1.4 — Unit & Integration tests cho Giai đoạn 1**
  - **File dự kiến tạo:** `backend/tests/unit/test_storage_backends.py`, `backend/tests/integration/test_s3_upload_flow.py`
  - **Phụ thuộc:** T1.3.

### Tiêu chí hoàn thành (Definition of Done — Giai đoạn 1)
- [x] `STORAGE_BACKEND=local`: toàn bộ test cũ + mới PASS 100%, upload/preview/reindex/delete không đổi hành vi.
- [x] `STORAGE_BACKEND=s3`: test offline (fake/stub boto3) xác nhận object được lưu đúng key `{tenant}/{doc_id}/v{n}/original.xlsx`, lỗi MongoDB tự cleanup object, `tests/architecture` PASS 9/9.

### Rủi ro & giảm thiểu (Giai đoạn 1)
- **File cũ trên Local bị 404 khi bật S3:** Báo lỗi rõ khi thiếu object; chuẩn bị hướng copy/backfill lên S3 trước khi cắt chuyển production.
- **Race condition ghi đè bản gốc:** Khóa immutability bằng `version` tăng dần + conditional put (`IfNoneMatch="*"` trên S3, `os.link` trên Local).

---

## Giai đoạn 2 — Ingest Excel thành Parquet trên S3 + Sinh Table Catalog vào MongoDB
**Mục tiêu**: Mở rộng bước ingest Excel: làm sạch từng sheet từ `read_workbook()` → ghi Parquet lên S3 (`{tenant}/{doc_id}/v{n}/tables/{ten_bang}.parquet`) → sinh Table Catalog (tên bảng, cột, kiểu, mô tả, dòng mẫu) lưu vào MongoDB.

### Danh sách task
- [ ] **T2.1 — Bộ chuẩn hóa bảng & chuyển đổi Parquet (`tabular.py`)**
  - **File dự kiến tạo:** `backend/app/documents/excel/tabular.py`
  - **File dự kiến sửa:** `backend/requirements.txt` (`pyarrow`)
  - **Phụ thuộc:** T1.2.
  - **Nội dung:** Tái sử dụng `read_workbook()`; chuẩn hóa tên bảng `snake_case` ASCII duy nhất (`[a-z][a-z0-9_]{0,62}`), chuẩn hóa tên cột duy nhất (giữ `original_name`); suy luận kiểu dữ liệu an toàn (`INT64`, `DOUBLE`, `BOOLEAN`, `DATE`/`TIMESTAMP`, `VARCHAR`), chuẩn hóa chuỗi số/rỗng thành `NULL`; xuất Parquet bytes bằng `pyarrow` và trích `row_count`, `sample_rows` (3–5 dòng mẫu giới hạn độ dài ô).

- [ ] **T2.2 — MongoDB model, index & repository cho Table Catalog**
  - **File dự kiến sửa:** `backend/app/documents/models.py`, `backend/app/documents/indexes.py`, `backend/app/documents/repository.py`
  - **Phụ thuộc:** T2.1.
  - **Nội dung:** Thêm `DocumentTableCatalogRecord` & `TableColumnSchema` (collection `document_table_catalogs`); tạo index unique `(version_id, table_name)` và index `(tenant_id, document_id, version_id)` trong `initialize_document_indexes()`; thêm phương thức repository `replace_version_tables`, `list_tables_for_versions`, `delete_tables_for_version`.

- [ ] **T2.3 — Tích hợp xuất Parquet + Catalog vào `IngestionService._process`**
  - **File dự kiến sửa:** `backend/app/documents/ingestion.py`, `backend/app/documents/service.py`
  - **Phụ thuộc:** T2.2, T1.3.
  - **Nội dung:** Với file `.xlsx`, trước khi ghi bảng: gọi `storage.delete_prefix("{tenant}/{doc_id}/v{n}/tables/")` và xóa catalog cũ của `version_id` để đảm bảo **idempotent khi retry**; xuất Parquet lên S3 và lưu catalog vào MongoDB; cleanup cả prefix `tables/` và catalog của `version_id` trong `_fail_before_activation` nếu job lỗi trước khi activate (không chạm version đang active). Giữ nguyên luồng embedding + Qdrant hiện tại trong Giai đoạn 2.

- [ ] **T2.4 — Unit & Integration tests cho Giai đoạn 2**
  - **File dự kiến tạo:** `backend/tests/unit/test_excel_tabular.py`, `backend/tests/integration/test_excel_parquet_ingestion.py`
  - **Phụ thuộc:** T2.3.

### Tiêu chí hoàn thành (Definition of Done — Giai đoạn 2)
- [ ] Upload `.xlsx` (gồm nhiều sheet, cột tiếng Việt, cột trùng/trống, kiểu hỗn hợp, `data/hr_employees_mock.xlsx`) tạo đúng file Parquet trên `{tenant}/{doc_id}/v{n}/tables/*.parquet` và catalog khớp schema/row count trong MongoDB.
- [ ] Retry job không tạo rác Parquet hay trùng catalog; upload v2 lỗi vẫn giữ nguyên v1 đang active.
- [ ] Đọc lại Parquet bằng `pyarrow.parquet.read_table` khớp 100% số dòng, tên cột và giá trị.

### Rủi ro & giảm thiểu (Giai đoạn 2)
- **Ô công thức Excel (`data_only=False`):** Chuỗi công thức `=...` có thể làm cột bị suy luận thành `VARCHAR` — ghi nhận cờ `has_formula_values` trong catalog (hoặc đọc cached value an toàn theo quyết định thiết kế).
- **Trùng tên sheet/cột sau khi chuẩn hóa không dấu:** Deduplicate xác định bằng hậu tố `_2`, `_3` và lưu `sheet_name` / `original_name` để LLM đối chiếu.

---

## Giai đoạn 3 — Tool `run_sql` (DuckDB In-Memory + `sqlglot` + RBAC + S3 Read-Only)
**Mục tiêu**: Xây dựng tool `run_sql` dùng DuckDB in-memory tạo TEMP VIEW từ catalog được cấp quyền, kiểm duyệt chỉ cho `SELECT` bằng `sqlglot` + whitelist tên bảng, giới hạn memory/threads/timeout/số hàng và dùng credential S3 chỉ đọc.

### Danh sách task
- [ ] **T3.1 — Khai báo contract `run_sql` & cấu hình S3 Read-Only / DuckDB limits**
  - **File dự kiến sửa:** `backend/app/tool_use/contracts.py`, `backend/app/shared/config.py`, `backend/requirements.txt` (`duckdb`, `sqlglot`), `.env.example`
  - **Phụ thuộc:** T2.2.
  - **Nội dung:** Thêm `"run_sql"` vào `ToolName` & `ALLOWED_TOOL_NAMES`, khai báo `RunSqlArguments(sql: str)` (tuyệt đối không có `user_id`/`tenant_id`/`s3_path`); thêm cấu hình `S3_QUERY_ACCESS_KEY_ID`, `S3_QUERY_SECRET_ACCESS_KEY`, `DUCKDB_MEMORY_LIMIT`, `DUCKDB_THREADS`, `DUCKDB_QUERY_TIMEOUT_SECONDS`, `DUCKDB_MAX_ROWS`.

- [ ] **T3.2 — Bộ kiểm duyệt SQL AST (`sql_guard.py`) dùng `sqlglot`**
  - **File dự kiến tạo:** `backend/app/documents/excel/sql_guard.py`
  - **Phụ thuộc:** T3.1.
  - **Nội dung:** Parse với dialect `duckdb`; ép đúng 1 statement; chỉ chấp nhận `SELECT`/`UNION`/`INTERSECT`/`EXCEPT` (+ CTE `WITH`), chặn toàn bộ DDL/DML/PRAGMA/COPY/ATTACH/CALL/LOAD/INSTALL/EXPORT; kiểm tra mọi table reference (loại trừ CTE alias) thuộc whitelist view hợp lệ; chặn các hàm đọc file/secret (`read_parquet`, `read_csv`, `read_json`, `glob`, `duckdb_secrets`, `duckdb_settings`, `getenv`, `parquet_scan`); tự chèn/giới hạn `LIMIT <= max_rows` ở mức AST.

- [ ] **T3.3 — Port `SqlQueryExecutor` & Adapter `DuckDBSqlExecutor`**
  - **File dự kiến sửa:** `backend/app/documents/ports.py`
  - **File dự kiến tạo:** `backend/app/infrastructure/duckdb_executor.py`
  - **Phụ thuộc:** T3.2.
  - **Nội dung:** Mở connection `:memory:` mới cho mỗi truy vấn và đóng trong `finally`; thiết lập `memory_limit`, `threads`, tắt spill đĩa (`temp_directory=''`); với S3: nạp `httpfs`, tạo `SECRET` chỉ đọc (`SCOPE 's3://{bucket}/{tenant_id}/'`), bật `disabled_filesystems = 'LocalFileSystem'`; tạo `CREATE TEMP VIEW` chỉ cho các bảng được cấp quyền; khóa cấu hình (`SET lock_configuration = true`) trước khi chạy SQL; giới hạn timeout bằng watchdog `threading.Timer` gọi `conn.interrupt()`.

- [ ] **T3.4 — Service phân quyền catalog & thực thi `run_sql`**
  - **File dự kiến tạo:** `backend/app/documents/excel/sql_service.py`
  - **Phụ thuộc:** T3.3, T2.2.
  - **Nội dung:** Nhận `(user, tenant_id, session_scope)` từ Backend; lọc document `INDEXED` (không `DELETED`), thỏa `can_access_resource`, thuộc `tenant_id` và `SessionScope`; lấy catalog của `active_version_id`; cấp alias view không đụng độ giữa nhiều file; chạy `sql_guard` → `DuckDBSqlExecutor` → trả kết quả JSON-safe kèm metadata bảng/tài liệu đã tham chiếu.

- [ ] **T3.5 — Unit & Security tests cho Giai đoạn 3**
  - **File dự kiến tạo:** `backend/tests/unit/test_sql_guard.py`, `backend/tests/unit/test_duckdb_executor.py`, `backend/tests/integration/test_run_sql_rbac.py`
  - **Phụ thuộc:** T3.4.

### Tiêu chí hoàn thành (Definition of Done — Giai đoạn 3)
- [ ] Chặn 100% payload nguy hiểm: DDL/DML, multi-statement, `read_parquet('/etc/passwd')`, `duckdb_secrets()`, `PRAGMA`, bảng ngoài whitelist, vượt quyền user/tenant, document `DELETED` hoặc version chưa `INDEXED`.
- [ ] `LIMIT` tự động áp dụng đúng `duckdb_max_rows`; truy vấn quá hạn bị ngắt trả `TOOL_TIMEOUT`; truy vấn tổng hợp (`SUM`, `AVG`, `COUNT`, `GROUP BY`) trên Parquet trả kết quả chính xác.

### Rủi ro & giảm thiểu (Giai đoạn 3)
- **Môi trường production không ra ngoài tải `httpfs`:** Cài sẵn extension `httpfs` lúc build Docker image và đặt `autoinstall_known_extensions = false` lúc runtime.
- **Trùng tên sheet giữa nhiều file Excel:** Sinh alias view duy nhất theo document/sheet và truyền đúng ánh xạ trong catalog cho LLM.

---

## Giai đoạn 4 — Tích hợp Chat Flow (`run_sql` + `search_text`) & Tối ưu Embedding
**Mục tiêu**: Tích hợp `run_sql` song song với `rag_search` (`search_text`) vào `ChatOrchestrator` cho cả `/chat` và `/chat/stream`, sau đó tối ưu embedding Excel chỉ embed cột văn bản tự do và chấp nhận file 0 chunk.

### Danh sách task
- [ ] **T4.1 — Tích hợp `run_sql` + tóm tắt catalog vào Chat Flow (JSON & SSE parity)**
  - **File dự kiến sửa:** `backend/app/chat/agent_tools.py`, `backend/app/chat/orchestrator.py`, `backend/app/chat/agent.py`, `backend/app/chat/prompts.py`, `backend/app/api/routes/chat.py`, `backend/app/shared/config.py`
  - **Phụ thuộc:** T3.4.
  - **Nội dung:** Thêm cờ `EXCEL_SQL_ENABLED=false`; truyền `current_user`, `tenant_id`, `sql_service` từ `api/routes/chat.py` (cả `/chat` và `/chat/stream`) vào `ChatOrchestrator`; đăng ký `run_sql` cạnh `rag_search` và document metadata tools; chèn bản tóm tắt catalog (tôn trọng `ContextBudget`) vào prompt khi phiên có bảng Excel hợp lệ; gắn nguồn tài liệu Excel vào `sources` để hiển thị citation đồng nhất trên JSON & SSE.

- [ ] **T4.2 — Tối ưu Embedding Excel: chỉ embed cột văn bản tự do & hỗ trợ 0 chunk**
  - **File dự kiến sửa:** `backend/app/documents/excel/tabular.py`, `backend/app/rag/loaders/excel.py`, `backend/app/documents/ingestion.py`, `backend/app/shared/config.py`
  - **Phụ thuộc:** T4.1, T2.3.
  - **Nội dung:** Thêm cờ `EXCEL_TEXT_ONLY_EMBEDDING_ENABLED=false`; phân loại cột `is_free_text` trong `tabular.py` (loại cột số/ngày/mã ID/nhãn phân loại ngắn); khi bật cờ, `workbook_documents()` chỉ tạo text chunks cho các cột văn bản tự do; cập nhật `IngestionService._process` và `reconcile_processing` chấp nhận `chunk_count == 0` (bỏ qua embedding & Qdrant upsert, vẫn kích hoạt `INDEXED`) khi `.xlsx` đã có ≥ 1 bảng Parquet + catalog hợp lệ.

- [ ] **T4.3 — Integration & Regression tests cho Giai đoạn 4**
  - **File dự kiến tạo:** `backend/tests/integration/test_chat_sql_routing.py`, `backend/tests/unit/test_excel_selective_embedding.py`
  - **File dự kiến sửa:** `backend/tests/integration/test_chat_json_tools.py`
  - **Phụ thuộc:** T4.2.

### Tiêu chí hoàn thành (Definition of Done — Giai đoạn 4)
- [ ] Câu hỏi tính toán/lọc trên Excel đi qua `run_sql` trên cả `/chat` và `/chat/stream`, trả số liệu chính xác kèm citation nguồn; câu hỏi chính sách đi qua `rag_search`; câu hỏi kết hợp gọi phối hợp cả hai.
- [ ] File Excel thuần số/bảng biểu (0 cột văn bản tự do) vẫn đạt trạng thái `INDEXED` với `chunk_count=0`, không gọi Gemini embedding và không báo lỗi `empty_chunks`.
- [ ] Toàn bộ `tests/architecture` (9/9), `tests/unit`, `tests/integration` và Frontend `npm.cmd run test:contract` PASS 100%.

### Rủi ro & giảm thiểu (Giai đoạn 4)
- **Catalog lớn làm tràn `rag_system_max_tokens` (1024):** Cắt gọn catalog theo `ContextBudget` (ưu tiên document trong `SessionScope` hoặc tên khớp câu hỏi; tự rút bớt dòng mẫu nếu sát ngưỡng).
- **LLM viết sai SQL/tên cột:** Trả lỗi an toàn kèm danh sách cột hợp lệ trong `ToolEnvelope` để vòng Agentic tự sửa trong giới hạn `max_agent_steps`.

---

## Giả định, Câu hỏi cần quyết định & Thay đổi hạ tầng

### Giả định đã đặt ra
- Hệ thống chưa có collection `tenants` riêng: tạm dùng `tenant_id` từ `UserContext` (nếu có) hoặc fallback `DEFAULT_TENANT_ID="default"`.
- `run_sql` tái sử dụng `ChatOrchestrator` hiện tại và giữ nguyên hoàn toàn REST/SSE contract để không phải sửa Frontend.
- Dùng `pyarrow` để ghi Parquet có schema chuẩn trước khi lưu lên S3 (tách khỏi DuckDB runtime).
- Giữ `rag_search` hiện có làm tool tìm văn bản tự do (trừ khi quyết định đổi/thêm alias `search_text`).

### Câu hỏi cần quyết định (trước khi bắt đầu code)
1. **Nguồn `tenant_id`:** Thêm `tenant_id` vào JWT/`UserRecord` ngay ở Giai đoạn 1, hay tạm dùng `DEFAULT_TENANT_ID="default"` (hoặc `user_id`) trước?
2. **Ô công thức Excel (`data_only=False`):** Giữ nguyên chuỗi công thức thô `=...` hay cho phép đọc **cached value** trong XML (vẫn `read_only=True`, không chạy macro/external link) cho bước xuất Parquet?
3. **Tên tool văn bản & bật Agentic:** Giữ tên `rag_search` hay thêm/đổi thành `search_text`? Khi bật `EXCEL_SQL_ENABLED=true`, có tự động dùng Agentic cho phiên có Excel không hay yêu cầu bật sẵn `AGENTIC_MODE_ENABLED=true`?
4. **Mô tả cột (`description`) trong Catalog:** Sinh tự động theo rule (tên cột gốc + kiểu + vài giá trị mẫu, 0 chi phí LLM) hay gọi LLM sinh mô tả lúc ingest?
5. **Migration file cũ trên Local:** Có cần viết script `backend/scripts/migrate_local_to_s3.py` để đồng bộ file cũ lên S3 + tạo Parquet/catalog không, hay chỉ áp dụng cho upload mới / `POST /documents/{id}/re-index`?

### Thay đổi Config, Dependencies & Migration
- **Dependencies (`backend/requirements.txt`):** `boto3>=1.35.0` (GĐ 1), `pyarrow>=17.0.0` (GĐ 2), `duckdb>=1.1.0`, `sqlglot>=25.0.0` (GĐ 3).
- **Env vars (`.env.example` & `config.py`):**
  - GĐ 1: `STORAGE_BACKEND`, `DEFAULT_TENANT_ID`, `S3_BUCKET`, `S3_REGION`, `S3_ENDPOINT_URL`, `S3_INGEST_ACCESS_KEY_ID`, `S3_INGEST_SECRET_ACCESS_KEY`.
  - GĐ 3: `S3_QUERY_ACCESS_KEY_ID`, `S3_QUERY_SECRET_ACCESS_KEY`, `DUCKDB_MEMORY_LIMIT`, `DUCKDB_THREADS`, `DUCKDB_QUERY_TIMEOUT_SECONDS`, `DUCKDB_MAX_ROWS`.
  - GĐ 4: `EXCEL_SQL_ENABLED`, `EXCEL_TEXT_ONLY_EMBEDDING_ENABLED`.
- **Migration dữ liệu cũ:** Non-breaking trên MongoDB (`DocumentRecord.tenant_id` mặc định `"default"`, thêm collection `document_table_catalogs` + indexes idempotent tại startup). File Excel cũ vẫn đọc preview/RAG bình thường và có thể sinh Parquet/catalog bằng re-index hoặc script migration.
