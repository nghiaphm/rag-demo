# Phase 2 — Nhật ký đã lưu trữ

> Các entry dưới đây được chuyển nguyên nội dung từ `CURRENT_CHANGE.md` theo quy tắc chỉ giữ 10–15 entry gần nhất.

### [2026-10-12] P2-02 — Session APIs

- **Trạng thái:** COMPLETED.
- **Đã thực hiện:** Thêm Mongo repository/service và REST APIs create/list/get/PATCH title/delete cho session; list và message history trả pagination `offset/limit/total`, history sắp theo `(sequence, _id)`. UUID sai trả 422, session không tồn tại trả 404, tombstone trả 410. DELETE soft-delete session trước, hard-delete related messages, giữ tombstone và cho phép retry idempotent. Scope/user không nhận tùy ý từ client; create mặc định `ALL_ACTIVE`. `/chat` vẫn stateless đúng phạm vi.
- **Files thay đổi:** `backend/app/conversation_repository.py`, `backend/app/conversation_service.py`, `backend/app/conversation_schemas.py`, `backend/app/api/sessions.py`, `backend/app/main.py`, `backend/tests/test_sessions_api.py`, `backend/scripts/smoke_session_api.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử:** Focused tests PASS 15/15; toàn bộ unit/API/in-memory regression PASS 66/66. Live Atlas Session API PASS create/list/get/update/history pagination, 404/410, list exclusion, message cleanup, repeated DELETE và exact cleanup. MongoDB/Qdrant connection PASS; FastAPI startup + `/health/dependencies` PASS HTTP 200. Live `verify_cutover.py` PASS 3 documents/68 chunks, retrieval, Q&A, page metadata, active-version filter, delete-no-retrieval và cleanup. `compileall`, `pip check` PASS.
- **Tồn đọng / quyết định:** Xóa session giữ tombstone nhưng xóa hẳn messages; không có distributed transaction, nên tombstone được ghi trước và DELETE lặp lại tiếp tục cleanup. Chưa ghi messages từ `/chat`, chưa có atomic generation guard; thuộc P2-03/P2-04. M-06 vẫn IN PROGRESS.
- **Tiếp theo:** `P2-03` — chưa bắt đầu; chờ giao việc riêng.

### [2026-10-12] P2-03 — Message persistence

- **Trạng thái:** COMPLETED.
- **Đã thực hiện:** Mở rộng `/chat` nhận optional `session_id`; thiếu ID giữ nguyên stateless response `answer + sources`. Với session, cấp atomically hai sequence, ghi user `COMPLETED` và assistant `PENDING` trước generation, dùng chung `request_id`, rồi replace assistant sang `COMPLETED` kèm model/citations hoặc `FAILED` với mã an toàn. Usage để null vì pipeline hiện không trả metadata. Invalid/missing/deleted session lần lượt trả 422/404/410; chưa thêm one-generation guard của P2-04.
- **Files thay đổi:** `backend/app/conversation_models.py`, `backend/app/conversation_repository.py`, `backend/app/conversation_service.py`, `backend/app/api/chat.py`, `backend/app/schemas.py`, `backend/tests/test_chat_persistence.py`, `backend/scripts/smoke_message_persistence.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử PASS:** Focused 21/21; toàn bộ unit/API/in-memory regression 72/72; live persistent `/chat` trên Atlas/Qdrant/provider xác minh user/PENDING-before-generation, assistant COMPLETED, citations, request linkage và stable order; forced provider failure và empty output xác minh FAILED/error code an toàn; exact cleanup PASS. MongoDB/Qdrant connection, FastAPI startup `/health/dependencies`, `compileall`, `pip check` PASS.
- **Kiểm thử FAIL có nguyên nhân ngoài task:** `verify_cutover.py` retry 2 lần đều FAIL tại stateless `product_api_qa`, cleanup PASS; diagnostic an toàn xác nhận HTTP 502 `TooManyRequestsResponseError` từ OpenRouter. Nhánh stateless unit compatibility PASS và live persistent provider call trước đó PASS; không đổi hai lượt rate-limit thành PASS.
- **Tồn đọng / quyết định:** Sequence allocation là atomic nhưng chưa chặn hai generation đồng thời trên cùng session; P2-04 xử lý guard. Response chưa thêm message/request IDs để giữ backward compatibility; thuộc P3.
- **Tiếp theo:** `P2-04` — chưa bắt đầu; chờ giao việc riêng.

### [2026-10-12] P2-04 — Concurrency

