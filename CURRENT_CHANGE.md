# CURRENT_CHANGE — Nhật ký thực thi RAG V2

> **Vai trò:** Ghi ngắn gọn những gì Agent **thực sự đã làm** sau mỗi task, kèm file thay đổi, kiểm thử và công việc kế tiếp. Kế hoạch/checklist chính nằm tại [`PROJECT_LOG_V2.md`](./PROJECT_LOG_V2.md). Không tự nhận hoàn thành từ nội dung kế hoạch.

## 1. Trạng thái gần nhất

- **Giai đoạn:** Giai đoạn 1 — IN PROGRESS; connection layer đã triển khai, chưa migration/cutover
- **Task vừa hoàn thành:** `P1-07` — Phase 1 verification
- **Task tiếp theo:** `M-03` (**chưa bắt đầu; chờ giao việc**)
- **Blocker:** Không có blocker cho P1-07; `/chat` chưa cutover khỏi PostgreSQL/pgvector và MongoDB user còn role rộng
- **Lần cập nhật:** P1-07 unit/live verification và regression/eval V1 đều PASS; checklist P1-07 đã hoàn thành

> **Quyết định hạ tầng:** MongoDB Atlas cloud, không dùng MongoDB container; Qdrant Cloud (người dùng đã tạo cluster), không dùng Qdrant Docker; raw files lưu local. IP Access List Atlas hiện `0.0.0.0/0` theo xác nhận người dùng — chỉ phù hợp tạm cho development, cần thu hẹp khi có thể. Agent cần kiểm tra `QDRANT_URL` và `QDRANT_API_KEY` đã có trong `.env`, không in/copy giá trị vào log; `.env.example` chỉ dùng placeholder. Không lưu MongoDB URI/Qdrant URL thực/credentials trong file này. Đây là cập nhật tài liệu, **không phải bằng chứng P1-02 hoặc M-02 đã triển khai**.

## 2. Quy tắc ghi nhật ký dành cho Agent

1. Sau **mỗi task**, thêm đúng một mục nhật ký ở **đầu Mục 3** (mới nhất trên cùng); không ghi lại nguyên roadmap hoặc reasoning dài.
2. Ghi `Task ID`, thay đổi thực tế, những file đã sửa, lệnh kiểm thử + trạng thái **PASS / FAIL / NOT RUN**, vấn đề tồn đọng, task kế tiếp. Chỉ ghi PASS nếu đã thực sự chạy và xác minh.
3. Đồng bộ phần **Trạng thái gần nhất** ở trên với dashboard/checkbox của `PROJECT_LOG_V2.md`. Nếu task chưa nghiệm thu, ghi `IN PROGRESS` hoặc `BLOCKED`, không đánh dấu `[x]`.
4. **Không chép secrets, nội dung tài liệu nội bộ, stack trace chứa thông tin nhạy cảm** hay output quá dài vào log. Dùng đường dẫn file và tóm tắt ngắn.
5. Giữ khoảng **10–15 mục gần nhất** trong file này. Khi vượt ngưỡng, chuyển mục cũ nguyên vẹn sang `docs/changelog/phase-XX.md` (tạo thư mục nếu cần), thêm đường dẫn archive ở Mục 4. **Không xóa lịch sử nếu chưa archive thành công.**
6. Nếu có quyết định kiến trúc mới đã được duyệt, ghi tóm tắt quyết định vào Mục 12 của `PROJECT_LOG_V2.md`; entry ở đây chỉ ghi ảnh hưởng thực tế.

## 3. Nhật ký thay đổi (mới nhất ở trên)

<!-- Agent: chèn entry mới bên dưới dòng này. Không coi template hoặc ghi chú tạo file là bằng chứng triển khai. -->

### [2026-10-11] P1-07 — Verification

