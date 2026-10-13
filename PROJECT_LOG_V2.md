# PROJECT_LOG_V2 — Kế hoạch triển khai RAG V2 dành cho Coding Agent

> **Vai trò:** Tài liệu điều phối ổn định: kiến trúc đã chốt, thứ tự task, checklist và tiêu chí nghiệm thu. **Không ghi nhật ký triển khai chi tiết tại đây**; ghi vào [`CURRENT_CHANGE.md`](./CURRENT_CHANGE.md).
>
> **Trạng thái ban đầu:** PLANNED / NOT VERIFIED. Roadmap dựa trên README V1, Research_AI_RAG và các quyết định đã thống nhất. Chưa có task V2 nào được xác minh hoàn thành. Agent phải kiểm tra source code thực tế trước khi sửa.

## 0. Quy tắc bắt buộc cho Agent

1. Mỗi phiên làm việc: đọc `PROJECT_LOG_V2.md`, phần đầu và mục mới nhất của `CURRENT_CHANGE.md`, `README.md`, source/test liên quan và `.env.example`. Không in hoặc commit `.env`, API key hay tài liệu riêng tư.
2. Đối chiếu README với code đang checkout; **audit trước khi sửa**. Xác định task đầu tiên chưa hoàn thành, không bị chặn, trong giai đoạn hiện hành. Nếu phụ thuộc task M-series thì xử lý đúng prerequisite được giao.
3. **Mỗi lần chỉ làm một task trong phạm vi được giao.** Không tự chuyển task/giai đoạn, thêm frontend, Agent, LangGraph, WebSocket, Redis, S3 hoặc auth đầy đủ khi chưa được yêu cầu. Vẫn áp dụng biện pháp bảo vệ tối thiểu cho endpoint hiện có.
4. Trước thay đổi: nêu hiện trạng, file dự kiến sửa, phụ thuộc và cách nghiệm thu. Giữ tính năng/API baseline nếu có thể; breaking change phải được giải thích, có hướng chuyển đổi và test.
5. Sau thay đổi: chạy kiểm thử phù hợp; ghi chính xác **PASS / FAIL / NOT RUN**, lệnh và kết quả ngắn. Thiếu credentials/hạ tầng thì ghi BLOCKED hoặc NOT RUN; không tự nhận PASS. Không tích `[x]` khi chưa có bằng chứng.
6. **Cập nhật hai file đúng trách nhiệm:** `PROJECT_LOG_V2.md` chỉ đổi checkbox, dashboard, task vừa xong/task tiếp theo, blockers và quyết định kiến trúc nếu được duyệt; `CURRENT_CHANGE.md` ghi một mục ngắn gồm thay đổi thực tế, files, test, tồn đọng. Không chép log dài vào file kế hoạch.
7. Không tuyên bố migration thành công khi chưa kiểm tra số tài liệu/chunks, retrieval, metadata, delete và regression. Không xóa hạ tầng cũ sớm.
8. ID ổn định xuyên MongoDB/Qdrant/API; timestamps dùng UTC. Xác thực scope/quyền trước khi truy xuất tài liệu và file. External provider nhận chunk/context nên chỉ test bằng dữ liệu không nhạy cảm khi chưa duyệt chính sách dữ liệu.
9. Chỉ hỏi người phụ trách khi gặp xung đột kiến trúc thực sự, thao tác phá hủy hoặc thiếu điều kiện bắt buộc. Nếu không, làm đúng phạm vi nhỏ nhất và ghi rõ giả định.

**Quy ước trạng thái:** `[ ]` chưa xong/chưa xác minh · `[x]` hoàn thành **có bằng chứng** · `IN PROGRESS` đang làm · `BLOCKED` bị chặn. Không đánh dấu hoàn thành chỉ từ mô tả trong README.

## 1. Kiến trúc V2 đã chốt

