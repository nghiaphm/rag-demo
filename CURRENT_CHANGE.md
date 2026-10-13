# CURRENT_CHANGE — Nhật ký thực thi RAG V2

> **Vai trò:** Ghi ngắn gọn những gì Agent **thực sự đã làm** sau mỗi task, kèm file thay đổi, kiểm thử và công việc kế tiếp. Kế hoạch/checklist chính nằm tại [`PROJECT_LOG_V2.md`](./PROJECT_LOG_V2.md). Không tự nhận hoàn thành từ nội dung kế hoạch.

## 1. Trạng thái gần nhất

- **Giai đoạn:** Frontend F0/F1/F2/F3 COMPLETED; backend roadmap giữ nguyên.
- **Task vừa hoàn thành:** `[FRONTEND/F3-03]` — Cancel/recovery, 2026-10-14.
- **Task tiếp theo:** `F4-01` — NOT STARTED; chờ giao việc riêng.
- **Blocker:** Không có cho implementation F3-03; browser live SSE/cancel cần API base URL/CORS phù hợp và chưa chạy.
- **Lần cập nhật:** Controller cancel/recovery fixtures 8/8, combined frontend 58/58, 45-schema contract, build/typecheck/lint/diff PASS; chi tiết FRONTEND_PLAN mục 18. Groq/Gemini live calls = 0.

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

### [2026-10-13] [FRONTEND/F1-02] — API client/errors

- **Trạng thái:** COMPLETED; F0-01/F1-STAB/F1-01 giữ COMPLETED.
- **Đã thực hiện:** Wrapper REST fetch với explicit baseUrl, generic data/status/headers, JSON hoặc FormData, timeout bao gồm đọc body, caller AbortSignal/cleanup và default cache no-store. ApiClientError phân biệt HTTP/network/timeout/abort/invalid response, giữ HTTP status kể cả malformed error body; safe generic messages, chỉ lấy ChatError code/retryable, không lưu raw body/answer/detail/input/ctx. Không retry, không endpoint integration/UI/SSE/provider calls hoặc dependency mới.
- **Files thay đổi:** `frontend/lib/api/client.ts`, `frontend/tests/api-client.test.mjs`, `FRONTEND_PLAN.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-03-04.md` (archive entry cũ nguyên vẹn để giữ 15 entry); giữ các thay đổi có sẵn.
- **Kiểm thử:** `node --test tests/api-client.test.mjs` PASS 20/20 fake cases; `npm.cmd run build` PASS; typecheck sau build PASS; `npm.cmd run lint` PASS; `git diff --check`/new-file whitespace PASS. Một real GET `http://127.0.0.1:8000/health` qua client PASS HTTP 200/expected fields, không gọi dependencies/chat/documents. Browser CORS/UI/cloud/provider smoke NOT RUN; Groq=0, Gemini=0.
- **Tồn đọng / blocker:** Không blocker F1-02. baseUrl do caller cung cấp; env/CORS chưa cấu hình, Node health không chứng minh browser connectivity. Success DTO vẫn compile-time generic, chưa runtime validation; timeout 30s mặc định cần override cho ingestion đồng bộ sau này. Domain clients và parser giữ rỗng.
- **Tiếp theo:** `F1-03` NOT STARTED; dừng, không tự động triển khai.

### [2026-10-13] [FRONTEND/F1-01] — API Contract & TypeScript Types

