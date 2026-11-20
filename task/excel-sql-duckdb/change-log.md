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
> **Trạng thái**: Chưa bắt đầu  
> **Phạm vi**: `Sheet Normalization` · `PyArrow Parquet` · `S3 tables/*.parquet` · `MongoDB Table Catalog`

### Thay đổi đã thực hiện
- *(Sẽ cập nhật sau khi triển khai T2.1 – T2.4)*

### Files thêm mới / chỉnh sửa
- *(Chưa có)*

### Kết quả kiểm thử
- *(Chưa chạy)*

---

## Giai đoạn 3 — Tool `run_sql` (DuckDB In-Memory + `sqlglot` + RBAC + S3 Read-Only)
> **Trạng thái**: Chưa bắt đầu  
> **Phạm vi**: `sqlglot AST Guard` · `DuckDB In-Memory Sandbox` · `S3 Read-Only Secret` · `RBAC Catalog Scoping`

### Thay đổi đã thực hiện
- *(Sẽ cập nhật sau khi triển khai T3.1 – T3.5)*

### Files thêm mới / chỉnh sửa
- *(Chưa có)*

### Kết quả kiểm thử
- *(Chưa chạy)*

---

## Giai đoạn 4 — Tích hợp Chat Flow (`run_sql` + `search_text`) & Tối ưu Embedding
> **Trạng thái**: Chưa bắt đầu  
> **Phạm vi**: `ChatOrchestrator (JSON & SSE)` · `Catalog Prompt Budgeting` · `Free-Text Selective Embedding` · `Zero-Chunk Support`

### Thay đổi đã thực hiện
- *(Sẽ cập nhật sau khi triển khai T4.1 – T4.3)*

### Files thêm mới / chỉnh sửa
- *(Chưa có)*

### Kết quả kiểm thử
- *(Chưa chạy)*
