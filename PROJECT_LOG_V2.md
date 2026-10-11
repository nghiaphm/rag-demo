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
|---|---|---|
| Backend | Python + FastAPI | API-first; giữ `/chat` JSON baseline hoặc version hóa có hướng chuyển đổi |
| Điều phối RAG | LangChain / LCEL | Ingestion, retrieval, context và generation; chưa cần LangGraph |
| LLM | OpenRouter API | External generation; cấu hình model trong settings |
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
|---|---|---|
| Giai đoạn 1 — Metadata và lưu trữ tài liệu | IN PROGRESS | Upload → lưu → index Qdrant → list/get → delete/re-index đã xác minh |
| Giai đoạn 2 — Session và Message Persistence | PLANNED | Hội thoại lưu bền vững, thứ tự đúng, kiểm soát concurrent generation |
| Giai đoạn 3 — Response Contract | PLANNED | JSON/SSE schema có ví dụ, có tests |
| Giai đoạn 4 — SSE Streaming API | PLANNED | Stream thực sự, xử lý disconnect/lỗi và trạng thái message |
| Giai đoạn 5 — History-aware RAG | PLANNED | Test multi-turn và evaluation retrieval/generation đạt tiêu chí |
| M — Migration pgvector → Qdrant Cloud | IN PROGRESS | Qdrant là retrieval backend sau kiểm thử cutover |

- **Giai đoạn hiện tại:** Giai đoạn 1 (IN PROGRESS; audit baseline đã hoàn thành, chưa triển khai V2)
- **Task vừa hoàn thành:** `P1-01 / M-01` — đã audit repository, dependencies và toàn bộ coupling PostgreSQL/pgvector; không thay đổi source code.
- **Task tiếp theo:** `P1-02 / M-02` — kết nối MongoDB Atlas và Qdrant Cloud (**chưa bắt đầu**).
- **Blockers:** Python trong `.venv` trỏ tới interpreter không còn tồn tại; Docker daemon không chạy; `.env` chưa có cấu hình MongoDB. Qdrant credentials hiện diện nhưng chưa được settings/source sử dụng và chưa kiểm tra kết nối cloud.
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
- [ ] **P1-02 — Kết nối MongoDB Atlas:** kiểm tra dependency/driver phù hợp và cấu hình `MONGODB_URI`, `MONGODB_DB_NAME` qua settings/`.env.example` (chỉ placeholder); tạo client lifecycle khi FastAPI startup/shutdown, ping/readiness có timeout và báo lỗi an toàn; xây repository/adapter; xác minh quyền DB tối thiểu, TLS/URI `mongodb+srv://` nếu cluster cung cấp, không log URI/secret; **không thêm MongoDB vào Docker Compose, không tạo cluster mới và không tự thay đổi IP Access List**.
- [ ] **P1-03 — Document models/indexes trên MongoDB Atlas:** `documents`, `document_versions`, `ingestion_jobs`; ID độc lập filename, checksum, unique/indexes, status và active version.
- [ ] **P1-04 — File storage abstraction:** local adapter (save/read/exists/delete); opaque versioned storage key, validation, download/read có kiểm soát; không xây S3 adapter bây giờ.
- [ ] **P1-05 — Ingestion tích hợp:** upload raw file → metadata `UPLOADED/PROCESSING` → parse/chunk/embed → upsert Qdrant → verify → `INDEXED` hoặc `FAILED`; xử lý retry/reconciliation, không phá active version khi fail.
- [ ] **P1-06 — Document APIs:** upload/list/get/delete/update/re-index và response rõ ràng; delete/unpublish loại ngay khỏi retrieval, cleanup theo chính sách đã chốt; ghi nhận giữ hay xóa file.
- [ ] **P1-07 — Verification:** kiểm tra upload, file gốc, metadata/page, số chunk, Qdrant retrieval, version switching, failed re-index, delete không còn retrieve, regression/eval; cập nhật README.

**Điều kiện kết thúc:** Luồng document end-to-end có test; lỗi re-index không làm mất active version; document bị xóa không còn được tìm thấy; Qdrant hoạt động thay pgvector.

## 5. Giai đoạn 2 — Session & Message Persistence

**Mục tiêu:** lưu session/messages bền vững trong MongoDB, trước tiên tích hợp với non-streaming hiện có.