| Lớp | Quyết định | Trách nhiệm |
| --- | --- | --- |
| Backend | Python + FastAPI | API-first; giữ `/chat` JSON baseline hoặc version hóa có hướng chuyển đổi |
| Điều phối RAG | LangChain / LCEL | Ingestion, retrieval, context và generation; chưa cần LangGraph |
| LLM | Groq qua OpenAI-compatible API | External generation; `GROQ_API_KEY`, `OPENAI_BASE_URL` và model cấu hình trong settings |
| Embedding | Google Gemini API | Embedding query/chunks với cấu hình tương thích |
| Application DB | **MongoDB Atlas (cloud; cluster đã được người dùng tạo)** | Document metadata, versions, ingestion jobs, sessions, messages; backend kết nối qua URI trong biến môi trường |
| Vector DB | **Qdrant Cloud (cluster đã được người dùng tạo)** | Chunk embeddings, payload, semantic retrieval; thay pgvector; kết nối bằng URL và API key qua settings |
| File gốc | **Local File Storage** | Qua storage abstraction để đổi sang S3-compatible sau này; **chưa làm S3** |
| Infrastructure | Backend local + dịch vụ cloud | **Không tạo container MongoDB hay Qdrant**; backend kết nối MongoDB Atlas và Qdrant Cloud qua mạng. Docker Compose chỉ giữ service local thực sự cần thiết sau audit |
| Phong cách | Modular Monolith | Các service và adapter phân định rõ trong một backend |

**MongoDB Atlas đã chốt:** cluster đã được tạo; IP Access List hiện có `0.0.0.0/0` (cho phép kết nối từ mọi IPv4, **không phải** quyền truy cập miễn xác thực). Chỉ chấp nhận tạm cho development: ưu tiên thu hẹp về IP hiện tại/VPN hoặc private networking khi có thể; dùng DB user ít quyền, mật khẩu mạnh, TLS, không lộ URI trong log/commit, cân nhắc rotate credentials sau giai đoạn mở rộng truy cập. Agent **không được tự sửa Atlas network rules hoặc giả định đã xác minh kết nối**. `.env.example` chỉ chứa placeholder `MONGODB_URI`, `MONGODB_DB_NAME`; URI thật nằm trong `.env` không commit.

**Qdrant Cloud đã chốt:** người dùng đã tạo cluster. Agent kiểm tra hai biến `QDRANT_URL` và `QDRANT_API_KEY` trong `.env` (chỉ kiểm tra hiện diện/định dạng và thử kết nối an toàn; **không in giá trị**). `.env.example` chỉ ghi placeholder; `.env` không commit. Xác minh endpoint HTTPS, quyền API key, network/TLS, collection và dimension trước khi tạo/migrate dữ liệu. Việc cluster đã tạo **không đồng nghĩa** kết nối, schema hoặc migration đã PASS. Không tự tạo Qdrant local/Docker hay sửa/xóa cluster cloud. Nếu credentials từng bị lộ đầy đủ, yêu cầu rotate key.

**Data ownership:** MongoDB là nguồn sự thật của lifecycle tài liệu/hội thoại; Qdrant là retrieval index có thể dựng lại; file storage giữ bytes gốc. Không lưu toàn bộ file gốc vào MongoDB document thông thường hoặc Qdrant. Payload Qdrant có thể giữ chunk text để retrieval nhanh.

**Baseline mô tả bởi README V1 (cần kiểm tra bằng code):** `/health`, `/documents/upload`, `/documents`, `/documents/{document_id}`, `/chat`; PDF/MD/TXT loader; OpenRouter, Gemini, pgvector; evaluation corpus 3 tài liệu/9 cases; document ID theo filename; delete chỉ xóa vectors mà giữ file. Không xem đây là xác nhận trạng thái source hiện tại.

**Ngoài phạm vi V2:** Frontend, triển khai S3, Agent/tool-calling, LangGraph, GraphRAG, OCR/DOCX nâng cao, tối ưu scale lớn, IAM multi-tenant đầy đủ. Không đưa tài liệu nhạy cảm thật lên hệ thống nhiều người dùng trước khi có authentication, quyền theo tài liệu và đánh giá xử lý dữ liệu bởi external provider.

## 2. Thứ tự và bảng trạng thái tiến độ

**Thứ tự:** Giai đoạn 1 → 2 → 3 → 4 → 5. Task migration `M-01…M-05` bắt đầu **trong Giai đoạn 1**, `M-06` kiểm tra xuyên các giai đoạn tiếp theo; **không phải Giai đoạn 6**. Không nghiệm thu Giai đoạn 1 nếu luồng Qdrant index/retrieve chưa smoke-test thành công.

