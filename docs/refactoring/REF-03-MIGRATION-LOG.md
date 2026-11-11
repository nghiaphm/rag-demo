# REF-03: Backend Structural Migration Log

## 1. Migration Overview

- **Bắt đầu:** 2026-11-11
- **Hoàn thành:** 2026-11-12
- **Branch thực hiện:** `refactor/architecture`
- **Tình trạng:** Hoàn tất toàn bộ các pha (Phase 0 đến Phase 4), 393/393 tests PASS (384 existing tests + 9 new architecture tests).
- **Nguyên tắc bảo toàn:** 0 thay đổi logic nghiệp vụ, 0 thay đổi API contract, 0 thay đổi JSON/SSE payload format.

---

## 2. Nhật Ký Chi Tiết Từng Pha

### Pha 0: Baseline Audit & Chuẩn Bị Môi Trường
1. **Kiểm tra môi trường:**
   - Python: 3.12.10 x64 tại `C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe`.
   - Virtualenv: `.venv` tại `D:\Project\rag-demo\.venv`.
   - Kiểm tra `pip check`: PASS (không xung đột dependency).
2. **Chạy Baseline Test:**
   - Lệnh: `.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v`
   - Kết quả: `Ran 384 tests in 5.132s - OK`.
3. **Lập tài liệu Baseline:** Xuất bản `REF-00-BASELINE-AUDIT.md`.
4. **Tạo nhánh làm việc:** `git checkout -b refactor/architecture`.

---

### Pha 1: Di Chuyển Module & Thiết Lập Cấu Trúc Bounded Context
1. **Tạo cây thư mục mục tiêu:**
   - `app/shared`, `app/infrastructure`, `app/rag/loaders`, `app/documents/excel`, `app/documents/migrations`, `app/conversations`, `app/chat`, `app/api/{routes,schemas,streaming}`.
2. **Di chuyển 34 modules:**
   - Ánh xạ các modules từ `app/` sang các package tương ứng theo [REF-01](REF-01-MODULE-MAPPING.md).
   - Tách `storage.py` thành interface `app/documents/ports.py` và adapter `app/infrastructure/storage.py`.
   - Tách `cloud_connections.py` thành `infrastructure/status.py`, `mongo.py`, `qdrant.py`, `connections.py`.
3. **Sửa đổi các vấn đề phát sinh:**
   - Cập nhật `PROJECT_ROOT` trong `app/shared/config.py`: Đổi `parents[2]` thành `parents[3]` để trỏ đúng thư mục gốc repo `rag-demo`.
   - Cập nhật AST tests trong `test_chat_orchestration.py` và `test_tool_use.py` để quét đúng đường dẫn tệp mới và tập module hợp lệ.
   - Sửa đổi toàn bộ direct imports và chuỗi patch targets trong 34 tệp test và 22 scripts.
4. **Kiểm tra và Xác nhận:**
   - Chạy script kiểm tra import: `check_imports.py` -> `bad: 0`.
   - Chạy test suite: 384 tests PASS.
5. **Git Commit:**
   - Commit: `5f3bb49`
   - Message: `refactor(backend): move modules into feature-based layout`

---

### Pha 2: Thực Hiện 3 Điểm Tách Nghiệp Vụ Cốt Lõi

#### Split 1: Phân tách `excel.py`
- Tách thành:
  - `app/documents/excel/validation.py` (Validation, limits, MIME, WorkbookError).
  - `app/documents/excel/preview.py` (Bounded tabular preview).
  - `app/rag/loaders/excel.py` (LangChain Document generator).
- Cập nhật patch target trong `test_message_attachments_excel.py` (`MAX_INGEST_CHARS`).
- Commit: `81c081d` - `refactor(excel): split validation, preview and RAG row loader`.
- Test: 384 tests PASS.

#### Split 2: Phân tách `ingestion.py`
- Tách các bước kỹ thuật thuần túy sang `app/rag/indexing.py`:
  - `parse_and_split(path)`
  - `embed_chunks(chunks, embedding_model)`
  - `build_vector_records(document_id, version_id, file_name, chunks, vectors)`
- `app/documents/ingestion.py` giữ lại `IngestionService` làm nhiệm vụ điều phối trạng thái, versioning và file storage.
- Commit: `f3424df` - `refactor(ingestion): delegate parse/embed/records to rag.indexing`.
- Test: 384 tests PASS.

#### Split 3: Phân tách SSE Transport Adapter khỏi Chat Domain
- Trích xuất Domain Event `ProviderStreamChunk` sang `app/chat/events.py`.
- Tạo `app/api/streaming/event_adapter.py` với các hàm `stream_domain_events_to_sse` và `accumulate_stream_to_json`.
- Cập nhật `chat/orchestrator.py` và `chat/pipeline.py` để phát sinh domain events trung lập.
- Commit: `c329675` - `refactor(chat): separate domain events from SSE/JSON adapter`.
- Test: 384 tests PASS.

