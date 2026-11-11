# REF-02: Architecture Decisions Record (ADR)

## ADR-01: Modular Monolith theo Feature-based Packages

### Context
Cấu trúc trước đây của `backend/app/` có tính chất phẳng lai (flat/hybrid), trong đó các module thuộc các miền nghiệp vụ khác nhau (documents, chat, conversations, vector index, streaming) nằm chung một cấp thư mục hoặc chia sẻ phụ thuộc chéo. Điều này khiến ranh giới trách nhiệm (bounded context) bị mờ nhạt và tăng nguy cơ phụ thuộc vòng (circular dependencies).

### Decision
Tổ chức lại toàn bộ mã nguồn `backend/app/` theo mô hình Feature-based Modular Monolith:
- `app/shared`: Cấu hình toàn hệ thống, không phụ thuộc vào bất kỳ feature package nào.
- `app/tool_use`: Hợp đồng (`contracts.py`) và bộ điều phối thực thi tool (`executor.py`), độc lập với logic nghiệp vụ tài liệu hay chat.
- `app/infrastructure`: Triển khai cụ thể các adapters hạ tầng (MongoDB, Qdrant, Local filesystem storage).
- `app/rag`: Xử lý kỹ thuật RAG trung lập (loaders, chunking/splitter, embeddings, retriever, port định nghĩa vector index).
- `app/documents`: Miền nghiệp vụ tài liệu (models, repository, document service, lifecycle ingestion, excel previews/validation).
- `app/conversations`: Miền nghiệp vụ phiên và lịch sử hội thoại (models, repository, service, history buffer).
- `app/chat`: Bộ điều phối nghiệp vụ chat, pipeline tổng hợp ngữ cảnh, xử lý query rewriting, token context budget và mapping citations.
- `app/api`: Lớp giao tiếp HTTP transport (FastAPI routes, request/response DTO schemas, SSE streaming adapters).
- `app/main.py`: Composition root duy nhất kết nối dependency injection và quản lý vòng đời ứng dụng (lifespan).

### Consequences
- Mỗi package có phạm vi trách nhiệm rõ ràng.
- Đồ thị phụ thuộc trở thành đồ thị có hướng không chu trình (DAG).
- Dễ dàng thay thế adapter (ví dụ: chuyển từ local file storage sang S3) mà không ảnh hưởng tới business service.

---

## ADR-02: Tách Bounded XLSX Processing (Split 1)

### Context
Trước đây, tệp `app/excel.py` gộp chung 3 trách nhiệm không tương đồng:
1. Validation an toàn tệp XLSX (kiểm tra MIME, giải nén ZIP an toàn, phát hiện macro, giới hạn kích thước).
2. Tạo dữ liệu preview cho giao diện người dùng (bảng dữ liệu có giới hạn dòng/cột hiển thị).
3. Đọc dữ liệu chuyển thành các đối tượng `Document` của LangChain phục vụ ingestion vector.

### Decision
Tách `excel.py` thành 3 module độc lập theo miền trách nhiệm:
1. `app/documents/excel/validation.py`: Quản lý các hằng số giới hạn (`MAX_XLSX_BYTES`, `MAX_SHEETS`, `MAX_ROWS`), ngoại lệ an toàn `WorkbookError`, và parser đọc workbook thô.
2. `app/documents/excel/preview.py`: Hàm `build_excel_preview` trả về cấu trúc xem trước có giới hạn hiển thị.
3. `app/rag/loaders/excel.py`: Hàm `workbook_documents` biến đổi dữ liệu hàng/cột thành LangChain `Document` có metadata chi tiết (`sheet_name`, `row_index`).

### Consequences
- Lớp `rag` chỉ chịu trách nhiệm tạo ra LangChain `Document` phục vụ vectorization.
- Lớp `documents` hoàn toàn làm chủ logic validation và hiển thị preview mà không kéo theo phụ thuộc LangChain Document trong logic preview.

---

## ADR-03: Phân Định Rõ Ràng Ingestion Nghiệp Vụ và Indexing Kỹ Thuật (Split 2)

### Context
Module `app/ingestion.py` trước đây vừa quản lý nghiệp vụ tài liệu (tạo DocumentRecord, DocumentVersionRecord, tính SHA256 checksum, cập nhật trạng thái `ACTIVE`/`FAILED` trên MongoDB, lưu file storage), vừa kiêm luôn các bước kỹ thuật số học (gọi embedding API, tính chunk id dạng UUIDv5, build vector records).

### Decision
Phân tách rõ ràng hai lớp:
1. `app/rag/indexing.py`: Chứa các hàm thuần kỹ thuật xử lý dữ liệu:
   - `parse_and_split(path)`: Phân tích file và chia chunk.
   - `embed_chunks(chunks, embedding_model)`: Gọi embedding provider lấy danh sách vector.
   - `build_vector_records(document_id, version_id, file_name, chunks, vectors)`: Tạo các bản ghi `VectorRecord` trung lập.
