# Phase 2 — Nhật ký đã lưu trữ

> Các entry dưới đây được chuyển nguyên nội dung từ `CURRENT_CHANGE.md` theo quy tắc chỉ giữ 10–15 entry gần nhất.

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