---

### Pha 3: Tái Tổ Chức `tests/`, `evaluation/`, và `scripts/`
1. **Phân loại lại `evaluation/`:**
   - `evaluation/datasets/`: Chứa golden sets (`golden_set.json`, `history_golden_set.json`) và corpus markdown.
   - `evaluation/runner/`: Chứa `eval_cli.py`, `eval_history_cli.py`.
   - `evaluation/scoring/`: Chứa `metrics.py`, `history_eval.py`.
2. **Phân loại lại `tests/`:**
   - `tests/unit/`: 23 tệp test kiểm thử đơn vị logic thuần túy.
   - `tests/integration/`: 14 tệp test tích hợp + 16 integration smoke scripts.
   - `tests/smoke/`: 4 tệp smoke tests chạy offline.
3. **Cập nhật đường dẫn tương đối:**
   - Cập nhật các phép tính `Path(__file__).resolve().parents[...]` để tìm đúng root, `.env.example`, và golden sets.
4. **Kiểm tra và Xác nhận:**
   - Toàn bộ 4 smoke scripts offline trả về exit code 0.
   - Chạy test suite: 384 tests PASS.
5. **Git Commit:**
   - Commit: `ed7cdb9`
   - Message: `refactor(tests): organize tests and evaluation into subpackages`

---

### Pha 4: Thiết Lập và Thực Thi Kiểm Soát Quy Tắc Phụ Thuộc (Architecture Tests)
1. **Loại bỏ hoàn toàn các liên kết module-level vi phạm ranh giới:**
   - `app/api/routes/documents.py`: Bỏ import trực tiếp `infrastructure.storage`, sử dụng `_service(request).storage`.
   - `app/documents/service.py` & `ingestion.py`: Chuyển khởi tạo mặc định của `QdrantVectorIndex` và `create_file_storage` thành dynamic/injected dependency.
   - `app/rag/retriever.py`: Chuyển khởi tạo `QdrantVectorIndex` và `MongoDocumentRepository` trong factory `get_retriever` thành dynamic resolution khi không truyền mock/port.
   - `app/conversations/service.py`: Chuyển `map_verified_citations` thành helper method nội bộ để bảo toàn quy tắc 1 chiều `chat -> conversations`.
2. **Tạo bộ Architecture Tests (`backend/tests/architecture/test_dependency_rules.py`):**
   - 9 test cases kiểm tra tĩnh qua AST duyệt toàn bộ cây import của các module trong `app/`.
   - Xác minh tất cả các quy tắc phụ thuộc:
     - `shared` độc lập 100%.
     - `tool_use` chỉ phụ thuộc `shared` và chính nó.
     - `infrastructure` chỉ implement ports, không import `api` hay `chat`.
     - `rag` không import `infrastructure`, `chat`, hay `api`.
     - `documents` không có module-level import trỏ vào `infrastructure`.
     - `conversations` không import `chat`, `api`, hay `infrastructure`.
     - `chat` không import `api` hay `infrastructure`.
     - `sse_schema` bị cô lập hoàn toàn trong `api/streaming`.
     - `api` không import `infrastructure`.
3. **Chạy toàn bộ test suite:**
   - Tổng cộng: **393 tests** (384 existing + 9 architecture tests).
   - Kết quả: `Ran 393 tests in 4.570s - OK`.
4. **Git Commit:**
   - Commit: `1c0c0bc`
   - Message: `test(architecture): enforce one-way dependency rules`

---

## 3. Các Vấn Đề Gặp Phải và Cách Xử Lý (Troubleshooting Log)

| Vấn đề | Hiện tượng | Nguyên nhân | Giải pháp |
| :--- | :--- | :--- | :--- |
| Sandbox Socket Hang | Lệnh test chạy `asyncio` bị treo khi chạy sandbox tiêu chuẩn | Trên môi trường Windows sandbox, `socket.socketpair()` bị hạn chế quyền mạng cục bộ | Chạy lệnh test runner đầy đủ với cờ `BypassSandbox: true` |
| PROJECT_ROOT Lệch | Tests nạp `.env` hoặc file corpus tìm sai đường dẫn | Khi chuyển `config.py` từ `app/` vào `app/shared/`, cấp độ thư mục tăng 1 cấp | Đổi `Path(__file__).resolve().parents[2]` thành `parents[3]` |
| Static AST Test Fail | `test_chat_orchestration.py` và `test_tool_use.py` báo lỗi import | Các bài test này kiểm tra AST của source code và có danh sách whitelist modules cũ | Cập nhật whitelist đường dẫn module mới cho AST assertions |
| Patch Target Không Tồn Tại | `AttributeError: app.api.routes.documents does not have MongoDocumentRepository` | Test `test_message_attachments_excel.py` patch chuỗi thuộc tính cũ | Cập nhật patch trỏ vào `create_document_service` thay vì patch trực tiếp class hạ tầng |
