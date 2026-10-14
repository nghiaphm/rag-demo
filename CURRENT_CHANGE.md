# CURRENT_CHANGE — Nhật ký thực thi RAG V2

> **Vai trò:** Ghi ngắn gọn những gì Agent **thực sự đã làm** sau mỗi task, kèm file thay đổi, kiểm thử và công việc kế tiếp. Kế hoạch/checklist chính nằm tại [`PROJECT_LOG_V2.md`](./PROJECT_LOG_V2.md). Không tự nhận hoàn thành từ nội dung kế hoạch.

## 1. Trạng thái gần nhất

- **Giai đoạn:** Frontend F0/F1/F2/F3/F4/F5/F6 COMPLETED; backend roadmap giữ nguyên.
- **Task vừa hoàn thành:** `[FRONTEND/F6-03]` — Versions/reindex/delete, 2026-10-14.
- **Task tiếp theo:** `F7-01` — NOT STARTED; chờ giao việc riêng.
- **Blocker:** Không blocker implementation; browser/live mutation smoke chưa chạy. API chưa atomic revision/If-Match; raw files giữ theo soft-delete contract.
- **Lần cập nhật:** Full regression 139/139 (13 document-action tests), 45-schema contract, build/typecheck/lint/diff PASS; chi tiết FRONTEND_PLAN mục 26. Groq/Gemini live calls = 0.

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

### [2026-10-14] [FRONTEND/F6-03] — Versions/reindex/delete

- **Trạng thái:** COMPLETED; F6 COMPLETED, F7-01 chưa bắt đầu.
- **Đã thực hiện:** PUT multipart new-version/POST re-index/DELETE clients đúng routes/status/ownership, giữ 200/202 cleanup và raw-retention DTO. Detail toolbar/dialog explicit confirmations với shared controller, duplicate guard và preflight stale snapshot checks. Post-action/error GET reconciliation không optimistic-promote active, failed version giữ old active, selected/list stale responses không apply. DELETE202 pending cho confirmation mới retry cleanup idempotent; UI nói giữ raw/history, không fake hard-delete. Refresh failure/uncertain outcomes/abort không tự retry mutation. Không backend/dependency/live changes.
- **Files thay đổi:** `frontend/lib/api/documents.ts`, `frontend/lib/documents/{actions-controller,controller}.ts`, `frontend/components/documents/{document-actions,documents-preview}.tsx`, `frontend/tests/document-actions.test.mjs`, `FRONTEND_PLAN.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`; giữ thay đổi sẵn có.
- **Kiểm thử:** Full frontend regression PASS 139/139 gồm 13 protected-action/stale-state/API/SSR tests; build/typecheck/lint (0 warnings)/contract 45 schemas/diff/new-file whitespace PASS. Browser DOM confirmations/focus/mobile/live version/reindex/delete/provider smoke NOT RUN; chưa có quyền live mutation/provider. Groq=0, Gemini=0, không tạo/xóa live artifacts.
- **Tồn đọng / blocker:** Không blocker implementation. Preflight GET không atomic do API chưa If-Match; backend vẫn quyết định conflict/activation. Action error sau gửi có thể đã thay đổi persisted state; reconcile GET, không retry tự động. Soft-delete không xóa raw files; cleanup pending cần người dùng xác nhận DELETE lại. Browser/live QA vẫn cần chạy khi có quyền/công cụ phù hợp.
- **Tiếp theo:** `F7-01` NOT STARTED; dừng, không tự động triển khai.

### [2026-10-14] [FRONTEND/F6-02] — Upload/progress