2. `app/documents/ingestion.py`: `IngestionService` đóng vai trò điều phối nghiệp vụ:
   - Ghi nhận trạng thái lifecycle, kiểm soát versioning.
   - Lưu trữ bản sao tệp thô qua `FileStorage` port.
   - Ủy nhiệm các bước kỹ thuật cho `rag.indexing`.
   - Nạp các vector records vào `VectorIndex` port.

### Consequences
- Các bước toán học, embedding và chunking có thể được kiểm thử độc lập mà không cần mock MongoDB hoặc FileStorage.
- Business logic của Ingestion trở nên trong sáng, tập trung vào tính toàn vẹn trạng thái tài liệu.

---

## ADR-04: Tách Biệt Domain Events và SSE Transport Formatting (Split 3)

### Context
Trong luồng SSE streaming trước đây, `chat_orchestration.py` và `rag/pipeline.py` trực tiếp sinh ra hoặc định dạng các event frame mang cấu trúc giao thức SSE (`data: {"event": "delta", ...}\n\n`). Điều này vi phạm nguyên tắc Separation of Concerns, buộc core chat pipeline phải biết về định dạng transport HTTP.

### Decision
1. Trích xuất Domain Event trung lập `ProviderStreamChunk` vào `app/chat/events.py` (chỉ chứa text delta, usage token thô, lỗi logic).
2. Xây dựng adapter chuyên trách `app/api/streaming/event_adapter.py`:
   - Hàm `format_sse_event(event_type, payload)`: Tạo chuẩn SSE wire protocol.
   - Hàm `stream_domain_events_to_sse(...)`: Biến đổi chuỗi domain event thành chuỗi SSE events (`start` -> `metadata` -> `delta*` -> `done`/`error`).
   - Hàm `accumulate_stream_to_json(...)`: Biến đổi chuỗi domain event thành kết quả JSON hoàn chỉnh cho endpoint `/chat`.
3. Chỉ duy nhất package `app/api/streaming` được phép import `sse_schema.py`. Cả `app/chat` và `app/rag` tuyệt đối không biết về SSE schema.

### Consequences
- Pipeline nghiệp vụ chat hoàn toàn trung lập với phương thức truyền tải (transport agnostic).
- Đảm bảo tính nhất quán tuyệt đối (parity) giữa endpoint JSON (`/chat`) và streaming SSE (`/chat/stream`).

---

## ADR-05: Ports and Adapters cho Storage và Vector Index (Split 4)

### Context
Trước đây `storage.py` và `qdrant_ingestion.py` vừa chứa abstract interface, vừa chứa code triển khai kết nối trực tiếp đến đĩa cục bộ hoặc Qdrant Cloud. Điều này khiến các business services (`DocumentService`, `Retriever`) bị phụ thuộc cứng vào thư viện bên ngoài.

### Decision
1. Chuyển abstract interface `FileStorage`, `StoredFile`, `StorageError` vào `app/documents/ports.py`. Lớp `documents` chỉ giao tiếp với storage qua port này.
2. Triển khai concrete adapter `LocalFileStorage` và factory `create_file_storage` trong `app/infrastructure/storage.py`.
3. Giữ abstract interface `VectorIndex`, `VectorRecord`, `VectorFilter` tại `app/rag/vector_index.py`.
4. Triển khai concrete adapter `QdrantVectorIndex` trong `app/infrastructure/qdrant_vector_index.py`.
5. Đảm bảo `documents` và `rag` không có module-level dependency tĩnh nào trỏ vào `app.infrastructure`.

### Consequences
- Tuân thủ triệt để Dependency Inversion Principle (DIP).
- Toàn bộ unit tests có thể inject in-memory/fake storage và vector index mà không cần động đến I/O thật.

---

## ADR-06: Không Sử Dụng Shims (No Shims Policy)

### Context
Khi thay đổi cấu trúc module, một giải pháp thường thấy là để lại các tệp facade/shim ở vị trí cũ để re-export đối tượng nhằm tránh sửa đổi import ở tests và scripts. Tuy nhiên, shims che giấu các mối phụ thuộc cũ và dẫn đến nợ kỹ thuật (technical debt).

### Decision
Thực hiện chính sách **Zero Shims**:
- Xóa hoàn toàn các tệp cũ ở vị trí cũ.
- Cập nhật trực tiếp toàn bộ import statements và patch target strings trong 34 tệp test và 22 tệp script/evaluation.
- Kiểm tra toàn diện bằng AST analysis để đảm bảo không còn tệp nào import theo đường dẫn cũ.

### Consequences
- Mã nguồn hoàn toàn sạch sẽ, không còn tàn dư của cấu trúc cũ.
- Cây import của dự án phản ánh chính xác 100% cấu trúc thực tế.
