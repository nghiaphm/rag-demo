# Phase 3–4 — Nhật ký đã lưu trữ

> Các entry chuyển nguyên vẹn từ CURRENT_CHANGE.md ngày 2026-10-13 để giữ 15 entry gần nhất.

### [2026-10-12] P4-04 — Error/disconnect

- **Trạng thái:** COMPLETED; P4-02 giữ DEFERRED/BLOCKED theo quyết định người dùng.
- **Đã thực hiện:** Thêm deadline `STREAM_TIMEOUT_SECONDS` cho toàn provider stream. Lỗi provider/output rỗng/timeout/persistence sau headers phát đúng một terminal SSE `error` an toàn với `FAILED` hoặc `PARTIAL`; không retry sau output. Timeout và cancel đóng async iterator. Disconnect/cancel tại cả prefix hoặc delta yield cố finalize assistant bằng `RAG_STREAM_CANCELLED` rồi release generation guard; không phát terminal frame khi client đã rời kết nối. Lỗi dependency/retrieval/session trước headers tiếp tục trả HTTP phù hợp. Cập nhật cache headers thành `no-cache, no-transform`, giữ `X-Accel-Buffering: no`.
- **Files thay đổi:** `backend/app/api/chat.py`, `backend/app/config.py`, `.env.example`, `backend/tests/test_chat_stream.py`, `backend/scripts/smoke_stream_errors.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-01.md`.
- **Kiểm thử:** Focused stream/lifecycle/SSE/provider — PASS 33/33; toàn bộ unit/API/in-memory regression — PASS 115/115; live `smoke_stream_errors.py` — PASS provider partial error, timeout, Atlas `PARTIAL/FAILED`, guard release và exact cleanup; `compileall`, `pip check`, `git diff --check` — PASS.
- **Tồn đọng / quyết định:** Disconnect thực tế không thể gửi SSE terminal vì transport đã đóng; durable state vẫn được finalize best-effort. Nếu MongoDB cũng unavailable trong cleanup thì không có distributed recovery trong request; stale-guard reconciliation vẫn là giới hạn vận hành. Metrics first-event/first-content/total latency và reconstruction suite thuộc P4-05. P4-02 không được chạy lại cho tới khi người dùng yêu cầu.
- **Tiếp theo:** `P4-05` — chưa bắt đầu; chờ giao việc riêng. Không tự động quay lại P4-02.

### [2026-10-12] P4-03 — Lifecycle

