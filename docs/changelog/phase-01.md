# Phase 1 — Nhật ký đã lưu trữ

> Các entry dưới đây được chuyển nguyên nội dung từ `CURRENT_CHANGE.md` theo quy tắc chỉ giữ 10–15 entry gần nhất.

### [2026-10-11 15:22 UTC+07:00] P1-03 — Document models & indexes

- **Trạng thái:** COMPLETED
- **Đã thực hiện:** Thêm Pydantic models `DocumentRecord`, `DocumentVersionRecord`, `IngestionJobRecord` với UUID v4 độc lập filename, Enum status, SHA-256 validation, UTC-aware datetime và `active_version_id=None`. Thêm initializer idempotent và gọi khi FastAPI startup nếu MongoDB connected; không nối models vào upload/pipeline hiện tại.
- **Files thay đổi:** `backend/app/document_models.py`, `backend/app/document_indexes.py`, `backend/app/main.py`, `backend/scripts/init_mongodb_indexes.py`, `backend/tests/test_document_models.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử:** Unit tests — PASS 15/15 toàn suite. Live Atlas index init chạy hai lần — PASS/idempotent: `documents` 3, `document_versions` 4, `ingestion_jobs` 2 named indexes. Actual options — PASS: unique `(document_id, version)`, filename/checksum non-unique. Live namespace smoke — PASS: hai documents trùng filename được phép, duplicate document/version bị từ chối; cleanup chính xác 2 document + 1 version và xác minh không còn record test. `/health` và `/health/dependencies` — PASS HTTP 200, MongoDB/Qdrant connected. `try_step.py`, `pip check`, `docker compose config --quiet` — PASS.
- **Tồn đọng / quyết định:** MongoDB user vẫn có role quản trị rộng; nên thu hẹp quyền trước dữ liệu thật. Chưa có MongoDB JSON schema validator; Pydantic chịu trách nhiệm validation ở application layer. Chưa tạo Qdrant collection, chưa migration và chưa thay đổi PostgreSQL/pgvector pipeline.
- **Tiếp theo:** `P1-04 / M-03` — chưa bắt đầu; chờ giao việc riêng.

### [2026-10-11 15:02 UTC+07:00] P1-02 — Hoàn tất MongoDB Atlas connection

- **Trạng thái:** COMPLETED
- **Đã thực hiện:** Xác nhận bốn biến MongoDB/Qdrant hiện diện mà không in giá trị; chạy cloud smoke chỉ-đọc và xác minh MongoDB Atlas `ping` cùng Qdrant authentication thành công. Kiểm tra readiness và phạm vi role dưới dạng boolean; không tạo collection/schema/document, không migrate dữ liệu và không thay đổi PostgreSQL/pgvector pipeline.
- **Files thay đổi:** `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử:** `backend/scripts/check_cloud_connections.py` — PASS cho MongoDB và Qdrant. `/health/dependencies` — PASS HTTP 200, status `ok`, cả hai dependency `connected`; `/health` — PASS HTTP 200/contract cũ. Unit tests — PASS 6/6. `backend/scripts/try_step.py` — PASS, 1 document/7 chunks. `pip check` và `docker compose config --quiet` — PASS.
- **Tồn đọng / quyết định:** MongoDB authentication/connection đã đạt, nhưng kiểm tra role cho thấy user có quyền quản trị rộng và chưa có role scope riêng cho application database; cần thu hẹp quyền trước khi dùng dữ liệu thật. Qdrant vẫn có 0 collection; việc tạo schema/adapter thuộc task sau.
- **Tiếp theo:** `P1-03 / M-03` — chưa bắt đầu; chờ giao việc riêng.

### [2026-10-11 14:46 UTC+07:00] P1-02 — Xác minh lại MongoDB Atlas

- **Trạng thái:** BLOCKED
- **Đã thực hiện:** Xác nhận `MONGODB_URI`/`MONGODB_DB_NAME` hiện diện và đúng định dạng mà không in giá trị; chạy ping Atlas, cloud smoke và FastAPI readiness. Bổ sung phân loại an toàn Atlas error code 8000 thành `authentication_failed`; không thay đổi PostgreSQL/pgvector pipeline và không ghi dữ liệu.
- **Files thay đổi:** `backend/app/cloud_connections.py`, `backend/tests/test_cloud_connections.py`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử:** `backend/scripts/check_cloud_connections.py` — FAIL cho MongoDB (`authentication_failed`, code 8000/AtlasError), PASS cho Qdrant. `/health` — PASS HTTP 200/contract cũ; `/health/dependencies` — PASS về error handling, trả HTTP 503 `degraded` với MongoDB `authentication_failed` và Qdrant `connected`. Unit tests — PASS 6/6. `backend/scripts/try_step.py` — PASS, 1 document/7 chunks. `pip check` — PASS.
- **Tồn đọng / quyết định:** Atlas đã nhận kết nối nên không phải thiếu biến hay lỗi DNS cơ bản; cần kiểm tra database username/password, URL-encoding ký tự đặc biệt và database user thuộc đúng Atlas project/cluster. Chưa thể xác minh quyền DB tối thiểu, vì authentication chưa thành công. P1-02 không được đánh dấu `[x]`.
- **Tiếp theo:** Sửa credentials MongoDB trong `.env` rồi chạy lại cùng smoke test; không bắt đầu `P1-03` hoặc `M-03`.