- **Trạng thái:** COMPLETED; F6 IN PROGRESS, F6-03 chưa bắt đầu.
- **Đã thực hiện:** Create upload dialog POST `/documents/upload`, FormData field `file`/browser boundary và runtime HTTP201/index DTO guards. File extension/basename/nonempty size khớp backend, không đặt max bytes/MIME policy giả. Controller khóa duplicate submit, status receipt/activated tách biệt, pending không giả percent/UPLOADED/PROCESSING. Error không giả persisted FAILED, uncertain timeout/network/5xx/malformed response hướng refresh trước reselect/repost, không automatic retry. Client wait 5 phút; Dừng chờ/unmount abort không hứa backend rollback, late success bị bỏ qua. Valid receipt refresh list GET. Version/delete/reindex còn placeholders; không backend/dependency changes.
- **Files thay đổi:** `frontend/lib/api/documents.ts`, `frontend/lib/documents/{upload-validation,upload-controller}.ts`, `frontend/components/documents/{document-upload,documents-preview}.tsx`, `frontend/tests/document-upload.test.mjs`, `FRONTEND_PLAN.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`; giữ thay đổi sẵn có.
- **Kiểm thử:** Full regression PASS 126/126 gồm 13 upload multipart/validation/state/success/failure/abort/SSR tests và offline FastAPI filename/extension parity, network blocked. Build/typecheck/lint (0 warnings)/contract 45 schemas/diff/new-file whitespace PASS. Browser upload interaction/live file embedding/index/storage smoke NOT RUN — chưa có quyền live provider/mutation. Groq=0, Gemini=0, không tạo live artifact.
- **Tồn đọng / blocker:** Không blocker implementation. Backend chưa max-size/progress/polling; synchronous current runtime trả INDEXED hoặc HTTP error không có document IDs. Timeout/abort có thể vẫn ingest ở server, frontend không tự retry; cần kiểm tra list/cleanup backend thật trong live test khi được phép.
- **Tiếp theo:** `F6-03` NOT STARTED; dừng, không tự động triển khai.

### [2026-10-14] [FRONTEND/F6-01] — List/detail/status

- **Trạng thái:** COMPLETED; F6 IN PROGRESS, F6-02/F6-03 chưa bắt đầu.
- **Đã thực hiện:** Runtime-validated GET document list/detail clients, external-store controller/hook và Documents UI từ backend thay fixtures. Pagination 20/page, include_deleted filter đúng route, Tải thêm dựa raw page length, không giả total/status query. Loading/empty/error/retry riêng list/detail, 404 missing, config fail-closed, abort/stale guards khi filter/select/refresh/unmount. Status và active version riêng, giữ old active khi PROCESSING/FAILED, version badges, DELETED/cleanup notice. Mutation dialogs còn placeholders/disabled, không provider/backend/dependency changes.
- **Files thay đổi:** `frontend/lib/api/documents.ts`, `frontend/lib/documents/controller.ts`, `frontend/hooks/use-documents.ts`, `frontend/components/documents/documents-preview.tsx`, `frontend/app/documents/page.tsx`, `frontend/tests/documents.test.mjs`, `FRONTEND_PLAN.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`; giữ thay đổi sẵn có.
- **Kiểm thử:** Documents mock/client/controller/SSR PASS 12/12; full frontend regression PASS 113/113; build/typecheck/lint (0 warnings)/contract 45 schemas/diff/new-file whitespace PASS. Browser/live document GET/CORS/cloud smoke NOT RUN. Groq=0, Gemini=0; GET-only mock API, không mutation.
- **Tồn đọng / blocker:** Không blocker implementation. API trả array không total, nên full last page cần thêm empty probe; không server status filter/snapshot/cursor, concurrent updates có thể gây overlap (báo lỗi, không tự retry). API runtime cần public base/CORS; chưa browser smoke. Upload/progress và lifecycle actions thuộc F6-02/F6-03.
- **Tiếp theo:** `F6-02` NOT STARTED; dừng, không tự động triển khai.

### [2026-10-14] [FRONTEND/F5-02] — Citation UI