- [ ] **P2-01 — Models/indexes:** `sessions` (ID, title, scope, timestamps, optional user) và `messages` (session, role, content, status, citations, model, usage, timestamps, request ID); index thứ tự ổn định.
- [ ] **P2-02 — Session APIs:** create/list/get/update title/delete; phân trang history, xử lý ID sai/session đã xóa, quy tắc xóa message liên quan.
- [ ] **P2-03 — Message persistence:** lưu user message trước generation, lưu assistant success/failure. Chốt `/chat` không session giữ stateless hay tự tạo session; đảm bảo backward compatibility.
- [ ] **P2-04 — Concurrency:** một active generation/session bằng atomic guard, giải phóng khi hoàn tất/lỗi/hủy; test hai request đồng thời.
- [ ] **P2-05 — Verification:** restart backend vẫn tải session/history; thứ tự, pagination, invalid/deleted session, failed generation; cập nhật README.

**Điều kiện kết thúc:** Session/messages khôi phục được sau restart; thứ tự đúng; concurrent same-session request tuân thủ chính sách đã ghi.

## 6. Giai đoạn 3 — Response Contract

**Mục tiêu:** một schema logical reply, độc lập transport/provider.

- [ ] **P3-01 — JSON schema:** `request_id`, `session_id`, `user_message_id`, `assistant_message_id`, `answer`, `sources/citations`, `metadata`, `usage`, `status`, `error`; quy định optional/null.
- [ ] **P3-02 — Citation mapping:** chỉ map `chunk_id`, `document_id`, `version_id`, page từ tài liệu thực và đủ điều kiện; không tin citation ID do LLM tự tạo; phân biệt retrieved candidates và cited sources.
- [ ] **P3-03 — SSE schema:** định nghĩa `start`, `metadata`, `citation`, `delta`, `done`, `error`, thứ tự event, terminal rules, cách ghép nội dung và ID của assistant message.
- [ ] **P3-04 — Compatibility/tests:** Pydantic validation, lỗi/usage không có, fallback no-results, nhiều documents; giữ client `/chat` cũ hoặc có version/migration rõ ràng.

**Điều kiện kết thúc:** Có ví dụ JSON/SSE transcript và test schema/citation; không lộ raw provider response/secrets.

## 7. Giai đoạn 4 — SSE Streaming API

**Mục tiêu:** stream delta từ LLM qua SSE và ghi lifecycle assistant message vào MongoDB.

- [ ] **P4-01 — Endpoint:** thêm `POST /chat/stream` (ví dụ); giữ `/chat` JSON; hướng dẫn fetch-stream vì native EventSource không gửi POST body trực tiếp.
- [ ] **P4-02 — Provider integration:** consume LangChain/OpenRouter async stream, chuẩn hóa text delta; bỏ qua chunk không có text hợp lệ, ghi usage nếu có.
- [ ] **P4-03 — Lifecycle:** tạo assistant message trước streaming, tích lũy content để persist, phát event theo thứ tự, chỉ ghi `COMPLETED` khi thành công; `PARTIAL/FAILED` đúng thực tế.
- [ ] **P4-04 — Error/disconnect:** trước headers trả HTTP error phù hợp; sau headers gửi terminal SSE `error`; dừng downstream nếu có thể, tránh output lặp do retry; kiểm tra buffering/timeout.
- [ ] **P4-05 — Metrics/tests:** first-event, first-content, total latency; mock provider, output rỗng, lỗi giữa stream, disconnect/cancel, persistence và client reconstruction.

**Điều kiện kết thúc:** Client nhận nội dung tăng dần; stream kết thúc một lần; trạng thái/content MongoDB khớp kết quả; error/cancel tests đạt.

## 8. Giai đoạn 5 — History-aware RAG

**Mục tiêu:** hỏi đáp nhiều lượt, chọn history có giới hạn, cải thiện follow-up retrieval.

- [ ] **P5-01 — History loader:** lấy message đúng session/scope/thứ tự; mặc định loại assistant `PARTIAL/FAILED`, không cắt rời lượt user/assistant.
- [ ] **P5-02 — Context budget:** cấu hình giới hạn token cho system + history + chunks + query + output reserve; chọn các lượt hoàn chỉnh gần nhất, ghi cách truncate.
- [ ] **P5-03 — Query rewriting:** chỉ rewrite câu phụ thuộc context khi cần; giữ original query cho final generation, không thêm facts thiếu căn cứ; đo chi phí/latency phát sinh.
- [ ] **P5-04 — RAG integration:** retrieval chỉ tài liệu active/đúng scope; citation truy ngược Qdrant/MongoDB; stream và non-stream dùng chung retrieval/context builder.
- [ ] **P5-05 — Evaluation:** test pronoun/follow-up, chuyển chủ đề, long session, out-of-document và cross-document; so sánh với baseline, ghi retrieval, grounding proxy, latency/token; xử lý provider quota.
- [ ] **P5-06 — Final docs:** cập nhật README, kiến trúc, API example, test instructions và giới hạn còn tồn tại.