| Workstream | Trạng thái | Điều kiện kết thúc |
| --- | --- | --- |
| Giai đoạn 1 — Metadata và lưu trữ tài liệu | COMPLETED | Upload → lưu → index Qdrant → list/get → delete/re-index đã xác minh |
| Giai đoạn 2 — Session và Message Persistence | COMPLETED — P2-01…P2-05 | Hội thoại lưu bền vững, thứ tự đúng, kiểm soát concurrent generation |
| Giai đoạn 3 — Response Contract | COMPLETED — P3-01…P3-04 | JSON/SSE schema, compatibility và failure contract đã test |
| Giai đoạn 4 — SSE Streaming API | COMPLETED — P4-01…P4-05 | Groq live async stream, transport, lifecycle, errors và metrics đều PASS |
| Giai đoạn 5 — History-aware RAG | COMPLETED — P5-01…P5-06 | History loader, budget, rewrite, scoped integration, evaluation và final docs đã xác minh |
| M — Migration pgvector → Qdrant Cloud | COMPLETED — M-01…M-06 | Cutover và regression xuyên document/session/JSON/SSE/history-aware đều PASS |

- **Giai đoạn hiện tại:** Toàn bộ Giai đoạn 1–5 và workstream `M-01`…`M-06` đã COMPLETED.
- **Task vừa hoàn thành:** `M-06` — live cross-phase regression cho selected scope, history, JSON/SSE, citation/persistence và provider path đã PASS.
- **Task tiếp theo:** Không còn task chưa hoàn thành trong roadmap V2 hiện tại; chờ phạm vi mới được giao.
- **Blockers:** Không có blocker nghiệm thu. Các giới hạn vận hành còn lại đã ghi trong README, không bị trình bày như chức năng đã có.
- **Chi tiết nhật ký:** [`CURRENT_CHANGE.md`](./CURRENT_CHANGE.md).

## 3. Quy ước kỹ thuật chung

### ID và trạng thái

- Sử dụng ID ổn định: `document_id`, `version_id`, `chunk_id`, `session_id`, `user_message_id`, `assistant_message_id`, `request_id`. Chọn một quy tắc `_id` MongoDB nhất quán; API chuyển đổi hợp lệ. Qdrant point ID phải hợp lệ (có thể dùng UUID `chunk_id`).
- Dùng ID nhất quán trong MongoDB, Qdrant payload, citation và response. Citation nên gắn `version_id` để truy ngược đúng phiên bản.
- Document: `UPLOADED → PROCESSING → INDEXED | FAILED`. Khi cập nhật, index version mới và xác minh xong rồi mới đổi `active_version_id`; không xóa index active trước.
- Assistant message: `PENDING → STREAMING → COMPLETED | PARTIAL | FAILED` (chỉ thêm `CANCELLED` nếu xử lý đồng bộ ở mọi nơi). Disconnect/lỗi provider không được ghi `COMPLETED` giả.
- V2 giới hạn **một assistant generation đang hoạt động trên mỗi session** bằng cơ chế atomic tại persistence layer, không chỉ boolean trong một process. Giải phóng guard ở terminal state.

### An toàn lưu trữ

- Storage abstraction tối thiểu: `save`, `open/read`, `delete`, `exists`; dùng storage key opaque, không dùng nguyên filename của người dùng làm đường dẫn. Chặn path traversal, giới hạn dung lượng/loại file, không lộ lỗi nội bộ.
- Soft delete/unpublish phải loại document khỏi retrieval ngay bằng eligibility/filter; cleanup Qdrant và raw file có retry/đối soát. Chốt rõ soft/hard delete vì ba storage không có distributed transaction chung.
- Storage key theo version, ví dụ `documents/{document_id}/{version_id}/original.ext`; lưu checksum. Qdrant payload tối thiểu: `document_id`, `version_id`, `chunk_id`, `chunk_index`, `file_name`, `page` nếu có, `chunk_text`, scope nếu áp dụng.
- Với single-user development, scope mặc định là toàn bộ tài liệu active. Khi có authentication phải áp scope server-side; không tin tenant filter do client tự gửi.

### Response và streaming

- JSON non-stream và SSE biểu diễn **cùng một logical assistant reply**.
- Tên SSE thống nhất: `start`, `metadata`, `citation`, `delta`, `done`, `error`; không dùng lẫn `completed`/`done` làm event type. `done` chỉ thành công; `error` là terminal failure.
- SSE: `Content-Type: text/event-stream`, `event: <name>`, `data: <JSON>`; delta là content chunk, không giả định một token. Cấu hình no-buffering/timeout phù hợp.
- `start` mang IDs; `done` mang status/usage nếu provider trả; `error` chỉ trả code/message an toàn và terminal status. Citation chỉ gắn chunk thực có trong retrieval; phân biệt candidate sources và citation được dùng.
- Đo time-to-first-event, time-to-first-content-delta, tổng latency. Sau khi response header gửi, phải dùng SSE `error`, không cố đổi HTTP status. Tránh retry tự động sau khi đã emit partial output.