- **Trạng thái:** COMPLETED; F5 COMPLETED, F6-01 chưa bắt đầu.
- **Đã thực hiện:** Assistant Markdown dùng text-node Rehype citation plugin và message-local labelled SheetTriggers. Click callback resolve đúng metadata/source identity; code/link giữ marker nguyên văn, streaming marker chưa hoàn chỉnh giữ text. Drawer shadcn có close/title/description, responsive width/scroll, nhóm document/version/file/page và ưu tiên/highlight selected source. Kết hợp persisted citations để history vẫn có nguồn đã lưu; ordinal thiếu metadata giữ unavailable/fallback, không đoán từ citations order. Không giả URL/download/preview, backend change hoặc dependency mới.
- **Files thay đổi:** `frontend/components/chat/{chat-message,citation-content}.tsx`, `frontend/lib/chat/{citation-panel,citation-markdown}.ts`, `frontend/tests/citation-ui.test.mjs`, `FRONTEND_PLAN.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`; giữ F5-01 và thay đổi sẵn có.
- **Kiểm thử:** Full regression PASS 101/101 gồm 10 citation UI callback/ReactMarkdown/SSR/history/integration/streaming tests; build/typecheck/lint (0 warnings)/contract 45 schemas/diff/new-file whitespace PASS. Browser skill được áp dụng, bootstrap FAIL trước browser session nên DOM click/Escape/focus/mobile QA BLOCKED/NOT RUN; không đánh dấu PASS. Live provider smoke NOT RUN; Groq=0, Gemini=0.
- **Tồn đọng / blocker:** Không blocker implementation. Cần rerun browser click/keyboard/focus/viewport khi công cụ hoạt động. REST history hiện không expose sources order nên inline ordinal không thể resolve sau refresh; persisted citation list vẫn hiển thị đúng IDs/file/page, không dùng localStorage làm nguồn dữ liệu.
- **Tiếp theo:** `F6-01` NOT STARTED; dừng, không tự động triển khai.

### [2026-10-14] [FRONTEND/F5-01] — Source mapper

- **Trạng thái:** COMPLETED; F5 IN PROGRESS, F5-02 chưa bắt đầu.
- **Đã thực hiện:** Pure mapper resolve `[n]` theo sources[n-1] của đúng assistant, giữ owner key/message ID, marker offsets, resolved/unavailable reason và source IDs/file/page. Sparse ordinals không bị renumber; repeated occurrences giữ riêng nhưng citations deduplicate chunk ID theo first mention như backend. Xác minh PDF loader page 0-based, giữ raw page và cộng 1 chỉ cho PDF display; loader khác không suy đoán. Không tạo URL từ source path/model text hoặc đoán ordinal từ history citations; không UI/backend/dependency mới.
- **Files thay đổi:** `frontend/lib/chat/source-mapper.ts`, `frontend/tests/source-mapper.test.mjs`, `FRONTEND_PLAN.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`; giữ mọi thay đổi sẵn có.
- **Kiểm thử:** targeted mapper PASS 11/11 gồm offline backend ordinal parity và real PDF loader 2 trang [0,1], network blocked; full frontend regression PASS 91/91; contract verifier PASS 45 schemas; build/typecheck/lint (0 warnings)/diff/new-file whitespace PASS. Browser citation UI/live smoke NOT RUN; Groq=0, Gemini=0.
- **Tồn đọng / blocker:** Không blocker implementation. History thiếu sources/ordinal mapping, mapper trả missing_metadata. PDF page_label không expose; Markdown AST/click/source drawer/fallback UI thuộc F5-02.
- **Tiếp theo:** `F5-02` NOT STARTED; dừng, không tự động triển khai.

### [2026-10-14] [FRONTEND/F4-03] — Multi-turn integration