- **Trạng thái:** COMPLETED.
- **Đã thực hiện:** Thêm persistent guard `active_generation_id/started_at` trên session. Mongo `find_one_and_update` atomically kiểm tra session active, nhận guard và cấp message sequence pair; request thứ hai cùng session trả 409 trước khi tạo messages. Guard chỉ release khi khớp owner `request_id` trong `finally`; assistant được terminal hóa và guard được release khi completion, provider/output error hoặc cancellation. DELETE session khi active trả 409. Stateless `/chat` không bị ảnh hưởng.
- **Files thay đổi:** `backend/app/conversation_models.py`, `backend/app/conversation_repository.py`, `backend/app/conversation_service.py`, `backend/tests/test_conversation_models.py`, `backend/tests/test_chat_persistence.py`, `backend/tests/test_conversation_concurrency.py`, `backend/scripts/smoke_message_persistence.py`, `backend/scripts/smoke_session_concurrency.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử:** Focused concurrency/conversation PASS 25/25; toàn bộ unit/API/in-memory regression PASS 76/76. Live HTTP + Atlas test PASS: hai `POST /chat` đồng thời chỉ một generation chạy, request hai 409, non-owner không release được, DELETE active 409, guard release sau completion/error/cancel, terminal history đúng 6 messages và exact cleanup PASS. MongoDB/Qdrant connection, `compileall`, `pip check` PASS.
- **Tồn đọng / quyết định:** Với sync provider call, transport disconnect không ngắt worker ngay; guard được giữ tới terminal thực tế. Process crash có thể để lại stale guard; automatic lease/reconciliation chưa triển khai, cần kiểm tra ở P2-05/operational recovery. Không triển khai streaming/P3–P5.
- **Tiếp theo:** `P2-05` — chưa bắt đầu; chờ giao việc riêng.

### [2026-10-12] P2-05 — Verification

- **Trạng thái:** COMPLETED; Giai đoạn 2 đạt điều kiện kết thúc.
- **Đã thực hiện:** Thêm live verification dùng ba FastAPI lifespan liên tiếp và một session UUID riêng trên MongoDB Atlas. Xác minh session/title cùng 8 messages còn nguyên sau restart; thứ tự `1…8`, pagination `3 + 5`, request linkage, citations, ba turn thành công và một assistant `FAILED/RAG_PIPELINE_ERROR`; kiểm tra guard đã release, UUID sai 422, session thiếu 404, tombstone 410 sau restart, default list loại session đã xóa và DELETE lặp lại idempotent. Generation trong script được mock deterministic để test persistence không phụ thuộc quota provider; cloud clients/routes/indexes/lifecycle vẫn là thật. Exact cleanup PASS.
- **Files thay đổi:** `backend/scripts/verify_phase2.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-01.md` (archive 5 entry cũ theo quy tắc giới hạn nhật ký).
- **Kiểm thử:** `python backend/scripts/verify_phase2.py` — PASS, MongoDB/Qdrant readiness + hai restart persistence/tombstone và cleanup; `python backend/scripts/smoke_session_concurrency.py` — PASS, concurrent reject/owner guard/completion-error-cancel và cleanup; `python -m unittest discover -s tests -v` từ `backend/` — PASS 76/76; Python 3.10.11 hiện tại và `pip check` — PASS.
- **Tồn đọng / quyết định:** Clean restart sau terminal state đã PASS. Hard process kill giữa provider call vẫn có thể để lại stale guard vì chưa có lease/reconciliation tự động; đây là giới hạn vận hành đã ghi trong README, không làm sai acceptance P2-05. Không triển khai response contract, SSE hoặc history-aware trong task này.
- **Tiếp theo:** `P3-01` — chưa bắt đầu; chờ giao việc riêng. `M-06` tiếp tục IN PROGRESS cho các gate P3–P5.

### [2026-10-12] P3-01 — JSON schema

- **Trạng thái:** COMPLETED; Giai đoạn 3 IN PROGRESS.
- **Đã thực hiện:** Mở rộng additive `/chat` response với `request_id`, nullable `session_id/user_message_id/assistant_message_id`, `answer`, arrays `sources/citations`, `metadata.mode/model`, nullable validated token `usage`, terminal `status` và nullable safe `error`. Pydantic bắt buộc mọi top-level field hiện diện: stateless có ba ID null; persistent cần đủ ID và trả đúng ID vừa ghi MongoDB; `COMPLETED` cần answer khác rỗng + error null; `FAILED` cần safe error. Persistent service trả ID/citations/usage đã normalize; hai field cũ `answer/sources` được giữ. Thêm OpenAPI example và live HTTP smoke cô lập.
- **Files thay đổi:** `backend/app/schemas.py`, `backend/app/api/chat.py`, `backend/app/conversation_service.py`, `backend/tests/test_chat_response_schema.py`, `backend/tests/test_chat_persistence.py`, `backend/scripts/smoke_response_contract.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-01.md`.
- **Kiểm thử:** Focused contract/persistence/concurrency — PASS 15/15; toàn bộ unit/API/in-memory regression — PASS 82/82. Live `smoke_response_contract.py` — PASS stateless/persistent contract, explicit nulls, durable ID linkage, Atlas history, MongoDB/Qdrant readiness và cleanup. Live `verify_phase2.py` — PASS hai restart persistence/tombstone và cleanup.
- **Tồn đọng / quyết định:** Stateless `citations=[]` ở P3-01; quy tắc candidate source/eligible citation thuộc P3-02. HTTP integration errors vẫn dùng status + FastAPI `detail`; unified error envelope/compatibility thuộc P3-04. Không triển khai SSE hoặc history-aware.
- **Tiếp theo:** `P3-02` — chưa bắt đầu; chờ giao việc riêng. `M-06` tiếp tục IN PROGRESS.

### [2026-10-12] P3-02 — Citation mapping

- **Trạng thái:** COMPLETED; Giai đoạn 3 IN PROGRESS.
- **Đã thực hiện:** Thêm mapper server-side dùng ordinal `[n]` trong answer để chọn candidate thứ `n` từ danh sách retrieved theo thứ tự context. `sources` giữ mọi candidate; `citations` chỉ chứa candidate được nhắc, có ba UUID hợp lệ và page null/không âm; duplicate, ordinal 0/out-of-range, metadata lỗi và UUID/citation object do model tự viết bị bỏ qua. Prompt yêu cầu dùng đúng ordinal và cấm tự tạo ID. API và persistence cùng recompute verified citations từ answer + server sources; Pydantic buộc mọi citation là member của source list. Persistent Mongo history lưu đúng tập citations trả về.
- **Files thay đổi:** `backend/app/citation_mapping.py`, `backend/app/rag/prompt.py`, `backend/app/api/chat.py`, `backend/app/conversation_service.py`, `backend/app/schemas.py`, `backend/tests/test_citation_mapping.py`, `backend/tests/test_chat_response_schema.py`, `backend/tests/test_chat_persistence.py`, `backend/scripts/smoke_response_contract.py`, `backend/scripts/smoke_citation_mapping.py`, `backend/scripts/verify_phase2.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-01.md`.
- **Kiểm thử:** Focused citation/schema/persistence/retriever — PASS 22/22; toàn bộ unit/API/in-memory regression — PASS 89/89. Live HTTP/Atlas smoke — PASS 2 candidates/1 verified citation, response-history match và cleanup. Read-only real Gemini embedding → Qdrant retrieval → Mongo active-version provenance — PASS 3 candidates/1 citation. Live P2 restart/history regression — PASS và cleanup.
- **Tồn đọng / quyết định:** Nếu provider không emit `[n]`, citations cố ý rỗng để không overclaim; sources vẫn cho biết candidates. Không parse hoặc tin UUID do model sinh. Chưa triển khai SSE/P3-03 hay unified HTTP error compatibility/P3-04.
- **Tiếp theo:** `P3-03` — chưa bắt đầu; chờ giao việc riêng. `M-06` tiếp tục IN PROGRESS.

### [2026-10-12] P3-03 — SSE schema

- **Trạng thái:** COMPLETED; Giai đoạn 3 IN PROGRESS.
- **Đã thực hiện:** Định nghĩa typed discriminated events `start`, `metadata`, `citation`, `delta`, `done`, `error` và strict data models. `start` mang request/session/user/assistant IDs và kiểm tra stateless/persistent; metadata mang model + candidate sources; citation phải thuộc source; delta là content chunk; done chỉ `COMPLETED`; error mang safe error và `FAILED/PARTIAL`. Transcript validator buộc start đầu tiên, sequence `1…n`, metadata trước content, citation trước delta, một terminal cuối cùng, done cần delta, error status khớp partial output. Client reconstruction nối `delta.content`; encoder sinh đúng `event:` + JSON `data:` + blank line.
- **Files thay đổi:** `backend/app/sse_schema.py`, `backend/tests/test_sse_schema.py`, `backend/scripts/smoke_sse_schema.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-01.md`.
- **Kiểm thử:** Focused SSE/JSON/citation schema — PASS 20/20; toàn bộ unit/API/in-memory regression — PASS 96/96; offline `smoke_sse_schema.py` — PASS event order, stable assistant ID, JSON wire frames, terminal và reconstructed answer.
- **Tồn đọng / quyết định:** P3-03 chỉ chốt contract; chưa tạo `/chat/stream`, chưa consume provider async stream, persist streaming lifecycle, xử lý disconnect/buffering hay metrics — các việc này thuộc P4. HTTP error compatibility còn ở P3-04.
- **Tiếp theo:** `P3-04` — chưa bắt đầu; chờ giao việc riêng. `M-06` tiếp tục IN PROGRESS.