- **Trạng thái:** COMPLETED theo phạm vi types được giao; F0-01/F1-STAB giữ COMPLETED.
- **Đã thực hiện:** Đối chiếu REST OpenAPI 11 paths/32 schemas, routers/Pydantic và SSE source; điền bốn types files cho health/dependencies, sessions/messages/history, chat/source/citation/usage/error, SSE event-discriminated union, documents/versions/ingestion/multipart và API errors. REST optionality theo OpenAPI required lists, required nullable giữ bắt buộc; wire SSE event/done.status luôn có. Thêm verifier offline dùng TypeScript có sẵn, không dependency mới. Không API client/parser/UI/backend logic/environment configuration hoặc provider calls.
- **Files thay đổi:** `frontend/types/{api,chat,document,sessions}.ts`, `frontend/tests/verify-api-contract.mjs`, `FRONTEND_PLAN.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-03-04.md` (archive entry cũ nguyên vẹn để giữ 15 entry). Giữ thay đổi stabilization đã có trong working tree.
- **Kiểm thử:** `node tests/verify-api-contract.mjs` PASS 45 schemas + keys/queries/multipart/list/narrowing/nullability/negative fixtures và mocked health/dependency status 200/503, network blocked; TypeScript check sau build PASS; `npm.cmd run build` PASS; `npm.cmd run lint` PASS; `git diff --check` PASS. UI E2E/cloud/provider smoke NOT RUN; Groq=0, Gemini=0.
- **Contract gaps / blocker:** Không blocker F1-01. History không có sources/ordinal mapping, không map citations array index vào `[n]`; runtime SSE không emit citation realtime. OpenAPI thiếu chi tiết health/SSE và dynamic 202/HTTPException statuses; error body có detail string, validation detail array hoặc full ChatResponse. Chưa progress/poll/download/size/scope-mutation APIs; API base URL/CORS/env example chưa triển khai theo phạm vi types lần này. Chi tiết và route mapping ở FRONTEND_PLAN mục 10.
- **Tiếp theo:** `F1-02` NOT STARTED; dừng, không tự động triển khai.

### [2026-10-13] [FRONTEND/F1-STAB] — Baseline Stabilization

- **Trạng thái:** COMPLETED; F0-01 giữ COMPLETED, F1-01 chưa bắt đầu.
- **Đã thực hiện:** Thêm default-export placeholder tối thiểu cho hai page.tsx; sửa use-mobile bằng useSyncExternalStore/matchMedia subscription, SSR snapshot false và cleanup listener. Không thay component/config/dependencies hay disable ESLint. Xác nhận Python 3.10.11 qua pyvenv.cfg/README/changelog và requirements hiện tại; khôi phục interpreter chính thức vào `.venv/runtime/python310`, backup cfg cũ và sửa home local; giữ nguyên site-packages. Không sửa FastAPI/database/RAG, không gọi provider.
- **Files thay đổi:** `frontend/app/chat/[sessionId]/page.tsx`, `frontend/app/documents/page.tsx`, `frontend/hooks/use-mobile.ts`, `FRONTEND_PLAN.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-03-04.md` (archive hai entry cũ nguyên vẹn). Ignored local environment: `.venv/pyvenv.cfg`, cfg backup, runtime interpreter/archive; không commit môi trường.
- **Kiểm thử:** `npm.cmd run build` PASS; `node node_modules/typescript/bin/tsc --noEmit --incremental false` sau build PASS; `npm.cmd run lint` PASS; Node inline hook SSR/snapshot/change/cleanup verification PASS; `git diff --check` PASS. Python version/prefix/SSL PASS 3.10.11 AMD64; `python -m pip check` PASS; requirements metadata/constraints PASS 18/18; import app/OpenAPI với network bị chặn PASS 11 paths/32 schemas. Browser E2E/backend full suite/cloud smoke NOT RUN. Groq=0, Gemini=0.
- **Tồn đọng:** Không còn blocker stabilization. Local interpreter home gắn workspace hiện tại; đổi đường dẫn cần cấu hình lại. Chưa có API base URL/CORS/client/types/parser, Chat UI/Document Management; giới hạn contract ở F0 chưa thay đổi. Nhật ký giữ 15 entry, lịch sử P4-01/P3-04 đã archive.
- **Tiếp theo:** `F1-01` NOT STARTED; dừng, không tự động chuyển task.

### [2026-10-13] [FRONTEND/F0-01] — Baseline Audit