- **Trạng thái:** COMPLETED.
- **Đã thực hiện:** Thêm verification live namespace riêng cho raw bytes/checksum, Mongo metadata/chunk count, Qdrant similarity retrieval và payload, active-version switching, failed re-index giữ active version cũ, delete không còn retrieval hit và cleanup chính xác. Bổ sung unit verification cho `page` metadata qua loader/chunk/upsert/query. Không thêm query API sản phẩm, không cutover `/chat` và không đánh dấu M-03.
- **Files thay đổi:** `backend/scripts/verify_phase1.py`, `backend/tests/test_ingestion.py`, `backend/evaluation/results/eval_20261011_150123.json`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử PASS:** Unit/API/in-memory integration 38/38; live `verify_phase1.py` PASS toàn bộ tiêu chí V2 và cleanup; MongoDB Atlas/Qdrant Cloud connection PASS; existing loader PASS 1 document/7 chunks; PostgreSQL container healthy; regression/eval V1 PASS 9/9, 0 errors, retrieval hit/recall, answer relevance, faithfulness và fallback accuracy đều 1.0; `compileall`, `pip check` và Compose config PASS.
- **Tồn đọng / quyết định:** Lần eval đầu bị PostgreSQL timeout khi Docker Desktop chưa chạy; sau khi người dùng khởi động Docker, rerun đã PASS và sinh report mới. `/chat` và eval vẫn dùng PostgreSQL/pgvector đúng phạm vi; Qdrant query adapter/cutover thuộc M-03 task riêng.
- **Tiếp theo:** `M-03` — chưa bắt đầu; chờ giao việc riêng. Dừng sau P1-07.

### [2026-10-11] P1-06 — Document APIs