## 4. Giai đoạn 1 — Document Metadata & File Storage

**Mục tiêu:** quản lý document lifecycle bằng **MongoDB Atlas (cloud)**, file gốc trên local qua abstraction; index bằng **Qdrant Cloud**. Không triển khai MongoDB hoặc Qdrant local/Compose. Trạng thái cluster đã tạo và `0.0.0.0/0` do người dùng cung cấp; kết nối thực tế vẫn cần được Agent kiểm thử an toàn. Làm các prerequisite M-series song song theo dependency.

- [x] **P1-01 — Audit baseline:** kiểm tra source/requirements, routes, file upload/index/delete, scripts, eval, config và coupling pgvector; ghi nhận smoke tests. Phối hợp `M-01`.
- [x] **P1-02 — Kết nối MongoDB Atlas:** kiểm tra dependency/driver phù hợp và cấu hình `MONGODB_URI`, `MONGODB_DB_NAME` qua settings/`.env.example` (chỉ placeholder); tạo client lifecycle khi FastAPI startup/shutdown, ping/readiness có timeout và báo lỗi an toàn; xây repository/adapter; xác minh quyền DB tối thiểu, TLS/URI `mongodb+srv://` nếu cluster cung cấp, không log URI/secret; **không thêm MongoDB vào Docker Compose, không tạo cluster mới và không tự thay đổi IP Access List**.
- [x] **P1-03 — Document models/indexes trên MongoDB Atlas:** `documents`, `document_versions`, `ingestion_jobs`; ID độc lập filename, checksum, unique/indexes, status và active version.
- [x] **P1-04 — File storage abstraction:** local adapter (save/read/exists/delete); opaque versioned storage key, validation, download/read có kiểm soát; không xây S3 adapter bây giờ.
- [x] **P1-05 — Ingestion tích hợp:** upload raw file → metadata `UPLOADED/PROCESSING` → parse/chunk/embed → upsert Qdrant → verify → `INDEXED` hoặc `FAILED`; xử lý retry/reconciliation, không phá active version khi fail.
- [x] **P1-06 — Document APIs:** upload/list/get/delete/update/re-index và response rõ ràng; delete/unpublish loại ngay khỏi retrieval, cleanup theo chính sách đã chốt; ghi nhận giữ hay xóa file.
- [x] **P1-07 — Verification:** kiểm tra upload, file gốc, metadata/page, số chunk, Qdrant retrieval, version switching, failed re-index, delete không còn retrieve, regression/eval; cập nhật README.

**Điều kiện kết thúc:** Luồng document end-to-end có test; lỗi re-index không làm mất active version; document bị xóa không còn được tìm thấy; Qdrant hoạt động thay pgvector.

## 5. Giai đoạn 2 — Session & Message Persistence

**Mục tiêu:** lưu session/messages bền vững trong MongoDB, trước tiên tích hợp với non-streaming hiện có.

- [x] **P2-01 — Models/indexes:** `sessions` (ID, title, scope, timestamps, optional user) và `messages` (session, role, content, status, citations, model, usage, timestamps, request ID); index thứ tự ổn định.
- [x] **P2-02 — Session APIs:** create/list/get/update title/delete; phân trang history, xử lý ID sai/session đã xóa, quy tắc xóa message liên quan.
- [x] **P2-03 — Message persistence:** lưu user message trước generation, lưu assistant success/failure. Chốt `/chat` không session giữ stateless hay tự tạo session; đảm bảo backward compatibility.
- [x] **P2-04 — Concurrency:** một active generation/session bằng atomic guard, giải phóng khi hoàn tất/lỗi/hủy; test hai request đồng thời.
- [x] **P2-05 — Verification:** restart backend vẫn tải session/history; thứ tự, pagination, invalid/deleted session, failed generation; cập nhật README.

**Điều kiện kết thúc:** Session/messages khôi phục được sau restart; thứ tự đúng; concurrent same-session request tuân thủ chính sách đã ghi.

## 6. Giai đoạn 3 — Response Contract

**Mục tiêu:** một schema logical reply, độc lập transport/provider.