- **Trạng thái:** COMPLETED — audit có evidence, baseline quality gates chưa đạt.
- **Đã thực hiện:** Audit source/tree/config/scripts/git/env names và dependency thực cài; Next 16.4.0, React 19.3.0, TS 5.9.3, Tailwind 4.3.3, shadcn 4.21.4, 14 UI components. API/types/parser/business hooks và chat/documents routes là file rỗng. Đối chiếu FastAPI routes/Pydantic/SSE với scaffold, ghi bảng đã có/thiếu/giới hạn và đề xuất F1-01 tại FRONTEND_PLAN mục 8. Không đổi chức năng/component/config, không cài dependency, không sửa backend; giữ thay đổi Git sẵn có.
- **Files thay đổi:** `FRONTEND_PLAN.md`, `CURRENT_CHANGE.md`.
- **Kiểm thử:** `npm.cmd ls --depth=0` PASS; `npm.cmd run build` FAIL sau compile thành công, TS2306/TS2344 vì hai page.tsx rỗng; `node node_modules/typescript/bin/tsc --noEmit --incremental false` FAIL sau build (lần trước generated route types PASS, không đại diện kết quả cuối); `npm.cmd run lint` FAIL 1 error/0 warnings tại use-mobile.ts:14, react-hooks/set-state-in-effect. `.venv/Scripts/python.exe` để sinh app.openapi() với network chặn BLOCKED vì thiếu Python310 interpreter; source contract audit hoàn tất. UI/E2E/backend/live smoke NOT RUN; Groq=0, Gemini=0.
- **Tồn đọng:** Chưa có API base URL/env example/CORS/proxy; history chỉ có citations, không có sources/ordinal mapping; stream không phát citation realtime; document list là array, upload/index đồng bộ, chưa có progress/download API/max-size contract. Sửa route/hook/interpreter cần phạm vi riêng; không che lỗi kiểm tra. Phần trạng thái cũ P5-04 đã đồng bộ với entry M-06/backend roadmap hiện có, không sửa PROJECT_LOG_V2.
- **Tiếp theo:** `F1-01` NOT STARTED. Dừng sau F0-01 theo yêu cầu.

### [2026-10-12] M-06 — Regression liên giai đoạn

- **Trạng thái:** COMPLETED; workstream migration M-01…M-06 và roadmap V2 hiện tại COMPLETED.
- **Đã thực hiện:** Audit coverage P2–P5 và bổ sung `verify_m06.py` làm gate xuyên giai đoạn trên FastAPI lifespan, MongoDB Atlas, Qdrant application collection và Gemini embedding thật. Verifier tạo đúng một session `SELECTED_DOCUMENTS` với whole-turn seed, dùng deterministic rewrite/generation để kiểm tra ổn định hai request `/chat` và `/chat/stream`: retrieval không thoát active version đã chọn, original query vẫn vào final prompt, JSON/SSE contract và usage đúng, SSE reconstruct đúng, sáu messages/request linkage/terminal status ổn định, JSON citation và terminal stream citation cùng truy ngược server source, guard được release. Script không sửa document/raw file/Qdrant point và cleanup session/messages chính xác. Thêm unit coverage cho SSE parser, scope và citation assertions; cập nhật README command/kết quả.
- **Files thay đổi:** `backend/scripts/verify_m06.py`, `backend/tests/test_m06_verification.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`.
- **Kiểm thử:** Live `verify_m06.py` — PASS 2 transports, 6 messages, 2 rewrite calls, 5 scoped sources mỗi transport, citation/persistence và cleanup; live read-only `smoke_provider_stream.py` — PASS 13 valid text deltas, usage present. Focused citation/scope/JSON/SSE/history tests PASS 42/42; toàn bộ unit/API/in-memory regression PASS 155/155; `compileall`, `pip check`, secret scan, README reference/fence check và `git diff --check` PASS. M-06 history retrieval eval với rewriter external thật — NOT RUN vì quyền chạy bị từ chối do nguy cơ gửi history/query payload sang provider; không tạo artifact và không đổi kết quả này thành PASS. Bằng chứng live P5-05 hiện có vẫn PASS 5/5.
- **Tồn đọng / quyết định:** Không phát hiện regression runtime nên không sửa production code. Integrated verifier cố ý deterministic ở rewrite/generation để tránh quota và dữ liệu đi ra provider; provider transport được smoke riêng bằng prompt không nhạy cảm. Các giới hạn đã chốt vẫn còn: thiếu auth/multi-tenant, approximate budget, conservative rewrite guard, stale generation guard sau hard crash, chưa realtime stream citations và eval corpus nhỏ.
- **Tiếp theo:** Không còn task chưa hoàn thành trong `PROJECT_LOG_V2.md`; chờ phạm vi mới được giao.