- **Trạng thái:** COMPLETED
- **Đã thực hiện:** Chuyển list/delete sang MongoDB/Qdrant và thêm get/update/re-index. Response trả rõ document/version/job/status; update tạo immutable version mới, re-index dùng raw file của active version. DELETE soft-delete/unpublish metadata trước, đặt `active_version_id=null`, xóa và verify toàn bộ Qdrant points; giữ raw files cùng version/job history. Nếu Qdrant lỗi, trả HTTP 202 với `cleanup_pending=true`; DELETE lặp lại retry idempotent. Ingestion/reconciliation không thể tái activate document đã xóa. `/chat` PostgreSQL/pgvector được giữ nguyên.
- **Files thay đổi:** `backend/app/api/documents.py`, `backend/app/document_models.py`, `backend/app/document_repository.py`, `backend/app/document_service.py`, `backend/app/ingestion.py`, `backend/app/qdrant_ingestion.py`, `backend/app/schemas.py`, `backend/scripts/smoke_document_api.py`, `backend/tests/test_documents_api.py`, `backend/tests/test_ingestion.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử:** Unit/API/in-memory integration — PASS 37/37. Cloud connection — PASS, MongoDB/Qdrant `connected`. Live `smoke_document_api.py` — PASS upload/list/get/update/re-index/delete, DELETE retry idempotent, 3 versions, soft-delete, Qdrant count 0, raw retention và default-list exclusion; cleanup MongoDB/Qdrant/local — PASS. Namespace test bị gián đoạn trước đó — cleanup PASS. Existing loader — PASS 1 document/7 chunks. `compileall`, `pip check`, `docker compose config --quiet` và `git diff --check` — PASS; Docker chỉ cảnh báo không đọc được user config.
- **Tồn đọng / quyết định:** Soft-deleted metadata, raw files và audit history được giữ; garbage collection dài hạn chưa triển khai. `/chat` vẫn dùng PostgreSQL/pgvector, nên M-03 và cutover retrieval chưa hoàn thành. Không triển khai P1-07.
- **Tiếp theo:** `P1-07 / M-03` — chưa bắt đầu; chờ giao việc riêng.

### [2026-10-11 21:27 UTC+07:00] P1-05 — Hoàn tất live ingestion verification

- **Trạng thái:** COMPLETED
- **Đã thực hiện:** Xác minh lại MongoDB Atlas/Qdrant sau khi cập nhật allowlist; sửa PyMongo client dùng `tz_aware=True` để BSON datetime đọc lại đúng contract UTC-aware. Chạy live ingestion hoàn chỉnh qua raw local storage, MongoDB lifecycle, Gemini embedding và Qdrant verify; cleanup chính xác namespace test trên cả ba storage. Không thay đổi PostgreSQL/pgvector retrieval, không triển khai P1-06 và không đánh dấu M-03.
- **Files thay đổi:** `backend/app/cloud_connections.py`, `backend/tests/test_cloud_connections.py`, `backend/scripts/smoke_ingestion.py`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử:** Cloud connection — PASS, MongoDB/Qdrant `connected`. Live `smoke_ingestion.py` — PASS: document/version/job đạt terminal success, active version đúng, raw file tồn tại, Qdrant exact count khớp 1 chunk; cleanup MongoDB/Qdrant/local — PASS. Unit/API/in-memory integration — PASS 32/32. `/health` và `/health/dependencies` — PASS HTTP 200, dependency status `ok`, cả MongoDB/Qdrant `connected`. Existing loader — PASS 1 document/7 chunks. `compileall`, `pip check`, `docker compose config --quiet`, `git diff --check` — PASS; Docker chỉ có cảnh báo không đọc được user config.
- **Tồn đọng / quyết định:** Upload đã dùng V2 nhưng list/delete/chat vẫn dùng PostgreSQL/pgvector cho tới P1-06/M-05. M-03 mới có surface ingestion cần thiết, chưa có adapter query/delete/filter đầy đủ nên vẫn chưa hoàn thành. MongoDB database user vẫn cần thu hẹp role trước dữ liệu thật.
- **Tiếp theo:** `P1-06 / M-03` — chưa bắt đầu; chờ giao việc riêng.

### [2026-10-11 21:16 UTC+07:00] P1-05 — Xác minh lại MongoDB Atlas

- **Trạng thái:** BLOCKED — P1-05 chưa hoàn thành.
- **Đã thực hiện:** Chạy lại cloud connection smoke với timeout mặc định và timeout tạm thời 15 giây; kiểm tra DNS SRV, TCP và TLS theo cách không in URI/hostname/credentials. Không thay đổi source code, `.env`, Atlas network rules hoặc dữ liệu.
- **Files thay đổi:** `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử:** Qdrant Cloud — PASS/connected. MongoDB Atlas ping — FAIL/timeout ở cả 5 giây và 15 giây. DNS SRV — PASS, 3 targets; TCP reachability — PASS; TLS handshake — FAIL trên cả 3 targets với reason `TLSV1_ALERT_INTERNAL_ERROR`. `smoke_ingestion.py` — NOT RUN vì prerequisite MongoDB ping chưa đạt; không tạo MongoDB/Qdrant/local test record trong lần kiểm tra này.
- **Tồn đọng / quyết định:** Backend có thể tìm và mở TCP tới Atlas nhưng server đóng handshake TLS; cần kiểm tra trạng thái cluster, endpoint/connection string đang dùng, Atlas network access và sự kiện/maintenance phía Atlas. Không nới lỏng TLS verification trong code để né lỗi.
- **Tiếp theo:** Sau khi TLS/Atlas hoạt động, chạy lại `backend/scripts/check_cloud_connections.py`, rồi `backend/scripts/smoke_ingestion.py`; không bắt đầu P1-06/M-03.

### [2026-10-11 21:11 UTC+07:00] P1-05 — Ingestion tích hợp

