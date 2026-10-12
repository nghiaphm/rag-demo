# CURRENT_CHANGE — Nhật ký thực thi RAG V2

> **Vai trò:** Ghi ngắn gọn những gì Agent **thực sự đã làm** sau mỗi task, kèm file thay đổi, kiểm thử và công việc kế tiếp. Kế hoạch/checklist chính nằm tại [`PROJECT_LOG_V2.md`](./PROJECT_LOG_V2.md). Không tự nhận hoàn thành từ nội dung kế hoạch.

## 1. Trạng thái gần nhất

- **Giai đoạn:** Giai đoạn 2 — COMPLETED; `P2-01`…`P2-05` đã nghiệm thu
- **Task vừa hoàn thành:** `P2-05` — Verification
- **Task tiếp theo:** `P3-01` (**chưa bắt đầu; chờ giao việc**); `M-06` IN PROGRESS và chờ các gate P3–P5
- **Blocker:** Không có blocker cho P2-05; stale guard sau hard process crash chưa có automatic recovery; M-06 vẫn chờ response/SSE/history-aware
- **Lần cập nhật:** P2-05 live Atlas restart/history/failure/delete + concurrency + 76-test regression PASS

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

### [2026-10-12] P2-05 — Verification

- **Trạng thái:** COMPLETED; Giai đoạn 2 đạt điều kiện kết thúc.
- **Đã thực hiện:** Thêm live verification dùng ba FastAPI lifespan liên tiếp và một session UUID riêng trên MongoDB Atlas. Xác minh session/title cùng 8 messages còn nguyên sau restart; thứ tự `1…8`, pagination `3 + 5`, request linkage, citations, ba turn thành công và một assistant `FAILED/RAG_PIPELINE_ERROR`; kiểm tra guard đã release, UUID sai 422, session thiếu 404, tombstone 410 sau restart, default list loại session đã xóa và DELETE lặp lại idempotent. Generation trong script được mock deterministic để test persistence không phụ thuộc quota provider; cloud clients/routes/indexes/lifecycle vẫn là thật. Exact cleanup PASS.
- **Files thay đổi:** `backend/scripts/verify_phase2.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-01.md` (archive 5 entry cũ theo quy tắc giới hạn nhật ký).
- **Kiểm thử:** `python backend/scripts/verify_phase2.py` — PASS, MongoDB/Qdrant readiness + hai restart persistence/tombstone và cleanup; `python backend/scripts/smoke_session_concurrency.py` — PASS, concurrent reject/owner guard/completion-error-cancel và cleanup; `python -m unittest discover -s tests -v` từ `backend/` — PASS 76/76; Python 3.10.11 hiện tại và `pip check` — PASS.
- **Tồn đọng / quyết định:** Clean restart sau terminal state đã PASS. Hard process kill giữa provider call vẫn có thể để lại stale guard vì chưa có lease/reconciliation tự động; đây là giới hạn vận hành đã ghi trong README, không làm sai acceptance P2-05. Không triển khai response contract, SSE hoặc history-aware trong task này.
- **Tiếp theo:** `P3-01` — chưa bắt đầu; chờ giao việc riêng. `M-06` tiếp tục IN PROGRESS cho các gate P3–P5.

### [2026-10-12] P2-04 — Concurrency