- **Trạng thái:** COMPLETED; F4 COMPLETED, F5-01 chưa bắt đầu.
- **Đã thực hiện:** Key workspace/session boundary, capture active turn cho SSE callbacks và bỏ late/aborted/terminal events; unmount abort stream/history read và chặn stale URL replace. Reuse backend session ID, reject reused request/message IDs. Sau terminal đọc paginated persisted history, đối chiếu IDs/request/role/content/status/model/usage/error; success reconcile backend citations và giữ live sources theo message ID. Lỗi xác minh giữ streamed terminal/content, báo safe warning/link history, unlock composer, không retry request. Tách trạng thái verification khỏi Stop. Dùng chung history loader; không sửa backend/thêm dependency.
- **Files thay đổi:** `frontend/lib/chat/controller.ts`, `frontend/lib/sessions/history.ts`, `frontend/components/chat/{chat-preview,session-chat}.tsx`, `frontend/tests/multi-turn.test.mjs`, `FRONTEND_PLAN.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`; giữ các thay đổi F4-01/F4-02 sẵn có.
- **Kiểm thử:** `node --test tests/*.test.mjs` PASS 80/80 gồm 9 multi-turn tests; 3-turn production-controller/REST/SSE/parser/HTTP mock E2E có refresh/pagination/distinct IDs, switching/late callbacks và persistence guards. Contract verifier PASS 45 schemas; build/typecheck/lint/diff/new-file whitespace PASS. Browser DOM E2E/live backend persistence/provider smoke NOT RUN; chưa có quyền live provider. Groq=0, Gemini=0.
- **Tồn đọng / blocker:** Không blocker implementation. Mock persisted messages không xác minh MongoDB thật. Offset pagination không có snapshot, session dài cần đọc nhiều pages sau terminal; history thiếu sources/ordinal mapping. Cancel/disconnect chưa terminal chờ mở lại để đọc persisted cleanup; không suy diễn thành công.
- **Tiếp theo:** `F5-01` NOT STARTED; dừng, không tự động triển khai.

### [2026-10-14] [FRONTEND/F4-02] — History/pagination

- **Trạng thái:** COMPLETED; F4 IN PROGRESS, F4-03 chưa bắt đầu.
- **Đã thực hiện:** Thêm runtime-validated message page client và history controller tự tải đủ offset/limit pages, reject mixed-session/discontinuous/duplicate/incomplete data rồi stable-sort `(sequence, message_id)`. Dynamic session route chỉ dựng Chat UI sau session lookup và full history load; retry/refresh thay state từ backend, không dùng localStorage. Chat controller nhận initial messages; lượt đầu từ `/chat` thay URL bằng backend session ID sau terminal để route canonical tải history. Mapping giữ content/status/citations/model/usage/IDs nhưng không tự dựng `sources` vì history contract không có field này. Không F4-03/backend/dependency mới.
- **Files thay đổi:** `frontend/lib/api/sessions.ts`, `frontend/lib/sessions/history.ts`, `frontend/hooks/use-sessions.ts`, `frontend/lib/chat/controller.ts`, `frontend/components/chat/{chat-preview,session-chat,chat-message}.tsx`, `frontend/tests/sessions.test.mjs`, `FRONTEND_PLAN.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`; giữ các thay đổi F4-01 sẵn có.
- **Kiểm thử:** targeted session/history mock API PASS 13/13; combined API/parser/stream/chat/session PASS 71/71; contract verifier PASS 45 schemas; build/typecheck/lint/diff/new-file whitespace PASS. Live browser refresh/navigation/CORS/backend/provider smoke NOT RUN; Groq=0, Gemini=0.
- **Tồn đọng / blocker:** Không blocker implementation. Browser runtime cần `NEXT_PUBLIC_API_BASE_URL` và backend CORS phù hợp. History REST không trả sources nên refresh chưa thể dựng source metadata/citation ordinal; multi-turn switching/leak validation thuộc F4-03.
- **Tiếp theo:** `F4-03` NOT STARTED; dừng, không tự động triển khai.

### [2026-10-14] [FRONTEND/F4-01] — Session list/New Chat