- **Trạng thái:** BLOCKED — chưa đánh dấu checklist hoàn thành.
- **Đã thực hiện:** Chuyển `POST /documents/upload` sang orchestration đồng bộ: raw file immutable → MongoDB document/version/job lifecycle → parse/chunk → Gemini embedding → Qdrant collection/upsert → exact count verify → activate version. Thêm retry cùng version, reconciliation cho cửa sổ lỗi sau verify, cleanup Qdrant trước activation, CAS activation ưu tiên version mới hơn và giữ active version cũ khi candidate fail. Qdrant collection dùng cosine/3072 theo embedding thực và keyword payload indexes `document_id`, `version_id`, `file_name`. List/delete/chat vẫn giữ PostgreSQL/pgvector đúng phạm vi; M-03 chưa được đánh dấu hoàn thành.
- **Files thay đổi:** `backend/app/api/documents.py`, `backend/app/config.py`, `backend/app/document_models.py`, `backend/app/document_repository.py`, `backend/app/ingestion.py`, `backend/app/qdrant_ingestion.py`, `backend/scripts/reconcile_ingestion.py`, `backend/scripts/smoke_ingestion.py`, `backend/scripts/smoke_qdrant_ingestion.py`, `backend/tests/test_documents_api.py`, `backend/tests/test_ingestion.py`, `.env.example`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử:** Unit/API/in-memory integration — PASS 32/32, gồm lifecycle success/failure, retry, reconciliation, active-version preservation, Qdrant payload/schema và upload response contract. Live Gemini→Qdrant Cloud — PASS: 3072 dimensions, upsert/count verify và cleanup test points; collection được giữ, không xóa. Existing loader regression — PASS 1 document/7 chunks. `compileall`, `pip check`, `docker compose config --quiet`, `git diff --check` — PASS (Docker chỉ cảnh báo không đọc được user config). Live end-to-end Atlas/storage/Qdrant — BLOCKED/NOT RUN: MongoDB read-only connection timeout lặp lại ở 5 giây và 15 giây; Qdrant vẫn connected. Không có MongoDB/local test record được tạo bởi lần smoke bị chặn.
- **Tồn đọng / quyết định:** Chưa đủ bằng chứng để nghiệm thu P1-05 cho tới khi MongoDB Atlas ping và `smoke_ingestion.py` PASS cùng cleanup. Upload đã dùng V2, nhưng list/delete/chat vẫn là V1 nên document mới chưa xuất hiện trong các API đó trước P1-06/M-05. MongoDB role rộng và S3 chưa triển khai vẫn là tồn đọng cũ.
- **Tiếp theo:** Kiểm tra Atlas cluster/network/allowlist rồi chạy lại `backend/scripts/check_cloud_connections.py` và `backend/scripts/smoke_ingestion.py`; không bắt đầu P1-06 hoặc tự đánh dấu M-03.

### [2026-10-11 15:33 UTC+07:00] P1-04 — Local File Storage

- **Trạng thái:** COMPLETED
- **Đã thực hiện:** Thêm contract `FileStorage` (`save/open/read/delete/exists`), `LocalFileStorage` và factory theo `STORAGE_BACKEND`/`DOCUMENTS_DIR`. Storage key chỉ sinh từ UUID `document_id/version_id`, không dùng filename; save tính SHA-256/size, publish atomic không ghi đè key đã tồn tại, chặn traversal/symlink escape và cleanup temporary file khi lỗi I/O. Không nối adapter vào upload API, không sửa PostgreSQL/pgvector và không tạo Qdrant collection.
- **Files thay đổi:** `backend/app/storage.py`, `backend/app/config.py`, `backend/tests/test_storage.py`, `.env.example`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử:** Toàn bộ unit tests — PASS 25/25; bao phủ CRUD/open, duplicate filename khác document, hai version khác key, SHA-256, traversal, immutable no-overwrite, I/O cleanup và factory/settings. Existing loader regression `try_step.py backend/fixtures/sample_rag.md` — PASS, 1 document/7 chunks. `compileall`, `pip check`, `docker compose config --quiet`, `git diff --check` — PASS (Docker chỉ cảnh báo không đọc được user config, command vẫn exit 0).
- **Tồn đọng / quyết định:** Local adapter cố ý cấm ghi đè mọi key, mạnh hơn chỉ bảo vệ active version và không cần phụ thuộc MongoDB state. S3 adapter chưa được xây; upload V1 vẫn ghi trực tiếp theo hành vi cũ cho đến P1-05/P1-06. Tests chỉ dùng temporary directory/fixture, không ghi hoặc xóa dữ liệu trong `data/documents`.
- **Tiếp theo:** `P1-05 / M-03` — chưa bắt đầu; chờ giao việc riêng.

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

## 4. Lưu trữ nhật ký cũ (archive)

Chưa có. Khi archive, dùng ví dụ `docs/changelog/phase-01.md` và ghi đường dẫn thật tại đây.