### [2026-10-12] P5-06 — Final docs

- **Trạng thái:** COMPLETED; Giai đoạn 5 COMPLETED.
- **Đã thực hiện:** Đối chiếu README với routes, Pydantic JSON/SSE contract, settings, history loader, context budget, query rewriter, shared RAG pipeline và evaluation runner hiện tại. Bổ sung luồng history-aware end-to-end từ MongoDB history/scope qua conditional rewrite, active-version Qdrant filter, budgeted prompt đến JSON/SSE/citation; thêm `/chat/stream` vào API table, `STREAM_TIMEOUT_SECONDS`, ví dụ persistent multi-turn, quy tắc server-owned history/scope, unit/focused/cloud smoke/evaluation commands và project tree P5. Làm rõ first-run/re-run/retrieval-only eval, quota behavior, external-provider data boundary và các giới hạn scale, detector/grounding, selected scope, version snapshot, realtime SSE citation, stale guard và heuristic eval. Không thay đổi runtime code hay API.
- **Files thay đổi:** `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`.
- **Kiểm thử:** README validation — PASS: 34 code fences cân bằng, đủ 8 section/marker bắt buộc, 9/9 referenced P5 files tồn tại, không còn marker tài liệu cũ; toàn bộ unit/API/in-memory regression PASS 152/152; `compileall`, `pip check`, `git diff --check` PASS. Không chạy lại live cloud smoke vì task chỉ thay tài liệu; dùng đúng bằng chứng live P5-04/P5-05 đã lưu và không đổi code/config.
- **Tồn đọng / quyết định:** Giai đoạn 5 đã hoàn thành nhưng các giới hạn trong README vẫn áp dụng: token estimate xấp xỉ, lexical detector/guard bảo thủ, long-session loader chưa summary, public API chưa đổi `SELECTED_DOCUMENTS`, SSE chưa phát realtime verified citations, stale guard sau hard crash, thiếu auth/multi-tenant và eval corpus nhỏ. `M-06` vẫn IN PROGRESS; không tự động nghiệm thu trong task tài liệu này.
- **Tiếp theo:** `M-06` — chờ giao việc riêng để chạy/đối chiếu regression liên giai đoạn và quyết định trạng thái cuối.

### [2026-10-12] P5-05 — Evaluation

- **Trạng thái:** COMPLETED; Giai đoạn 5 IN PROGRESS.
- **Đã thực hiện:** Thêm golden set 5 nhóm pronoun/follow-up, topic switch, long session, out-of-document và cross-document; runner chạy paired baseline không history với history-aware trên collection Qdrant eval cô lập. Tách production pipeline thành shared component seam để evaluation dùng đúng budget/rewrite/retrieval/prompt/generation runtime. Báo cáo ghi retrieval hit/recall, fact coverage, faithfulness proxy, fallback/referent accuracy, budget, latency và rewrite/generation tokens. Provider lỗi có retry hữu hạn, chỉ lưu loại lỗi; `--retrieval-only` cho phép kiểm tra retrieval/budget/rewrite khi quota generation bị chặn. Dependent query phải gọi rewriter; grounding rejection/timeout được chấp nhận như safe fallback nhưng vẫn phải độc lập vượt retrieval/answer gates.
- **Files thay đổi:** `backend/app/rag/pipeline.py`, `backend/evaluation/history_golden_set.json`, `backend/evaluation/history_eval.py`, `backend/evaluation/results/p5_history_eval.json`, `backend/evaluation/results/p5_history_retrieval.json`, `backend/scripts/eval_history_cli.py`, `backend/tests/test_history_evaluation.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`.
- **Kiểm thử:** Focused evaluation/RAG/rewrite/budget PASS 25/25; toàn bộ unit/API/in-memory regression PASS 152/152. Live retrieval-only PASS 5/5 executions, retrieval hit/recall `1.0`, mọi budget hợp lệ; referent answer accuracy là `null` vì mode này không generation. Live paired generation PASS 5/5: baseline và history-aware retrieval hit/recall, answer relevance, faithfulness proxy, fallback accuracy đều `1.0`; referent accuracy `1.0`; history-aware delta trung bình `+5873.7 ms`, tổng `+4120` tokens. Long-session rewrite timeout và cross-document grounding rejection fallback nguyên query an toàn rồi vẫn PASS. Không re-index application collection, không ghi MongoDB và không in credentials/raw provider response.
- **Tồn đọng / quyết định:** Corpus chỉ có 5 history cases và metrics grounding/fact coverage là heuristic, không thay thế human/LLM judge. Baseline đã retrieval đúng toàn bộ in-document cases trên corpus nhỏ nên lần chạy này không cho thấy uplift retrieval; giá trị history được xác minh qua referent answer và behavior rewrite. Latency/token phụ thuộc provider và có thể biến động giữa runs. `M-06` giữ IN PROGRESS đến final cross-phase audit ở P5-06.
- **Tiếp theo:** `P5-06` — chưa bắt đầu; chờ giao việc riêng. Không tự động triển khai P5-06 hoặc hoàn tất M-06.