**Điều kiện kết thúc:** Multi-turn tests đúng referent; scope/citation đúng; không vượt budget; stream/non-stream nhất quán.

## 9. Workstream M — Migration pgvector → Qdrant Cloud (xuyên suốt)

> Làm `M-01…M-05` trong Giai đoạn 1; chạy lại `M-06` ở các Giai đoạn 3–5. Không gỡ PostgreSQL trước khi cutover được xác minh.

- [x] **M-01 — Kiểm kê phụ thuộc:** tìm pgvector trong db, vectorstore, retriever, pipeline, scripts, tests, eval, compose, requirements, settings; lưu kết quả retrieval baseline.
- [ ] **M-02 — Qdrant Cloud connection:** xác minh `.env` có `QDRANT_URL` và `QDRANT_API_KEY` (không in giá trị), cập nhật `.env.example` bằng placeholder, kết nối Qdrant Cloud qua HTTPS/SDK và health check; xử lý timeout/credential/TLS an toàn; kiểm tra collection naming, embedding dimension/distance và payload indexes. **Không thêm Qdrant vào Docker Compose; không tạo cluster mới.**
- [ ] **M-03 — Vector adapter:** add/upsert/query/delete/filter với ID hợp lệ, metadata/chunk text; cô lập sau interface để đổi backend.
- [ ] **M-04 — Data migration:** re-parse/re-embed raw demo corpus vào Qdrant Cloud; quản lý per-version/status; không nhận đã migrate nếu chưa kiểm chứng.
- [ ] **M-05 — Cutover:** so sánh document/chunk counts, retrieval Q&A, delete, page metadata, active-version filter và eval isolation; rồi mới gỡ runtime path/dependencies pgvector, cập nhật compose/config/docs; ghi rollback.
- [ ] **M-06 — Regression liên giai đoạn:** xác minh citation/scope với session, response, stream và history-aware; ghi và sửa regression.

## 10. Kiểm thử và nghiệm thu tối thiểu (mọi giai đoạn)

- [ ] Không lỗi import/startup; chạy lint/type-check nếu project có.
- [ ] Unit tests cho service/adapter và failure modes mới.
- [ ] Integration/smoke tests với **MongoDB Atlas cloud + Qdrant Cloud** khi môi trường sẵn sàng; phân biệt lỗi DNS, allowlist, credential, TLS, timeout; không đưa URI vào log.
- [ ] Kiểm tra regression chat/evaluation V1, hoặc ghi rõ BLOCKED/NOT RUN.
- [ ] Không log/commit secrets (đặc biệt MongoDB Atlas connection string, `QDRANT_URL` thực và `QDRANT_API_KEY`) hoặc raw file nhạy cảm.
- [ ] README, `.env.example`, checklist và `CURRENT_CHANGE.md` phản ánh code thực tế.
- [ ] Điều kiện nghiệm thu phase đạt; các hạn chế/lỗi tồn đọng được ghi.

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

**Đã chốt:** MongoDB Atlas (cloud, cluster người dùng đã tạo) quản lý application data; IP Access List hiện là `0.0.0.0/0` chỉ nên là tạm thời và cần thu hẹp khi có thể; **Qdrant Cloud (cluster đã tạo; kiểm tra `QDRANT_URL`, `QDRANT_API_KEY` từ `.env`)** thay pgvector; local file storage trong development, abstraction sẵn sàng đổi S3-compatible sau này; external LLM/embedding APIs; Modular Monolith; SSE; 5 giai đoạn + M xuyên suốt.

**Chốt trước khi thay đổi hành vi liên quan:** `/chat` stateless hay tự tạo session; upload/index sync hay background job; chính sách giữ/xóa file, soft/hard delete và citation cũ; Qdrant collection/dimension/distance phải xác minh; mapping client cancel/disconnect sang message status; authentication/ACL nếu dùng dữ liệu nội bộ thật/đa người dùng. Ghi quyết định mới ngắn gọn tại đây; diễn biến triển khai để ở `CURRENT_CHANGE.md`.