- [x] **P3-01 — JSON schema:** `request_id`, `session_id`, `user_message_id`, `assistant_message_id`, `answer`, `sources/citations`, `metadata`, `usage`, `status`, `error`; quy định optional/null.
- [x] **P3-02 — Citation mapping:** chỉ map `chunk_id`, `document_id`, `version_id`, page từ tài liệu thực và đủ điều kiện; không tin citation ID do LLM tự tạo; phân biệt retrieved candidates và cited sources.
- [x] **P3-03 — SSE schema:** định nghĩa `start`, `metadata`, `citation`, `delta`, `done`, `error`, thứ tự event, terminal rules, cách ghép nội dung và ID của assistant message.
- [x] **P3-04 — Compatibility/tests:** Pydantic validation, lỗi/usage không có, fallback no-results, nhiều documents; giữ client `/chat` cũ hoặc có version/migration rõ ràng.

**Điều kiện kết thúc:** Có ví dụ JSON/SSE transcript và test schema/citation; không lộ raw provider response/secrets.

## 7. Giai đoạn 4 — SSE Streaming API

**Mục tiêu:** stream delta từ LLM qua SSE và ghi lifecycle assistant message vào MongoDB.

- [x] **P4-01 — Endpoint:** thêm `POST /chat/stream` (ví dụ); giữ `/chat` JSON; hướng dẫn fetch-stream vì native EventSource không gửi POST body trực tiếp.
- [x] **P4-02 — Provider integration:** consume LangChain/Groq OpenAI-compatible async stream, chuẩn hóa text delta; bỏ qua chunk không có text hợp lệ, ghi usage nếu có. Groq authentication và configured-model availability PASS; live `astream()` phát 14 text delta hợp lệ kèm usage metadata; focused 34/34 và full regression 145/145 PASS.
- [x] **P4-03 — Lifecycle:** tạo assistant message trước streaming, tích lũy content để persist, phát event theo thứ tự, chỉ ghi `COMPLETED` khi thành công; `PARTIAL/FAILED` đúng thực tế.
- [x] **P4-04 — Error/disconnect:** trước headers trả HTTP error phù hợp; sau headers gửi terminal SSE `error`; dừng downstream nếu có thể, tránh output lặp do retry; kiểm tra buffering/timeout.
- [x] **P4-05 — Metrics/tests:** first-event, first-content, total latency; mock provider, output rỗng, lỗi giữa stream, disconnect/cancel, persistence và client reconstruction.

**Điều kiện kết thúc:** Client nhận nội dung tăng dần; stream kết thúc một lần; trạng thái/content MongoDB khớp kết quả; error/cancel tests đạt.

## 8. Giai đoạn 5 — History-aware RAG

**Mục tiêu:** hỏi đáp nhiều lượt, chọn history có giới hạn, cải thiện follow-up retrieval.

- [x] **P5-01 — History loader:** lấy message đúng session/scope/thứ tự; mặc định loại assistant `PARTIAL/FAILED`, không cắt rời lượt user/assistant.
- [x] **P5-02 — Context budget:** cấu hình giới hạn token cho system + history + chunks + query + output reserve; chọn các lượt hoàn chỉnh gần nhất, ghi cách truncate.
- [x] **P5-03 — Query rewriting:** chỉ rewrite câu phụ thuộc context khi cần; giữ original query cho final generation, không thêm facts thiếu căn cứ; đo chi phí/latency phát sinh.
- [x] **P5-04 — RAG integration:** retrieval chỉ tài liệu active/đúng scope; citation truy ngược Qdrant/MongoDB; stream và non-stream dùng chung retrieval/context builder. Unit/full regression, live scoped Atlas/Qdrant smoke và live JSON/SSE transport đã PASS.
- [x] **P5-05 — Evaluation:** test pronoun/follow-up, chuyển chủ đề, long session, out-of-document và cross-document; paired baseline/history-aware live PASS 5/5, retrieval/answer/grounding proxy/fallback/referent/budget đều đạt; ghi latency/token, retry hữu hạn và retrieval-only path xử lý provider quota.
- [x] **P5-06 — Final docs:** README đã đối chiếu runtime và cập nhật luồng history-aware, JSON/SSE/persistent examples, cấu hình, unit/smoke/eval instructions, project structure và giới hạn còn tồn tại; docs validation cùng full regression 152/152 PASS.

**Điều kiện kết thúc:** Multi-turn tests đúng referent; scope/citation đúng; không vượt budget; stream/non-stream nhất quán.

## 9. Workstream M — Migration pgvector → Qdrant Cloud (xuyên suốt)

> Làm `M-01…M-05` trong Giai đoạn 1; chạy lại `M-06` ở các Giai đoạn 3–5. Không gỡ PostgreSQL trước khi cutover được xác minh.