- **Trạng thái:** COMPLETED; F4 IN PROGRESS, F4-02/F4-03 chưa bắt đầu.
- **Đã thực hiện:** Thêm typed/runtime-validated REST list/create/get session clients, external-store hooks/controllers có abort cleanup và safe states. Sidebar tải first page 50 phiên, có New Chat POST một lần rồi route bằng backend ID và link mở session, không nhập/tự sinh UUID. Dynamic route validate ID cục bộ, GET session và hiển thị riêng invalid, 404/410, API error/retry, missing config trước Chat UI. Không history/localStorage/title/delete/scope mutation, backend change hoặc dependency mới.
- **Files thay đổi:** `frontend/lib/api/sessions.ts`, `frontend/lib/sessions/controller.ts`, `frontend/hooks/use-sessions.ts`, `frontend/components/layout/{app-shell,session-navigation}.tsx`, `frontend/components/chat/session-chat.tsx`, `frontend/app/{layout,chat/[sessionId]/page}.tsx`, `frontend/tests/sessions.test.mjs`, `FRONTEND_PLAN.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`.
- **Kiểm thử:** targeted session mock API PASS 7/7; combined API/parser/stream/chat/session PASS 65/65; contract verifier PASS 45 schemas; build/typecheck/lint/diff/new-file whitespace PASS. Live browser session/CORS/backend/provider smoke NOT RUN; Groq=0, Gemini=0.
- **Tồn đọng / blocker:** Không blocker implementation. Browser runtime cần `NEXT_PUBLIC_API_BASE_URL` và backend CORS phù hợp. Chỉ first page hiển thị; history/pagination/session refresh thuộc F4-02, multi-turn switching thuộc F4-03.
- **Tiếp theo:** `F4-02` NOT STARTED; dừng, không tự động triển khai.

### [2026-10-14] [FRONTEND/F3-03] — Cancel/recovery

- **Trạng thái:** COMPLETED; F3 COMPLETED, F4-01 chưa bắt đầu.
- **Đã thực hiện:** Thêm một AbortController cho mỗi accepted turn, truyền signal qua create session và stream. Stop control và unmount/navigation cleanup abort idempotent; không abort terminal turn và không retry request. Cancel giữ exact partial content, gán `PARTIAL|FAILED` cùng safe `RAG_STREAM_CANCELLED` đúng backend disconnect semantics; transport failure dùng `CLIENT_STREAM_ERROR`. `finally` luôn unlock generation. Composer hiển thị Stop button accessible khi đang stream. Không sửa backend/dependency hoặc thêm timeout policy.
- **Files thay đổi:** `frontend/lib/chat/controller.ts`, `frontend/components/chat/{chat-composer,chat-preview}.tsx`, `frontend/tests/chat-controller.test.mjs`, `FRONTEND_PLAN.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`; giữ các thay đổi F3-01/F3-02 sẵn có.
- **Kiểm thử:** targeted cancel/recovery/state fixtures PASS 8/8; combined API/parser/stream/state PASS 58/58; contract verifier PASS 45 schemas; build/typecheck/lint/diff/new-file whitespace PASS. Live browser SSE/cancel/CORS/backend/provider smoke NOT RUN; Groq=0, Gemini=0.
- **Tồn đọng / blocker:** Không blocker implementation. Browser runtime cần `NEXT_PUBLIC_API_BASE_URL` và backend CORS phù hợp. Live cancel/persistence reconciliation và history refresh chưa chạy; session/history UI thuộc F4.
- **Tiếp theo:** `F4-01` NOT STARTED; dừng, không tự động triển khai.

### [2026-10-13] [FRONTEND/F3-02] — Chat state/UI integration

