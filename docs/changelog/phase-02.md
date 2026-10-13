# Phase 2 — Nhật ký đã lưu trữ

> Các entry dưới đây được chuyển nguyên nội dung từ `CURRENT_CHANGE.md` theo quy tắc chỉ giữ 10–15 entry gần nhất.

### [2026-10-12] P4-02 — Live Groq verification hoàn tất

- **Trạng thái:** COMPLETED; Giai đoạn 4 COMPLETED.
- **Đã thực hiện:** Xác minh secret-safe `.env` dùng `GROQ_API_KEY`, official Groq OpenAI-compatible base và `LLM_MODEL=openai/gpt-oss-120b`; không còn biến OpenRouter. Kiểm tra read-only Groq model catalog xác nhận authentication và model availability, sau đó chạy provider smoke qua đúng LangChain `ChatOpenAI.astream()` runtime path. Không thay đổi API, retrieval pipeline, MongoDB/Qdrant data hay P5 runtime.
- **Files thay đổi:** `.env` (người dùng đổi model), `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`.
- **Kiểm thử:** Groq `/models` — PASS auth HTTP 200 và configured model listed; live `smoke_provider_stream.py` — PASS 14 valid text deltas, usage metadata present; focused provider/stream/query/context — PASS 34/34; toàn bộ unit/API/in-memory regression — PASS 145/145; `compileall`, Python 3.10.11 và `pip check` — PASS. Không in credential hoặc raw provider response.
- **Tồn đọng / quyết định:** P4-02 không còn blocker. Model availability/quota vẫn là phụ thuộc vận hành bên ngoài và smoke script có thể dùng lại để kiểm tra. P5-04 vẫn chưa bắt đầu.
- **Tiếp theo:** `P5-04` — chỉ triển khai khi được giao riêng; `M-06` tiếp tục IN PROGRESS.

### [2026-10-12] P4-02 — Chuyển provider sang Groq (xác minh live)

- **Trạng thái:** BLOCKED — implementation, cấu hình và regression PASS; live text delta chưa phát được do model không khả dụng.
- **Đã thực hiện:** Thay OpenRouter adapter bằng LangChain `ChatOpenAI` trỏ tới Groq OpenAI-compatible API; dùng `GROQ_API_KEY` dạng `SecretStr`, `OPENAI_BASE_URL` được kiểm tra đúng HTTPS host/path Groq và `LLM_MODEL` qua environment settings. Thay dependency manifest bằng `langchain-openai`, cập nhật smoke/test/docs và sửa `.env` từ website root sang API base chính thức mà không đọc/in credential. Khôi phục đúng CPython 3.10.11 cho `.venv`. Không thay retrieval, MongoDB/Qdrant data hay API contract.
- **Files thay đổi:** `.env`, `.env.example`, `backend/requirements.txt`, `backend/app/config.py`, `backend/app/rag/llm.py`, `backend/app/rag/chain.py`, `backend/app/rag/pipeline.py`, `backend/scripts/smoke_provider_stream.py`, `backend/tests/test_llm.py`, `backend/tests/test_cloud_connections.py`, `backend/tests/test_context_budget.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`.
- **Kiểm thử:** Kiểm tra cấu hình secret-safe — PASS key/base/model present, official Groq API base, không còn biến OpenRouter; Python 3.10.11 và `pip check` — PASS; focused provider/stream/query/context — PASS 34/34; toàn bộ unit/API/in-memory regression — PASS 145/145; `compileall` — PASS. Groq `/models` read-only — auth PASS HTTP 200 nhưng configured model không listed. Live `smoke_provider_stream.py` — BLOCKED `OpenAIModelNotFoundError`, không in raw response/credential.
- **Tồn đọng / quyết định:** Giữ nguyên model người dùng chọn, không tự đổi model. `llama-3.3-70b-versatile` hiện không khả dụng cho API/tier này; cần đổi `LLM_MODEL` sang model đang listed (mặc định tài liệu mẫu là `openai/gpt-oss-120b`) rồi chạy lại live smoke. Chỉ tích P4-02 khi nhận được text delta thật. P5-04 vẫn tạm dừng.
- **Tiếp theo:** Người dùng chọn/cấu hình một Groq model khả dụng; chạy lại P4-02 live smoke và regression liên quan. Không tự động triển khai P5-04.

### [2026-10-12] P5-03 — Query rewriting

- **Trạng thái:** COMPLETED; Giai đoạn 5 IN PROGRESS. P4-02 tiếp tục tạm bỏ qua/BLOCKED.
- **Đã thực hiện:** Thêm lexical dependency detector chỉ gọi provider khi query có tham chiếu context và có selected whole-turn history. Thêm LangChain `ainvoke` adapter với prompt cấm answer/thêm fact, timeout riêng và output một dòng. Result luôn giữ `original_query` cho final generation, tách `retrieval_query`; candidate phải khác original, đúng giới hạn và pass lexical provenance guard từ original/history, đồng thời phải mang antecedent từ history. Entity/số/fact mới, multiline, unchanged, oversized, provider error/timeout đều fallback original an toàn. Metrics ghi provider call, added latency, input/output/total token cost và `usage_source=provider|estimated|none`; không suy đoán USD cost. Chưa nối vào `/chat` hoặc retriever.
- **Files thay đổi:** `.env.example`, `backend/app/config.py`, `backend/app/query_rewriting.py`, `backend/tests/test_query_rewriting.py`, `backend/tests/test_context_budget.py`, `backend/scripts/smoke_query_rewriting.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`.
- **Kiểm thử:** Focused rewrite/context/history/streaming — PASS 27/27; toàn bộ unit/API/in-memory regression — PASS 144/144; offline `smoke_query_rewriting.py` — PASS independent zero-call, dependent rewrite, original preservation, unsupported-fact rejection, safe fallback và token/latency metrics; `compileall`, `pip check`, `git diff --check` — PASS.
- **Tồn đọng / quyết định:** Lexical provenance ngăn token/entity/số mới nhưng không chứng minh semantic entailment hoàn hảo; prompt guard và fallback giảm rủi ro, evaluation tiếp tục ở P5-05. Detector bảo thủ có thể bỏ sót follow-up không có marker và khi đó dùng original query. Live OpenRouter không chạy vì P4-02 vẫn bị free-tier 429; logic provider được xác minh deterministic. Runtime dùng rewritten query cho retrieval và original query cho final prompt thuộc P5-04.
- **Tiếp theo:** `P5-04` — chưa bắt đầu; chờ giao việc riêng. Không tự động triển khai P5-04 hoặc quay lại P4-02.

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