- **Trạng thái:** COMPLETED.
- **Đã thực hiện:** Thêm persistent guard `active_generation_id/started_at` trên session. Mongo `find_one_and_update` atomically kiểm tra session active, nhận guard và cấp message sequence pair; request thứ hai cùng session trả 409 trước khi tạo messages. Guard chỉ release khi khớp owner `request_id` trong `finally`; assistant được terminal hóa và guard được release khi completion, provider/output error hoặc cancellation. DELETE session khi active trả 409. Stateless `/chat` không bị ảnh hưởng.
- **Files thay đổi:** `backend/app/conversation_models.py`, `backend/app/conversation_repository.py`, `backend/app/conversation_service.py`, `backend/tests/test_conversation_models.py`, `backend/tests/test_chat_persistence.py`, `backend/tests/test_conversation_concurrency.py`, `backend/scripts/smoke_message_persistence.py`, `backend/scripts/smoke_session_concurrency.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử:** Focused concurrency/conversation PASS 25/25; toàn bộ unit/API/in-memory regression PASS 76/76. Live HTTP + Atlas test PASS: hai `POST /chat` đồng thời chỉ một generation chạy, request hai 409, non-owner không release được, DELETE active 409, guard release sau completion/error/cancel, terminal history đúng 6 messages và exact cleanup PASS. MongoDB/Qdrant connection, `compileall`, `pip check` PASS.
- **Tồn đọng / quyết định:** Với sync provider call, transport disconnect không ngắt worker ngay; guard được giữ tới terminal thực tế. Process crash có thể để lại stale guard; automatic lease/reconciliation chưa triển khai, cần kiểm tra ở P2-05/operational recovery. Không triển khai streaming/P3–P5.
- **Tiếp theo:** `P2-05` — chưa bắt đầu; chờ giao việc riêng.

### [2026-10-12] P2-03 — Message persistence

- **Trạng thái:** COMPLETED.
- **Đã thực hiện:** Mở rộng `/chat` nhận optional `session_id`; thiếu ID giữ nguyên stateless response `answer + sources`. Với session, cấp atomically hai sequence, ghi user `COMPLETED` và assistant `PENDING` trước generation, dùng chung `request_id`, rồi replace assistant sang `COMPLETED` kèm model/citations hoặc `FAILED` với mã an toàn. Usage để null vì pipeline hiện không trả metadata. Invalid/missing/deleted session lần lượt trả 422/404/410; chưa thêm one-generation guard của P2-04.
- **Files thay đổi:** `backend/app/conversation_models.py`, `backend/app/conversation_repository.py`, `backend/app/conversation_service.py`, `backend/app/api/chat.py`, `backend/app/schemas.py`, `backend/tests/test_chat_persistence.py`, `backend/scripts/smoke_message_persistence.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử PASS:** Focused 21/21; toàn bộ unit/API/in-memory regression 72/72; live persistent `/chat` trên Atlas/Qdrant/provider xác minh user/PENDING-before-generation, assistant COMPLETED, citations, request linkage và stable order; forced provider failure và empty output xác minh FAILED/error code an toàn; exact cleanup PASS. MongoDB/Qdrant connection, FastAPI startup `/health/dependencies`, `compileall`, `pip check` PASS.
- **Kiểm thử FAIL có nguyên nhân ngoài task:** `verify_cutover.py` retry 2 lần đều FAIL tại stateless `product_api_qa`, cleanup PASS; diagnostic an toàn xác nhận HTTP 502 `TooManyRequestsResponseError` từ OpenRouter. Nhánh stateless unit compatibility PASS và live persistent provider call trước đó PASS; không đổi hai lượt rate-limit thành PASS.
- **Tồn đọng / quyết định:** Sequence allocation là atomic nhưng chưa chặn hai generation đồng thời trên cùng session; P2-04 xử lý guard. Response chưa thêm message/request IDs để giữ backward compatibility; thuộc P3.
- **Tiếp theo:** `P2-04` — chưa bắt đầu; chờ giao việc riêng.

### [2026-10-12] P2-02 — Session APIs