- **Trạng thái:** COMPLETED; F3 IN PROGRESS, F3-03 chưa bắt đầu.
- **Đã thực hiện:** Thay Chat fixture preview bằng controlled composer và `ChatController` immutable snapshots. `/chat` tạo persistent session qua POST `/sessions` body `{}` trước stream; route có ID tái dùng ID đó. Controller khóa duplicate submit trước await, map start IDs/metadata/citation/usage, exact-append delta content và cập nhật COMPLETED/PARTIAL/FAILED. Session response được runtime-check HTTP 201; UI hiển thị draft/status/safe error và fail-closed khi thiếu `NEXT_PUBLIC_API_BASE_URL`. Không history, retry/cancel/timeout, backend change hoặc dependency mới.
- **Files thay đổi:** `frontend/lib/api/sessions.ts`, `frontend/lib/chat/controller.ts`, `frontend/components/chat/{chat-composer,chat-message,chat-preview}.tsx`, `frontend/app/chat/{page,[sessionId]/page}.tsx`, `frontend/tests/chat-controller.test.mjs`, `FRONTEND_PLAN.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`; giữ các thay đổi F3-01 sẵn có.
- **Kiểm thử:** targeted state/session fixtures PASS 4/4; combined API/parser/stream/state PASS 54/54; contract verifier PASS 45 schemas; build/typecheck/lint/diff/new-file whitespace PASS. Live browser SSE/CORS/backend/provider smoke NOT RUN; Groq=0, Gemini=0.
- **Tồn đọng / blocker:** Không blocker implementation. Browser runtime cần `NEXT_PUBLIC_API_BASE_URL` và backend CORS phù hợp. URL chưa đổi sau create và history chưa load thuộc F4; AbortController/unmount/navigation/recovery/timeout UX thuộc F3-03.
- **Tiếp theo:** `F3-03` NOT STARTED; dừng, không tự động triển khai.

### [2026-10-13] [FRONTEND/F3-01] — Stream client

- **Trạng thái:** COMPLETED; F3 IN PROGRESS, F3-02/F3-03 chưa bắt đầu.
- **Đã thực hiện:** Triển khai `createChatStreamClient` POST `/chat/stream`, đọc ReadableStream và tái dùng parser F1-03. Validator incremental giữ typed events/sequence/start IDs/metadata/citations/deltas/terminal/usage, exact-concatenate delta content và áp toàn bộ backend transcript order/provenance/terminal rules. `onEvent` nhận logical events độc lập network chunks. Safe error model tách before-response HTTP/network/pre-abort khỏi post-200 response/transport/abort/protocol/incomplete/consumer; valid SSE error là terminal result. Không retry, UI integration, timeout policy, backend change hoặc dependency mới.
- **Files thay đổi:** `frontend/lib/api/chat.ts`, `frontend/tests/chat-stream-client.test.mjs`, `FRONTEND_PLAN.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md` (archive entry cũ nguyên vẹn để giữ 15 entry); giữ các thay đổi sẵn có.
- **Kiểm thử:** targeted mock stream PASS 12/12; combined API/parser/stream PASS 50/50; contract verifier PASS 45 schemas; build/typecheck/lint/diff/new-file whitespace PASS. Live backend/browser/UI/provider smoke NOT RUN; mock fetch/ReadableStream only, Groq=0, Gemini=0.
- **Tồn đọng / blocker:** Không blocker F3-01. API base URL/CORS browser còn chưa cấu hình. F3-02 mới nối stream events vào Chat state/UI; F3-03 mới quản lý AbortController Stop/unmount/navigation/recovery và timeout UX.
- **Tiếp theo:** `F3-02` NOT STARTED; dừng, không tự động triển khai.

### [2026-10-13] [FRONTEND/F2-03] — Documents static components