- [x] **M-01 — Kiểm kê phụ thuộc:** tìm pgvector trong db, vectorstore, retriever, pipeline, scripts, tests, eval, compose, requirements, settings; lưu kết quả retrieval baseline.
- [x] **M-02 — Qdrant Cloud connection:** xác minh `.env` có `QDRANT_URL` và `QDRANT_API_KEY` (không in giá trị), cập nhật `.env.example` bằng placeholder, kết nối Qdrant Cloud qua HTTPS/SDK và health check; xử lý timeout/credential/TLS an toàn; kiểm tra collection naming, embedding dimension/distance và payload indexes. **Không thêm Qdrant vào Docker Compose; không tạo cluster mới.**
- [x] **M-03 — Vector adapter:** add/upsert/query/delete/filter với ID hợp lệ, metadata/chunk text; cô lập sau interface để đổi backend.
- [x] **M-04 — Data migration:** re-parse/re-embed raw demo corpus vào Qdrant Cloud; quản lý per-version/status; không nhận đã migrate nếu chưa kiểm chứng.
- [x] **M-05 — Cutover:** so sánh document/chunk counts, retrieval Q&A, delete, page metadata, active-version filter và eval isolation; rồi mới gỡ runtime path/dependencies pgvector, cập nhật compose/config/docs; ghi rollback.
- [x] **M-06 — Regression liên giai đoạn:** live Atlas/Qdrant/embedding verifier PASS selected session scope, whole-turn history, conditional rewrite, JSON/SSE response, citation provenance/persistence và exact cleanup; Groq async provider smoke PASS; focused 42/42, full regression 155/155, compile/dependencies/secret/diff checks PASS. Không phát hiện regression runtime cần sửa.

## 10. Kiểm thử và nghiệm thu tối thiểu (mọi giai đoạn)

- [x] Không lỗi import/startup; `compileall`, FastAPI lifespan và dependency readiness PASS; project không cấu hình lint/type-check riêng.
- [x] Unit tests cho service/adapter và failure modes mới — full regression PASS 155/155.
- [x] Integration/smoke tests với **MongoDB Atlas cloud + Qdrant Cloud** PASS; timeout/auth/network errors dùng contract an toàn, không đưa URI vào log.
- [x] Regression chat/evaluation V1 và history-aware đã PASS qua M-05/P5-05/M-06; lần chạy external-history bổ sung ở M-06 ghi `NOT RUN` do không được cấp quyền gửi payload sang provider.
- [x] Không log/commit secrets hoặc raw file nhạy cảm; secret scan cho files M-06 PASS.
- [x] README, `.env.example`, checklist và `CURRENT_CHANGE.md` phản ánh code thực tế.
- [x] Điều kiện nghiệm thu các phase đạt; hạn chế vận hành còn lại được ghi trong README/CURRENT_CHANGE.

**Lệnh baseline tham khảo, Agent phải kiểm tra trước khi dùng:** không chạy MongoDB/Qdrant bằng Docker; kiểm tra kết nối đến hai dịch vụ cloud bằng script/smoke test an toàn; trong `backend/` chạy `uvicorn app.main:app --reload --port 8000`; từ root chạy `python backend/scripts/eval_cli.py`. Điều chỉnh theo source sau migration; không tự nhận test PASS.

## 11. Mẫu giao việc cho Agent

```text
Đọc PROJECT_LOG_V2.md, CURRENT_CHANGE.md, README.md và source thực tế.
Chỉ làm task đầu tiên chưa hoàn thành trong giai đoạn hiện hành và prerequisite M-series liên quan được giao.
Trước khi sửa: báo cáo baseline, file sẽ đổi và acceptance tests.
Sau khi sửa: chạy test; ghi lệnh/kết quả PASS/FAIL/NOT RUN vào CURRENT_CHANGE.md;
chỉ tích [x] nếu có bằng chứng; cập nhật dashboard, task tiếp theo và blockers trong PROJECT_LOG_V2.md.
Không tự chuyển task/phase. Không commit secrets; giữ API đang hoạt động; cấu hình qua settings.
```

## 12. Quyết định và những vấn đề cần chốt khi triển khai