- **Trạng thái:** COMPLETED.
- **Đã thực hiện:** Thêm Mongo repository/service và REST APIs create/list/get/PATCH title/delete cho session; list và message history trả pagination `offset/limit/total`, history sắp theo `(sequence, _id)`. UUID sai trả 422, session không tồn tại trả 404, tombstone trả 410. DELETE soft-delete session trước, hard-delete related messages, giữ tombstone và cho phép retry idempotent. Scope/user không nhận tùy ý từ client; create mặc định `ALL_ACTIVE`. `/chat` vẫn stateless đúng phạm vi.
- **Files thay đổi:** `backend/app/conversation_repository.py`, `backend/app/conversation_service.py`, `backend/app/conversation_schemas.py`, `backend/app/api/sessions.py`, `backend/app/main.py`, `backend/tests/test_sessions_api.py`, `backend/scripts/smoke_session_api.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử:** Focused tests PASS 15/15; toàn bộ unit/API/in-memory regression PASS 66/66. Live Atlas Session API PASS create/list/get/update/history pagination, 404/410, list exclusion, message cleanup, repeated DELETE và exact cleanup. MongoDB/Qdrant connection PASS; FastAPI startup + `/health/dependencies` PASS HTTP 200. Live `verify_cutover.py` PASS 3 documents/68 chunks, retrieval, Q&A, page metadata, active-version filter, delete-no-retrieval và cleanup. `compileall`, `pip check` PASS.
- **Tồn đọng / quyết định:** Xóa session giữ tombstone nhưng xóa hẳn messages; không có distributed transaction, nên tombstone được ghi trước và DELETE lặp lại tiếp tục cleanup. Chưa ghi messages từ `/chat`, chưa có atomic generation guard; thuộc P2-03/P2-04. M-06 vẫn IN PROGRESS.
- **Tiếp theo:** `P2-03` — chưa bắt đầu; chờ giao việc riêng.

### [2026-10-12] M-06 — Regression liên giai đoạn (P2 slice)

- **Trạng thái:** IN PROGRESS; chưa đủ điều kiện đánh dấu hoàn thành.
- **Đã thực hiện:** Xác minh lại active-version scope, Qdrant citation metadata, `/chat` JSON, page metadata và delete-no-retrieval sau khi thêm P2-01. Session scope/model validation và request linkage PASS; không phát hiện regression cần sửa.
- **Kiểm thử:** Live `verify_cutover.py` PASS 3 documents/68 chunks, demo retrieval, product Q&A, PDF page, active-version filter, delete-no-retrieval và cleanup. Unit regression nằm trong lượt 62/62 PASS.
- **Tồn đọng:** Session APIs/message persistence thuộc P2-02/P2-03, response contract thuộc P3, SSE thuộc P4 và history-aware thuộc P5 chưa tồn tại; vì vậy các gate còn lại là prerequisite pending, không phải PASS giả.
- **Tiếp theo:** Chạy lại M-06 sau từng capability P3–P5; không tự động triển khai trong task này.

### [2026-10-12] P2-01 — Session/message models và indexes

- **Trạng thái:** COMPLETED.
- **Đã thực hiện:** Thêm Pydantic records cho session, retrieval scope, message role/lifecycle, citation, usage và request linkage với UUID/UTC validation. Thêm named indexes cho session listing và message stable order; unique `(session_id, sequence)` nhưng không unique `request_id`. Startup và index CLI khởi tạo cả document/conversation indexes idempotently. Thêm live smoke test dùng test IDs riêng và cleanup chính xác; không nối `/chat` vào persistence.
- **Files thay đổi:** `backend/app/conversation_models.py`, `backend/app/conversation_indexes.py`, `backend/app/main.py`, `backend/scripts/init_mongodb_indexes.py`, `backend/scripts/smoke_conversation_models.py`, `backend/tests/test_conversation_models.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử:** Unit/API/in-memory regression PASS 62/62. MongoDB Atlas/Qdrant connection PASS. Live index verification PASS cho 5 collections; `sessions` 3 và `messages` 4 indexes, rerun idempotent. Live session/message insert/order/request linkage/unique sequence/cleanup PASS. FastAPI startup + GET `/health/dependencies` PASS HTTP 200. `compileall`, `pip check` và `git diff --check` PASS.
- **Tồn đọng / quyết định:** Chưa có repository/session APIs, chưa ghi messages từ `/chat`, chưa có atomic generation guard; đúng phạm vi P2-02–P2-04. M-06 chỉ hoàn tất sau response/SSE/history-aware gates.
- **Tiếp theo:** `P2-02` — chưa bắt đầu; chờ giao việc riêng.

### [2026-10-12] M-05 — Qdrant cutover