### [2026-10-11 14:31 UTC+07:00] P1-02 / M-02 — Cloud connections

- **Trạng thái:** `P1-02` BLOCKED; `M-02` COMPLETED
- **Đã thực hiện:** Khôi phục đúng Python 3.10.11 cho `.venv`; thêm PyMongo/Qdrant SDK, secret-safe settings validation, client lifecycle FastAPI, timeout/error mapping, readiness endpoint và smoke script chỉ-đọc. Giữ nguyên `/health`, document/chat APIs, PostgreSQL/pgvector pipeline và Docker Compose; không tạo collection, schema hay migrate dữ liệu.
- **Files thay đổi:** `.env.example`, `backend/requirements.txt`, `backend/app/config.py`, `backend/app/cloud_connections.py`, `backend/app/main.py`, `backend/scripts/check_cloud_connections.py`, `backend/tests/test_cloud_connections.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử:** `python -m unittest discover -s tests -v` (từ `backend/`) — PASS, 6/6 test success/authentication/timeout. `python -m pip check` — PASS. `python backend/scripts/try_step.py` — PASS, 1 document/7 chunks. FastAPI smoke — PASS: `/health` giữ HTTP 200/contract cũ; readiness trả HTTP 503 an toàn khi MongoDB thiếu config và báo Qdrant connected. Cloud smoke chỉ-đọc — Qdrant PASS (HTTPS/auth/list collections); MongoDB BLOCKED (`not_configured`). Qdrant cluster có 0 collection, nên không có dimension/distance/payload index để xác minh ở bước này.
- **Tồn đọng / quyết định:** `P1-02` không được đánh dấu hoàn thành cho tới khi có hai biến MongoDB thật và ping Atlas PASS; chưa xác minh quyền DB tối thiểu. Qdrant target collection/schema thuộc M-03, chưa tạo. Không thay đổi `docker-compose.yml`.
- **Tiếp theo:** Bổ sung `MONGODB_URI`, `MONGODB_DB_NAME` vào `.env` rồi chạy lại `backend/scripts/check_cloud_connections.py`; không bắt đầu `P1-03` hoặc `M-03` trong phiên này.

### [2026-10-11 13:41 UTC+07:00] P1-01 / M-01 — Audit baseline

- **Trạng thái:** COMPLETED
- **Đã thực hiện:** Đối chiếu README với toàn bộ backend, routes, upload/index/list/delete, retrieval/chain, scripts, evaluation, dependencies, config và Compose. Xác nhận runtime V1 coupling trực tiếp với PostgreSQL/pgvector; chưa có MongoDB/Qdrant adapter. Ghi nhận loader thực tế hỗ trợ thêm XLSX và các rủi ro baseline: upload ghi đè file trước khi index, re-index xóa vector cũ trước khi add, delete không xóa file, chưa có test suite.
- **Files thay đổi:** `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md` (chỉ cập nhật trạng thái/nhật ký; không sửa source code).
- **Kiểm thử:** `docker compose config --quiet` — PASS; cấu hình Compose hợp lệ. Kiểm tra `.env` không in giá trị — PASS; Qdrant URL/key hiện diện, URL HTTPS, MongoDB URI/database chưa có. Python AST, `/health`, `try_step.py` và retrieval/eval hiện tại — NOT RUN; interpreter gốc của `.venv` không còn tồn tại. `docker compose ps` — NOT RUN; Docker daemon không chạy. Hai artifact eval ngày 2026-09-24 là baseline lịch sử: mỗi run 9/9 case không lỗi, retrieval hit/recall 1.0; đây không phải kết quả chạy lại.
- **Tồn đọng / quyết định:** `langchain-postgres`, `pgvector`, `psycopg`, `DATABASE_URL`, `app/db.py`, vectorstore/retriever/pipeline, API documents/chat, scripts, eval và Compose đều cần được thay thế hoặc tách khỏi PostgreSQL trong các task migration sau. `.env.example` và Settings chưa khai báo MongoDB/Qdrant; Qdrant credentials trong `.env` hiện bị `extra="ignore"`. Chưa xác minh kết nối cloud, collection/dimension hay dữ liệu.
- **Tiếp theo:** `P1-02 / M-02` — chỉ bắt đầu khi được giao; sửa môi trường Python trước khi chạy smoke test.