**Đã chốt:** MongoDB Atlas (cloud, cluster người dùng đã tạo) quản lý application data; IP Access List hiện là `0.0.0.0/0` chỉ nên là tạm thời và cần thu hẹp khi có thể; **Qdrant Cloud (cluster đã tạo; kiểm tra `QDRANT_URL`, `QDRANT_API_KEY` từ `.env`)** thay pgvector; local file storage trong development qua `FileStorage`, key chỉ sinh từ `document_id/version_id` và không cho ghi đè để giữ version immutable, abstraction sẵn sàng đổi S3-compatible sau này; upload P1-05 chạy đồng bộ để giữ API baseline, chỉ activate version sau Qdrant verify và giữ active version cũ khi candidate fail; P1-06 dùng soft-delete/unpublish metadata trước, xóa toàn bộ Qdrant points và verify trong request, giữ raw files cùng version/job history; lỗi Qdrant để `cleanup_pending=true` và DELETE lặp lại sẽ retry idempotent; M-05 đã cutover `/chat` sang Qdrant, scope retrieval lấy `active_version_id` từ MongoDB, eval dùng collection Qdrant riêng; pgvector runtime/dependencies/config/Compose đã gỡ; PostgreSQL container/volume cũ không bị xóa và rollback yêu cầu restore code/config từ Git ref trước M-05 rồi chạy lại V1 eval; P2-01 dùng UUID string làm Mongo `_id`, scope mặc định `ALL_ACTIVE`, message order bằng unique `(session_id, sequence)`, một `request_id` có thể liên kết cặp user/assistant; P2-02 soft-delete session trước rồi hard-delete related messages, giữ tombstone để trả `410`, DELETE lặp lại retry cleanup idempotent; P2-03 giữ `/chat` không có `session_id` stateless, còn request có session ghi user + assistant `PENDING` trước generation và terminal `COMPLETED/FAILED`, sequence cấp atomically theo cặp; P2-04 lưu `active_generation_id` trên session và acquire/release atomically theo owner request, request thứ hai và DELETE khi active trả `409`; P3-01 mở rộng additive `/chat` JSON: mọi top-level field luôn hiện diện, nullable field trả explicit `null`, list trả `[]`, stateless IDs null còn persistent IDs khớp MongoDB; P3-02 đánh số retrieved context phía server và chỉ map ordinal `[n]` trong answer về candidate metadata đủ UUID/page, không tin IDs do model sinh; P3-03 chốt SSE `start→metadata→citation*→delta*→done|error`, sequence liên tục, terminal duy nhất và answer ghép từ delta; external LLM/embedding APIs; Modular Monolith; SSE; 5 giai đoạn + M xuyên suốt.

**P3-04:** Giữ `/chat` tương thích additive, không đổi URL/version; client cũ tiếp tục dùng `answer`/`sources`. Generation failure sau khi đã tạo logical reply trả HTTP 502 với full `ChatResponse`, `status=FAILED` và error an toàn; validation/session/concurrency/persistence error xảy ra trước logical reply tiếp tục dùng HTTP `detail` hiện có.

**P4-01:** `/chat/stream` là POST SSE, giữ `/chat` JSON không đổi và dùng typed transcript P3-03. Client POST body qua `fetch`/`ReadableStream`, không dùng native `EventSource`.

**P4-02:** Stream provider dùng LangChain `ChatOpenAI.astream()` trỏ tới Groq OpenAI-compatible API sau retrieval/prompt; chỉ content text hợp lệ thành delta, usage chuẩn hóa từ metadata và được gửi ở `done` nếu provider có. Không buffer answer chỉ để phát citation vì contract hiện yêu cầu citation trước delta; không phát citation giả. `GROQ_API_KEY` được giữ bằng `SecretStr`, base URL bị giới hạn ở HTTPS `api.groq.com/openai/v1`, và runtime không còn phụ thuộc OpenRouter. Xác minh 2026-10-12 với `openai/gpt-oss-120b`: auth `/models`, model availability và live async stream đều PASS; 14 text delta hợp lệ và usage metadata được nhận.

**P4-03:** Với request có `session_id`, backend chuẩn bị retrieval trước headers rồi atomically tạo user message và assistant `PENDING → STREAMING`, giữ generation guard. Mọi delta được tích lũy; terminal success mới ghi `COMPLETED`, còn provider lỗi/no-content ghi `PARTIAL` hoặc `FAILED` và luôn release guard. Atlas smoke dùng provider deterministic, session UUID riêng và cleanup chính xác. Cancel/disconnect và persistence failure sau headers còn thuộc P4-04.

**P4-04:** Retrieval/session/dependency failure trước headers giữ HTTP 4xx/5xx phù hợp. Sau headers, provider error, output rỗng, timeout hoặc persistence failure chỉ phát một terminal SSE `error` an toàn; không retry sau output. `STREAM_TIMEOUT_SECONDS` đặt deadline tổng cho provider stream. Timeout/cancel đóng async iterator; disconnect ở cả prefix/delta yield cố finalize persistent message với `RAG_STREAM_CANCELLED` và release guard, nhưng không thể gửi terminal event khi client đã ngắt. `Cache-Control: no-cache, no-transform` và `X-Accel-Buffering: no` hạn chế proxy buffering.