- **Trạng thái:** COMPLETED; F2 COMPLETED, F3-01 chưa bắt đầu.
- **Đã thực hiện:** Thêm document fixtures typed theo `DocumentDetail` và responsive list/detail preview. Hiển thị status, active version, chunks/version count, immutable version history và state notices. Thêm upload/new-version dialogs đúng extensions/ingestion-sync contract, delete confirmation đúng soft-delete/cleanup/raw-retention semantics; file không được đọc/gửi, upload/re-index/delete CTA đều disabled. Local list selection là UI-only; không fetch/API call/backend mutation, progress/poll/download giả hoặc dependency mới.
- **Files thay đổi:** `frontend/fixtures/documents.ts`, `frontend/components/documents/{document-status-badge,document-dialogs,documents-preview}.tsx`, `frontend/app/documents/page.tsx`, `FRONTEND_PLAN.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-01.md` (archive entry cũ nguyên vẹn để giữ 15 entry); giữ các thay đổi sẵn có.
- **Kiểm thử:** build/typecheck/lint PASS, 0 warnings; API/SSE regression PASS 38/38; contract verifier PASS 45 schemas; dev HTTP `/documents` PASS 200 với list/selection/detail/status/active-version/history và action triggers trong HTML; `git diff --check`/new-file whitespace PASS. Browser click/dialog/viewport interaction BLOCKED/NOT RUN vì Node REPL của Browser plugin lỗi path; không đánh dấu PASS. Groq=0, Gemini=0.
- **Tồn đọng / blocker:** Không blocker implementation. Cần rerun list selection, dialog keyboard/focus và responsive visual QA khi Browser plugin hoạt động. Domain document API client vẫn chưa triển khai; live mutation thuộc F6.
- **Tiếp theo:** `F3-01` NOT STARTED; dừng, không tự động triển khai.

### [2026-10-13] [FRONTEND/F2-02] — Chat static components

- **Trạng thái:** COMPLETED; F2 IN PROGRESS, F2-03 chưa bắt đầu.
- **Đã thực hiện:** Thêm fixture-only Chat preview dùng chung cho `/chat` và `/chat/[sessionId]`: user/assistant bubbles, avatar, Markdown/GFM renderer, composer không submit, cùng conversation/empty/loading/error states chuyển bằng accessible button group. Loading có aria-busy/Skeleton, error có role=alert; control giả gửi/thử lại disabled và UI ghi rõ chưa kết nối API. Fixture type tách khỏi API DTO. Không fetch/API/SSE hook, backend change hoặc dependency mới.
- **Files thay đổi:** `frontend/fixtures/chat.ts`, `frontend/components/chat/{chat-message,chat-composer,chat-preview}.tsx`, `frontend/app/chat/page.tsx`, `frontend/app/chat/[sessionId]/page.tsx`, `FRONTEND_PLAN.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-01.md` (archive entry cũ nguyên vẹn để giữ 15 entry); giữ các thay đổi sẵn có.
- **Kiểm thử:** build/typecheck/lint PASS; API/SSE regression PASS 38/38; contract verifier PASS 45 schemas; dev HTTP `/chat` và `/chat/demo-session` PASS 200 với bubble labels, Markdown list, composer disabled và state controls trong HTML; `git diff --check`/new-file whitespace PASS. Browser click/viewport interaction BLOCKED/NOT RUN vì Node REPL của Browser plugin lỗi path; không đánh dấu PASS. Groq=0, Gemini=0.
- **Tồn đọng / blocker:** Không blocker implementation. Cần rerun visual/state-switch/keyboard QA khi Browser plugin hoạt động. Composer và retry cố ý không thực thi; stream/state integration thuộc F3.
- **Tiếp theo:** `F2-03` NOT STARTED; dừng, không tự động triển khai.

### [2026-10-13] [FRONTEND/F2-01] — Application shell