- **Trạng thái:** COMPLETED; Giai đoạn 4 vẫn IN PROGRESS vì P4-02 còn BLOCKED.
- **Đã thực hiện:** Cho phép `/chat/stream` với `session_id`. Sau khi chuẩn bị retrieval/prompt và trước SSE headers, service atomically tạo user message, assistant `PENDING → STREAMING` và giữ guard. Stream tích lũy content/usage; thành công mới finalize `COMPLETED`, provider lỗi hoặc output rỗng ghi `PARTIAL`/`FAILED` đúng content đã phát, kèm error code an toàn và release guard. SSE `start` persistent mang đúng durable IDs; `/chat` JSON không đổi.
- **Files thay đổi:** `backend/app/api/chat.py`, `backend/app/conversation_service.py`, `backend/app/conversation_repository.py`, `backend/app/conversation_models.py`, `backend/tests/test_chat_stream.py`, `backend/tests/test_chat_persistence.py`, `backend/scripts/smoke_stream_lifecycle.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử:** Focused lifecycle/provider/SSE — PASS 28/28; toàn bộ unit/API/in-memory regression — PASS 110/110; live `smoke_stream_lifecycle.py` — PASS Atlas persistent SSE, content/usage, terminal state, guard release và exact cleanup; `compileall`, `pip check`, `git diff --check` — PASS. Live `smoke_provider_stream.py` — BLOCKED: `TooManyRequestsResponseError`, không in credentials/raw response.
- **Tồn đọng / quyết định:** P4-03 dùng provider deterministic cho smoke persistence, không tiêu thụ quota hoặc ghi document data. P4-02 chỉ được đánh dấu COMPLETED sau live OpenRouter async smoke PASS. Cancel/disconnect, lỗi persistence sau headers, buffering/timeout thuộc P4-04.
- **Tiếp theo:** Xác minh lại `P4-02` khi provider khả dụng; P4-04 chưa bắt đầu và không tự động triển khai.

### [2026-10-12] P4-02 — Provider integration (xác minh lại)

- **Trạng thái:** BLOCKED — implementation và unit/mock verification PASS, nhưng live OpenRouter vẫn trả HTTP 429 sau khi người dùng thông báo đã reset limit.
- **Đã thực hiện:** Tách retrieval + prompt preparation khỏi provider stream; `/chat/stream` dùng LangChain/OpenRouter `astream()` sau headers. Chuẩn hóa content string/text block thành delta, bỏ qua control/empty/non-text chunk, chuẩn hóa `usage_metadata` hoặc OpenAI-style usage và giữ usage xuất hiện ở chunk không có text để đưa vào `done`. Giữ stateless, không persist message, không buffer answer để gắn citation sau delta và không xử lý exception sau headers — đúng ranh giới P4-03/P4-04.
- **Files thay đổi:** `backend/app/rag/pipeline.py`, `backend/app/api/chat.py`, `backend/tests/test_streaming_pipeline.py`, `backend/tests/test_chat_stream.py`, `backend/scripts/smoke_stream_endpoint.py`, `backend/scripts/smoke_provider_stream.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-01.md`.
- **Kiểm thử:** Xác minh cấu hình dưới dạng boolean — PASS cho API key/base URL/model; focused provider/endpoint/SSE/metrics — PASS 25/25; toàn bộ unit/API/in-memory regression — PASS 120/120; `compileall` và `pip check` — PASS. Key-management auth — PASS, key vẫn là free tier; configured model vẫn listed/free. Live `smoke_provider_stream.py` chạy hai lần hữu hạn, lần hai sau cửa sổ rate-limit 10 giây — BLOCKED `TooManyRequestsResponseError`. Request chẩn đoán tối thiểu xác nhận HTTP 429 thuộc nhóm free-tier limit/rate-limit/credit; không in credentials, model ID, endpoint cấu hình hay raw response.
- **Tồn đọng / quyết định:** Việc reset limit chưa tạo allowance dùng được cho API key hiện tại. Chỉ đánh dấu P4-02 COMPLETED khi live `astream()` phát được text delta thật. Không tự đổi sang model trả phí hoặc API key khác khi chưa có chỉ dẫn. Citation realtime cố ý rỗng vì contract bắt citation trước delta; lifecycle/error/metrics đã hoàn thành ở P4-03…P4-05.
- **Tiếp theo:** Người dùng cần nạp credit/đổi sang key có paid allowance, hoặc xác nhận model/key khác được phép dùng; sau đó chạy lại live smoke. Không tự động chuyển task.

### [2026-10-12] P4-01 — Endpoint

- **Trạng thái:** COMPLETED; Giai đoạn 4 IN PROGRESS; M-06 tiếp tục IN PROGRESS.
- **Đã thực hiện:** Thêm `POST /chat/stream` giữ nguyên `/chat` JSON. Endpoint stateless gọi RAG hiện có trước headers, sau đó phát typed SSE `start → metadata → citation* → delta → done` với `Content-Type: text/event-stream`, `Cache-Control: no-cache` và `X-Accel-Buffering: no`; transcript được xác minh bằng contract P3-03. Error trước headers trả JSON failure envelope an toàn HTTP 502. `session_id` trả HTTP 409 rõ ràng vì chưa có streaming lifecycle/persistence ở P4-03. P4-01 chỉ phát một delta từ answer hoàn tất; không tiêu thụ provider async stream, không persist streaming turn, không xử lý lỗi sau headers/disconnect.
- **Files thay đổi:** `backend/app/api/chat.py`, `backend/tests/test_chat_stream.py`, `backend/scripts/smoke_stream_endpoint.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-01.md`.
- **Kiểm thử:** Focused stream/SSE/chat — PASS 22/22; toàn bộ unit/API/in-memory regression — PASS 104/104; live `smoke_stream_endpoint.py` — PASS cloud readiness, typed event order/sequence và stateless POST SSE, không ghi dữ liệu; `compileall` và `pip check` — PASS.
- **Tồn đọng / quyết định:** Native `EventSource` không gửi POST body, README hướng dẫn `fetch`/`ReadableStream`. Async provider token deltas thuộc P4-02; persistent message lifecycle P4-03; post-header error, cancel/disconnect P4-04; metrics sâu P4-05.
- **Tiếp theo:** `P4-02` — chưa bắt đầu; chờ giao việc riêng. Không tự động chuyển task.

### [2026-10-12] P4-05 — Metrics/tests

- **Trạng thái:** COMPLETED; Giai đoạn 4 vẫn IN PROGRESS vì P4-02 đang DEFERRED/BLOCKED.
- **Đã thực hiện:** Thêm monotonic one-shot tracker đo từ đầu request qua retrieval/persistence tới logical terminal: `first_event_ms`, nullable `first_content_ms`, `total_latency_ms`, `delta_count`, request ID, mode và safe outcome. Production ghi structured log không chứa question/answer/sources/credentials; lỗi metrics không ảnh hưởng response. Mở rộng endpoint tests cho success reconstruction, output rỗng, lỗi giữa stream, timeout, persistence failure, cancel/disconnect và durable lifecycle; metric chỉ ghi một lần ở success/error/cancel/pre-header failure.
- **Files thay đổi:** `backend/app/stream_metrics.py`, `backend/app/api/chat.py`, `backend/tests/test_stream_metrics.py`, `backend/tests/test_chat_stream.py`, `backend/scripts/smoke_stream_metrics.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-01.md`.
- **Kiểm thử:** Focused metrics/stream/lifecycle/SSE/provider — PASS 38/38; toàn bộ unit/API/in-memory regression — PASS 120/120; live `smoke_stream_metrics.py` — PASS first-event/first-content/total latency, success/empty/partial transcripts, client reconstruction, Atlas terminal states/guard release và exact cleanup; `compileall`, `pip check`, `git diff --check` — PASS.
- **Tồn đọng / quyết định:** Metric là structured application log, chưa có Prometheus/exporter/dashboard. Total latency kết thúc tại logical terminal trước khi terminal frame được network flush; đây là server-side processing metric, không phải browser-perceived latency. P4-02 giữ deferred cho tới khi người dùng yêu cầu chạy lại.
- **Tiếp theo:** `P5-01` — chưa bắt đầu; chờ giao việc riêng. Không tự động triển khai hoặc quay lại P4-02.

### [2026-10-12] P3-04 — Compatibility/tests

- **Trạng thái:** COMPLETED; Giai đoạn 3 COMPLETED; M-06 tiếp tục IN PROGRESS.
- **Đã thực hiện:** Giữ `/chat` tương thích additive và không đổi URL/version: request không có `session_id` vẫn stateless, client cũ tiếp tục đọc `answer`/`sources`. Generation failure stateless trả HTTP 502 với full logical `ChatResponse`; persistent failure dùng safe `ConversationGenerationError` để trả đúng durable request/user/assistant IDs của failed turn, `status=FAILED`, `answer=null`, arrays rỗng, `usage=null` và không lộ raw provider detail. Validation/session/concurrency/persistence error trước logical reply giữ status/`detail` cũ. Bổ sung coverage cho Pydantic validation, missing usage, no-result fallback, nhiều documents/citations và legacy projection. Khôi phục đúng CPython 3.10.11 mà `.venv` đang tham chiếu, không đổi dependencies.
- **Files thay đổi:** `backend/app/api/chat.py`, `backend/app/conversation_service.py`, `backend/tests/test_chat_persistence.py`, `backend/scripts/smoke_response_contract.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-01.md`.
- **Kiểm thử:** Focused schema/citation/persistence/concurrency — PASS 26/26; toàn bộ unit/API/in-memory regression — PASS 100/100. Live FastAPI lifespan + `/health/dependencies` + MongoDB Atlas/Qdrant Cloud compatibility lifecycle — PASS legacy projection, fallback, 2-document candidates/citations, `usage=null`, persistent forced failure/durable IDs và exact cleanup. `compileall`, `pip check`, secret scan và `git diff --check` — PASS.
- **Tồn đọng / quyết định:** Không triển khai `/chat/stream`; runtime streaming thuộc P4. Lỗi xảy ra trước khi có logical reply vẫn dùng FastAPI `detail`, tránh tạo persistent IDs giả. M-06 chưa hoàn tất cho tới runtime SSE/history-aware gates P4–P5; stale guard recovery và thu hẹp MongoDB role vẫn là giới hạn vận hành.
- **Tiếp theo:** `P4-01` — chưa bắt đầu; chờ giao việc riêng. Không tự động chuyển task.