**P4-05:** Mỗi request stream dùng monotonic clock đo từ lúc endpoint bắt đầu: `first_event_ms`, nullable `first_content_ms`, `total_latency_ms` và `delta_count`; metric one-shot gắn `request_id`, mode và safe outcome. Logging không chứa question, answer, source hay credentials và lỗi metrics không làm hỏng response. Unit/integration bao phủ mock provider, success reconstruction, output rỗng, lỗi giữa stream, timeout, persistence failure, cancel/disconnect và terminal uniqueness; Atlas smoke đối chiếu reconstructed content với MongoDB history rồi cleanup chính xác.

**P5-01:** `ConversationHistoryLoader` trả session record kèm retrieval scope và các `HistoryTurn` bất khả phân theo thứ tự sequence tăng dần. Cặp hợp lệ phải cùng `request_id`, đúng session, `USER COMPLETED` đứng ngay trước assistant; mặc định assistant chỉ nhận `COMPLETED`, nên `PARTIAL/FAILED/PENDING/STREAMING`, orphan, cross-session hoặc cặp không liên tiếp đều bị loại cả lượt. Diagnostic caller có thể opt-in terminal `PARTIAL/FAILED`; active state không bao giờ là history. Token budget/truncation, query rewriting và nối loader vào RAG thuộc P5-02…P5-04.

**P5-02:** Context window mặc định 8192 token được chia cấu hình thành system 1024, history 2048, chunks 3584, query 512 và output reserve 1024; startup từ chối tổng allocation vượt window. Bộ đếm dùng `langchain-core` approximate counter với hệ số đa ngôn ngữ mặc định 3 chars/token, chưa phải tokenizer chính xác theo model. System instruction không bao giờ bị cắt mà fail an toàn nếu vượt phần cấp; history lấy suffix các whole turns mới nhất và dừng ở turn đầu tiên không vừa; chunks giữ retrieval rank, chỉ prefix-truncate chunk cuối vừa chỗ rồi dừng; query dùng deterministic head–tail marker. Contract này đã được nối vào runtime tại P5-04.

**P5-03:** `QueryDependencyDetector` chỉ mở provider call cho query có dấu hiệu tham chiếu context và có history; query độc lập/no-history giữ nguyên với zero call/token cost. `QueryRewriter` luôn trả riêng `original_query` và `retrieval_query`; provider output phải một dòng, khác original, trong giới hạn và mọi lexical token phải có provenance từ original/selected history hoặc connector an toàn, đồng thời phải thực sự đưa antecedent từ history vào. Entity/số/fact mới, output lỗi, timeout hoặc invalid đều fallback original. Metrics ghi provider-call count, added latency và token cost; ưu tiên usage thật, nếu vắng thì estimate và gắn `usage_source`. Không suy đoán USD cost khi chưa có pricing model/provider cố định. P5-04 đã nối retrieval query và original generation query theo đúng ranh giới này.

**P5-04:** `/chat` và `/chat/stream` dùng chung immutable prepared-request builder. Với session, builder tải whole-turn history và scope server-side từ MongoDB, resolve `ALL_ACTIVE` hoặc `SELECTED_DOCUMENTS` thành snapshot active-version IDs rồi áp Qdrant filter; missing/deleted/inactive document không được retrieve. Chỉ rewritten query đi vào embedding/retrieval, còn prompt cuối luôn chứa original query đã budget cùng recent whole turns và ranked chunk blocks; history chỉ hỗ trợ resolve tham chiếu, không phải nguồn được citation. Budget giữ ordinal/source mapping khi cắt chunk; response source/citation tiếp tục truy ngược exact Qdrant chunk và Mongo active version. JSON/SSE cùng dùng builder này.

**Chốt trước khi thay đổi hành vi liên quan:** upload/index sync hay background job; retention dài hạn/garbage collection cho raw file và audit history sau soft-delete; Qdrant collection/dimension/distance phải xác minh; mapping client cancel/disconnect sang message status; authentication/ACL nếu dùng dữ liệu nội bộ thật/đa người dùng. Ghi quyết định mới ngắn gọn tại đây; diễn biến triển khai để ở `CURRENT_CHANGE.md`.