### [2026-10-12] P5-04 — RAG integration

- **Trạng thái:** COMPLETED; Giai đoạn 5 IN PROGRESS.
- **Đã thực hiện:** Thay hai nhánh dựng context riêng bằng shared `PreparedRagStream` builder cho `/chat` và `/chat/stream`. Với session, runtime tải default whole-turn history và scope từ MongoDB, resolve `ALL_ACTIVE`/`SELECTED_DOCUMENTS` thành snapshot active version IDs rồi filter Qdrant; document missing/deleted/inactive bị loại. Builder budget system/history/ranked chunk blocks/original query/output reserve; conditional rewriter chỉ đổi query gửi retrieval, generation luôn nhận original query. History được ghi rõ chỉ để resolve tham chiếu, không phải nguồn citation; ordinal của chunk sau budget vẫn khớp source metadata để map Qdrant chunk → Mongo active version. Non-stream chuẩn hóa usage provider giống stream.
- **Files thay đổi:** `backend/app/rag/prompt.py`, `backend/app/rag/pipeline.py`, `backend/app/api/chat.py`, `backend/tests/test_rag_integration.py`, `backend/tests/test_chat_persistence.py`, `backend/tests/test_chat_stream.py`, `backend/scripts/smoke_rag_integration.py`, `README.md`, `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`.
- **Kiểm thử:** Focused scope/budget/rewrite/retriever/JSON/SSE — PASS 48/48; toàn bộ unit/API/in-memory regression — PASS 147/147; `compileall`, Python 3.10.11 và `pip check` — PASS. Live Atlas/Qdrant scoped smoke — PASS 1 active version, 5 sources, 1 whole history turn, citation provenance và exact cleanup. Live `/chat` — PASS HTTP 200/COMPLETED/5 sources. Live `/chat/stream` lần đầu terminal `RAG_STREAM_ERROR` an toàn do provider tạm thời; retry hữu hạn PASS HTTP 200, 204 deltas, terminal `done`, 5 sources. Không in credential/raw provider response.
- **Tồn đọng / quyết định:** Context token count vẫn là xấp xỉ. Scope được snapshot theo active versions lúc prepare; version đổi giữa prepare và provider completion không làm nới scope nhưng có thể khiến response dựa trên version vừa hết active. Streaming realtime citations vẫn rỗng theo contract citation-before-delta hiện tại; terminal persistence recompute citations từ answer/source. Multi-turn quality/eval, topic switching và long-session comparison thuộc P5-05.
- **Tiếp theo:** `P5-05` — chưa bắt đầu; chờ giao việc riêng. Không tự động triển khai P5-05.

## 4. Lưu trữ nhật ký cũ (archive)

- [Phase 1 + các entry M-03…M-06/P2-01 đã archive](./docs/changelog/phase-01.md)
- [Phase 2 — các entry P2 đã archive](./docs/changelog/phase-02.md)
- [Phase 3–4 — P3-04/P4-01…P4-04 cũ đã archive](./docs/changelog/phase-03-04.md)
