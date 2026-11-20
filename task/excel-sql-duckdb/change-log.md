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
> **Trạng thái**: Chưa bắt đầu  
> **Phạm vi**: `StorageBackend Protocol` · `LocalStorageBackend` · `S3StorageBackend` · `Versioned Key {tenant}/{doc_id}/v{n}/original.xlsx`

### Thay đổi đã thực hiện
- *(Sẽ cập nhật sau khi triển khai T1.1 – T1.4)*

### Files thêm mới / chỉnh sửa
- *(Chưa có)*

### Kết quả kiểm thử
- *(Chưa chạy)*

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