- **Trạng thái:** COMPLETED.
- **Đã thực hiện:** Chụp baseline pgvector trước cutover và đối chiếu đúng 3 demo documents với chunk counts `37/16/15` (68 tổng). Thêm Qdrant LangChain retriever lấy active-version scope từ MongoDB và filter bằng `MatchAny`; `/chat` dùng cloud clients chung và trả thêm `version_id/chunk_id`. Chuyển eval sang collection Qdrant riêng, cập nhật corpus/golden set hiện hành và chuẩn hóa Unicode dash trong deterministic fact metric. Chỉ sau khi live gates PASS mới gỡ `db.py`, pgvector vectorstore, V1 scripts, `DATABASE_URL`, ba package PostgreSQL và Compose. README ghi rollback; container/volume PostgreSQL cũ không bị xóa.
- **Files thay đổi:** `backend/app/api/chat.py`, `backend/app/cloud_connections.py`, `backend/app/config.py`, `backend/app/document_repository.py`, `backend/app/main.py`, `backend/app/qdrant_ingestion.py`, `backend/app/vector_index.py`, `backend/app/rag/chain.py`, `backend/app/rag/pipeline.py`, `backend/app/rag/retriever.py`, `backend/app/schemas.py`, `backend/scripts/eval_cli.py`, `backend/scripts/verify_cutover.py`, `backend/evaluation/corpus/qdrant.md`, `backend/evaluation/golden_set.json`, `backend/evaluation/metrics.py`, `backend/evaluation/results/m05_qdrant_eval.json`, `backend/tests/test_retriever.py`, `backend/tests/test_evaluation_metrics.py`, `backend/tests/test_vector_index.py`, `backend/requirements.txt`, `.env.example`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`; xóa `backend/app/db.py`, `backend/app/rag/vectorstore.py`, `backend/scripts/try_vectorstore.py`, `backend/scripts/try_rag.py`, `backend/scripts/try_pipeline.py`, `backend/fixtures/sample_pipeline.md`, `backend/evaluation/corpus/postgresql.md`, `docker-compose.yml`.
- **Kiểm thử:** Pre-cutover pgvector snapshot PASS 3 documents/68 chunks và khớp Qdrant. Unit/API/in-memory PASS 51/51. Live `verify_cutover.py` PASS document/chunk counts, retrieval ba demo sources, GET `/health/dependencies`, POST `/chat` Q&A, PDF page metadata, active-version exclusion, delete-no-retrieval và exact cleanup. Qdrant-isolated eval PASS 9/9, 0 errors; retrieval hit/recall, answer relevance/fact coverage, faithfulness và fallback accuracy đều `1.0`. `compileall`, `pip check`, runtime import/dependency grep và `git diff --check` PASS. Một lượt eval bị provider treo và timeout, retry hữu hạn sau đó PASS; không tính lượt timeout là PASS.
- **Tồn đọng / rollback:** Không có dual-write hoặc runtime feature flag; rollback cần restore code/config/requirements/Compose từ Git ref trước M-05, đặt lại `DATABASE_URL`, dùng container/volume cũ đang được giữ và chạy V1 eval trước khi trả traffic. Không xóa MongoDB/Qdrant khi rollback. MongoDB role rộng vẫn cần thu hẹp; `.env` có thể còn biến `DATABASE_URL` cũ nhưng settings hiện bỏ qua và không dùng.
- **Tiếp theo:** `P2-01` — chưa bắt đầu; chờ giao việc riêng. Không tự động triển khai M-06.

### [2026-10-12] M-04 — Data migration

- **Trạng thái:** COMPLETED.
- **Đã thực hiện:** Khôi phục đúng Python 3.10.11 cho virtual environment hiện có, không đổi dependency. Thêm `source_key` tùy chọn với unique partial index để nhận diện corpus migration mà không áp unique lên filename/checksum; ingestion chỉ cho gán key khi tạo document. Thêm manifest cố định cho 3 raw demo files và migration service/CLI: re-parse, re-embed, tạo version/status qua lifecycle hiện có, verify raw checksum/size, Mongo active version, exact Qdrant chunk count, filtered retrieval và payload. Rerun cùng checksum chỉ verify read-only; source đổi tạo immutable version mới; lỗi không thay active version. Không cutover `/chat`, không xóa PostgreSQL/pgvector hay dữ liệu cloud cũ.
- **Files thay đổi:** `backend/app/data_migration.py`, `backend/app/document_models.py`, `backend/app/document_indexes.py`, `backend/app/document_repository.py`, `backend/app/ingestion.py`, `backend/migration/demo_corpus.json`, `backend/scripts/migrate_demo_corpus.py`, `backend/tests/test_document_models.py`, `backend/tests/test_ingestion.py`, `backend/evaluation/results/m04_regression.json`, `.gitignore`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử:** Python 3.10.11 và `pip check` PASS. Unit/API/in-memory PASS 47/47. Cloud connection PASS. Live migration lần đầu PASS 3/3 documents, 68 chunks (37/16/15), 0 failed; rerun PASS 3/3 `VERIFIED`, 0 document/version mới. Live `verify_phase1.py` PASS raw/checksum, metadata/page, chunk count, retrieval, version switch, failed re-index, delete-no-retrieval và cleanup. Regression/eval PostgreSQL V1 PASS 9/9, 0 errors; retrieval/fact/fallback `1.0`, faithfulness `0.889`. `compileall`, Compose config và `git diff --check` PASS.
- **Tồn đọng / quyết định:** Migration chỉ xử lý đúng manifest repository-owned, không scan toàn bộ `DOCUMENTS_DIR`. Same-checksum nhưng verify lỗi được báo FAILED và không tự sinh version; operator sửa dependency/dữ liệu rồi chạy lại. `/chat` vẫn dùng PostgreSQL/pgvector; so sánh/cutover và rollback thuộc M-05. MongoDB user role rộng vẫn cần thu hẹp trước dữ liệu thật.
- **Tiếp theo:** `M-05` — chưa bắt đầu; chờ giao việc riêng. Dừng sau M-04.

### [2026-10-11] M-03 — Vector adapter

- **Trạng thái:** COMPLETED.
- **Đã thực hiện:** Thêm backend-neutral `VectorIndex` contract cùng `VectorRecord`, `VectorFilter`, `VectorSearchResult`, UUID/dimension/finite-vector validation và deterministic chunk point ID. `QdrantVectorIndex` implement add có duplicate guard, idempotent upsert, similarity query, exact count, delete an toàn và filter kết hợp theo document/version/filename; mapping giữ chunk text cùng page metadata và bọc lỗi backend không lộ raw detail. Refactor ingestion/document service và smoke scripts chỉ dùng contract chung; Qdrant SDK chỉ còn trong adapter/composition root. Không migration dữ liệu và không cutover `/chat`.
- **Files thay đổi:** `backend/app/vector_index.py`, `backend/app/qdrant_ingestion.py`, `backend/app/ingestion.py`, `backend/app/document_service.py`, `backend/tests/test_vector_index.py`, `backend/tests/test_ingestion.py`, `backend/scripts/smoke_vector_adapter.py`, `backend/scripts/smoke_qdrant_ingestion.py`, `backend/scripts/smoke_ingestion.py`, `backend/scripts/smoke_document_api.py`, `backend/scripts/verify_phase1.py`, `backend/evaluation/results/m03_regression.json`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử:** Unit/API/in-memory integration PASS 42/42. Live `smoke_vector_adapter.py` PASS add/upsert/query/filter/delete, duplicate guard và cleanup. Live `verify_phase1.py` PASS toàn bộ lifecycle/retrieval và cleanup sau refactor. Regression/eval V1 PASS 9/9, 0 errors; retrieval hit/recall, answer relevance, fact coverage và fallback accuracy `1.0`, faithfulness `0.889`. `compileall`, `pip check`, Compose config và `git diff --check` PASS.
- **Tồn đọng / quyết định:** `add` dùng preflight duplicate check vì Qdrant không cung cấp create-only atomic primitive trong adapter hiện tại; ingestion dùng deterministic ID và `upsert` cho idempotency. Chưa migrate corpus/dữ liệu sang Qdrant và chưa thay retriever `/chat`; các việc đó thuộc M-04/M-05.
- **Tiếp theo:** `M-04` — chưa bắt đầu; chờ giao việc riêng. Dừng sau M-03.

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

## 4. Lưu trữ nhật ký cũ (archive)

- [Phase 1 — P1-01 đến P1-03](./docs/changelog/phase-01.md)