- **Trạng thái:** COMPLETED; F2 IN PROGRESS, F2-02/F2-03 chưa bắt đầu.
- **Đã thực hiện:** Tạo root application shell bằng shadcn Sidebar/Sheet hiện có: sidebar responsive, sticky header, content area, active App Router navigation cho `/chat`, `/chat/[sessionId]` và `/documents`; `/` redirect sang `/chat`. Thêm skip link, một main landmark, named nav, `aria-current`, labelled headings/trigger, focus styles, đóng menu sau mobile navigation và Ctrl/Cmd+B. Cô lập `usePathname` dưới Suspense cho Next 16 cacheComponents. Các route chỉ có shell-level placeholder; không Chat UI, Documents UI, API/SSE integration hoặc dependency mới.
- **Files thay đổi:** `frontend/components/layout/app-shell.tsx`, `frontend/app/layout.tsx`, `frontend/app/page.tsx`, `frontend/app/chat/page.tsx`, `frontend/app/chat/[sessionId]/page.tsx`, `frontend/app/documents/page.tsx`, `FRONTEND_PLAN.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-03-04.md` (archive entry cũ nguyên vẹn để giữ 15 entry); giữ các thay đổi sẵn có.
- **Kiểm thử:** `npm.cmd run build` PASS (static routes và partial-prerender dynamic route); typecheck PASS; lint PASS; API/SSE regression PASS 38/38; contract verifier PASS 45 schemas; dev HTTP PASS `/` 307→`/chat`, ba representative routes 200 và rendered accessibility semantics; `git diff --check` PASS. Browser desktop/mobile/keyboard interaction BLOCKED/NOT RUN do Browser Node REPL lỗi khởi tạo path; không đánh dấu PASS. Groq=0, Gemini=0.
- **Tồn đọng / blocker:** Không blocker implementation. Cần rerun viewport/click/tab visual QA khi Browser plugin hoạt động. Shell không tải session/document data; placeholder functional UI thuộc task sau.
- **Tiếp theo:** `F2-02` NOT STARTED; dừng, không tự động triển khai.

### [2026-10-13] [FRONTEND/F1-03] — SSE parser foundation

- **Trạng thái:** COMPLETED; frontend F1 COMPLETED theo checklist, các task trước giữ COMPLETED.
- **Đã thực hiện:** Parser incremental Uint8Array/TextDecoder fatal cho event/data SSE, arbitrary UTF-8 chunk split, LF/CRLF/mixed endings, multiple/split/EOF events, multiline JSON data, comment/BOM và unknown event. Known frames runtime-check đúng sáu SSE DTO/Pydantic invariants và trả recognized discriminated result; safe parser errors không giữ raw payload. Parser frame-level không tự thực thi transcript order/terminal/citation provenance thuộc F3-01. Không fetch/hook/UI/retry/backend/dependency mới.
- **Files thay đổi:** `frontend/lib/sse/parser.ts`, `frontend/tests/sse-parser.test.mjs`, `FRONTEND_PLAN.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-03-04.md` (archive entry cũ nguyên vẹn để giữ 15 entry); giữ các thay đổi có sẵn.
- **Kiểm thử:** parser PASS 18/18 gồm fixture trực tiếp từ backend `encode_sse_event` với network blocked; API client + parser regression PASS 38/38; contract verifier PASS 45 schemas; build/typecheck/lint/diff/new-file whitespace PASS. Live stream/browser/UI/cloud/provider smoke NOT RUN; Groq=0, Gemini=0.
- **Tồn đọng / blocker:** Không blocker F1-03. Runtime hiện không emit citation event; parser vẫn hỗ trợ schema. Transcript sequence/order/single terminal/error-state/provenance và aggregate size policy chờ F3/F7; browser CORS/environment vẫn chưa xác minh. hooks/use-chat-stream và domain clients còn rỗng.
- **Tiếp theo:** `F2-01` NOT STARTED; dừng, không tự động triển khai.

## 4. Lưu trữ nhật ký cũ (archive)

- [Phase 1 + các entry M-03…M-06/P2-01 đã archive](./docs/changelog/phase-01.md)
- [Phase 2 — các entry P2 đã archive](./docs/changelog/phase-02.md)
- [Phase 3–4 — P3-04/P4-01…P4-04 cũ đã archive](./docs/changelog/phase-03-04.md)
