# FRONTEND_PLAN.md — RAG Workspace (Next.js)

> Frontend roadmap & agent execution contract. Cập nhật checklist theo bằng chứng thực thi, không đánh dấu PASS chỉ vì code đã được viết.

## 0. Bối cảnh và nguồn sự thật

- Backend RAG: FastAPI API-first; MongoDB Atlas (documents/sessions/messages), Qdrant Cloud (retrieval), Gemini (embedding), Groq (LLM). Các backend phase đã được người dùng báo cáo hoàn thành.
- Frontend: thư mục `frontend/` đã khởi tạo Next.js và shadcn/ui; đã cài một số UI components, tạo cấu trúc thư mục và chạy Next.js thành công theo báo cáo người dùng. **Agent phải audit lại thực tế**, không reinitialize hoặc ghi đè.
- `PROJECT_LOG_V2.md`: kiến trúc/roadmap backend, không sửa checklist cũ trừ khi phát hiện vấn đề được giao xử lý.
- `CURRENT_CHANGE.md`: nhật ký thực thi dùng chung; entry frontend có tiền tố `[FRONTEND/Fx-yy]`. Giữ mới nhất ở trên, tóm tắt file thay đổi, test (PASS/FAIL/BLOCKED/NOT RUN), blocker và next task; archive khi dài.
- `README.md` và source FastAPI/Pydantic/OpenAPI: nguồn xác nhận **API contract thực tế**; không suy đoán field hoặc route từ file kế hoạch này.

## 1. Mục tiêu và phạm vi

Xây RAG Workspace UI: chat streaming, conversation persistence, citations, knowledge base/document lifecycle, responsive và demo ổn định. Next.js là API client; business logic, session ownership, document indexing, retrieval và external provider credentials nằm ở FastAPI. Không bổ sung frontend AI orchestration/Next.js database integration.

### Stack dự kiến

Next.js App Router + TypeScript + Tailwind + shadcn/ui; `fetch` + `ReadableStream` để tiêu thụ `POST /chat/stream` SSE; `react-markdown`/`remark-gfm` khi cần. State đơn giản bằng React Hooks trước; chỉ thêm dependency nếu task chứng minh nhu cầu. Không đưa `GROQ_API_KEY`, Gemini/MongoDB/Qdrant credentials vào biến `NEXT_PUBLIC_*`.

### Kiến trúc luồng

`Browser (Next.js) → FastAPI REST/SSE → MongoDB / Qdrant / Gemini / Groq`.

## 2. Quy tắc bắt buộc cho Coding Agent

1. Đầu mỗi lượt: đọc file này, entry frontend mới nhất trong `CURRENT_CHANGE.md`, audit đúng source liên quan. Không cần đọc lại toàn bộ lịch sử changelog nếu không liên quan.
2. Chỉ làm **một task ID** được người dùng giao. Không tự chuyển phase hoặc triển khai task NEXT.
3. Ưu tiên tận dụng code/component/config hiện hữu; không tạo lại app, không thêm thư viện hoặc đổi design system tùy tiện.
4. Trước khi code: nêu hiện trạng, phạm vi, file dự kiến thay đổi, acceptance criteria và rủi ro. Nếu backend contract mâu thuẫn, báo cáo và dừng thay vì tự sửa backend.
5. Sau khi code: test phù hợp, báo cáo lệnh/kết quả; phân biệt PASS, FAIL, BLOCKED, NOT RUN. Không tự suy diễn test chưa chạy là PASS.
6. Mặc định **0 live Groq/Gemini calls** trong unit/component/integration tests; dùng fixture/mock SSE. Live smoke chỉ khi người dùng cho phép, tối thiểu request, không retry 429 hàng loạt.
7. Không commit `.env*` chứa credentials; `.env.example` chỉ placeholder; không log raw secrets, private document contents hoặc provider responses nhạy cảm.
8. Không sửa `PROJECT_LOG_V2.md` và business logic FastAPI ngoài phạm vi task. Không xóa/migrate MongoDB, Qdrant hoặc file storage trong frontend work.
9. Mọi thao tác nguy hiểm (delete/reindex) có xác nhận trên UI, phản ánh đúng backend semantics; client không giả định thành công trước response.
10. Kết thúc: cập nhật checkbox của task và dashboard bên dưới, thêm entry ngắn vào `CURRENT_CHANGE.md`, nêu **next task chưa bắt đầu**.

## 3. Dashboard

| Phase | Trạng thái | Ghi chú |
| --- | --- | --- |
| F0 — Baseline audit | COMPLETED | F0-01 audit 2026-10-13; build/typecheck/lint FAIL, OpenAPI runtime BLOCKED; xem mục 8 |
| F1 — Foundation/API | COMPLETED | F1-STAB và F1-01…F1-03 COMPLETED; environment/CORS browser là giới hạn đã ghi |
| F2 — Layout/Design | COMPLETED | F2-01…F2-03 COMPLETED; interaction QA bị giới hạn bởi Browser plugin đã ghi |
| F3 — Chat/SSE | COMPLETED | F3-01…F3-03 COMPLETED; mock stream/state/cancel regression PASS |
| F4 — Sessions/History | COMPLETED | F4-01…F4-03 COMPLETED; scripted multi-turn HTTP mock PASS, live smoke chưa chạy |
| F5 — Sources/Citations | COMPLETED | F5-01/F5-02 COMPLETED; callback/Markdown/history fixtures PASS; browser interaction BLOCKED |
| F6 — Documents | COMPLETED | F6-01…F6-03 COMPLETED; protected-action/stale-state mocks PASS; live mutation chưa chạy |
| F7 — UX/Resilience | IN PROGRESS | F7-01 COMPLETED; F7-02 implementation xong, chờ manual acceptance |
| F7-03 — Functional Completeness & API Integration | IN PROGRESS | F7-03-05 gate NOT PASSED: BUG-STREAM-001 terminal/history parity FAIL và browser/manual BLOCKED; task02/03/04 automated checks xong |
| F8 — Testing/E2E | NOT STARTED | |

**Task đang thực hiện:** F7-03-05 — Functional QA & Regression, IN PROGRESS; gate NOT PASSED, evidence mục35/[QA report](./docs/frontend-functional-qa.md). **Blockers:** BUG-STREAM-001 cần bugfix riêng; actual browser/manual NOT RUN. **Checks:** frontend193/193/build7/7/typecheck/lint/contract45/runtime OpenAPI/CORS/production HTTP PASS; backend80/81 PASS,1 FAIL parity thật. F8 NOT STARTED; không tự chuyển hoặc waive manual AC. No provider calls.

## 4. Roadmap và acceptance criteria

### F0 — Baseline Audit (không đổi chức năng)

- [x] **F0-01 — Audit frontend/backend contracts:** Inspect versions, Next.js App Router, `frontend/` tree, shadcn/ui components đã cài, scripts/build/lint, git status, biến env public; đối chiếu FastAPI routes + Pydantic schemas + OpenAPI/SSE events/session/document semantics; lập bảng implemented/missing/conflict. Chạy existing build/typecheck/lint nếu có. **Không code chức năng mới**. AC: audit có evidence, đề xuất task F1-01 và không xóa cấu hình cũ.

### F1 — Foundation & API Contract

- [x] **F1-STAB — Baseline Stabilization (task bổ sung được giao):** Hai route placeholder default export hợp lệ; sửa hook mobile bằng external-store subscription, giữ ESLint rules; xác minh Python 3.10.11/requirements và khôi phục interpreter, giữ dependency hiện có. AC: frontend build/typecheck/lint đều PASS, git diff --check PASS, backend verification được báo cáo đúng; không API client/Chat UI/SSE parser/Document Management. Evidence mục 9.
- [x] **F1-01 — API Contract & TypeScript Types (phạm vi người dùng giao):** Đối chiếu REST OpenAPI/Pydantic và SSE source; DTO health/dependencies, sessions/messages/history, chat/usage/citations, SSE discriminated union, documents/versions/ingestion/multipart và API errors; phân biệt required/optional/nullable, ghi contract gaps. AC: contract parity, typecheck/build/lint/diff PASS, không API client/parser/UI/provider calls. API base URL/env example/CORS trong mô tả ban đầu chưa triển khai, chờ phạm vi environment riêng; không coi đây là môi trường kết nối đã PASS.
- [x] **F1-02 — API client/errors:** Tạo wrapper `fetch` tối giản cho REST, timeout/AbortSignal nếu cần, parse safe errors; không nuốt HTTP status. AC: fake tests cho 2xx, 4xx, 5xx, network error; health connectivity manual PASS hoặc BLOCKED rõ ràng. Evidence mục 11: 20/20 tests, build/typecheck/lint/diff PASS, localhost GET /health qua client PASS.
- [x] **F1-03 — SSE parser foundation:** Pure parser cho SSE `event:`/`data:` xử lý UTF-8 split, CRLF/LF, multiple events per network chunk, JSON/unknown event theo contract; **chưa làm Chat UI**. AC: deterministic tests, zero LLM calls. Evidence mục 12: parser tests 18/18, backend encoder fixture, build/typecheck/lint/diff PASS.

### F2 — Layout & Design System

- [x] **F2-01 — Application shell:** responsive sidebar/header/content area, routes Chat và Documents theo Next.js App Router; tận dụng shadcn/ui có sẵn, không lắp cả thư viện vô cớ. AC: desktop/mobile usable, keyboard accessible. Evidence mục 13: build/typecheck/lint, route/semantic HTTP checks PASS; Browser interaction BLOCKED bởi Node REPL của công cụ.
- [x] **F2-02 — Chat static components:** composer, user/assistant bubbles, Markdown/content placeholders, empty/loading/error mock states. AC: UI chỉ dùng fixtures, chưa live generation. Evidence mục 14: component/fixture boundaries, build/typecheck/lint/regression/HTTP checks PASS; Browser interaction BLOCKED bởi Node REPL của công cụ.
- [x] **F2-03 — Documents static components:** list/detail/upload/status/confirm/dialog placeholders dựa trên backend contract. AC: responsive, chưa mutate backend. Evidence mục 15: typed fixtures, disabled mutation actions, build/typecheck/lint/regression/HTTP checks PASS; Browser interaction BLOCKED bởi Node REPL của công cụ.

### F3 — Chat & SSE Streaming (MVP core)

- [x] **F3-01 — Stream client:** `POST /chat/stream` bằng `fetch` + `ReadableStream`, parse `start`, `metadata`, `delta`, `done`, `error`; giữ `sequence`, request/session/message IDs, `usage` nếu có; lỗi trước HTTP 200 khác lỗi sau khi SSE đã mở. AC: mock SSE fixture tests; không coi `reader.read()` là một event; không coi delta là một token/từ. Evidence mục 16: targeted 12/12, combined 50/50, build/typecheck/lint/contract/diff PASS; 0 live calls.
- [x] **F3-02 — Chat state/UI integration:** gửi question; session ID do backend trả về hoặc tạo trước qua session API đúng contract; buffer delta giữ nguyên whitespace; cập nhật assistant draft, terminal statuses; chặn submit trùng khi đang generate. AC: successful stream fixture kết thúc COMPLETED, không ghép sai nội dung. Evidence mục 17: targeted 4/4, combined 54/54, build/typecheck/lint/contract/diff PASS; 0 live calls.
- [x] **F3-03 — Cancel/recovery:** AbortController Stop Generating, component unmount/navigation cleanup, partial text/status/error UI theo backend semantics, tránh retry tự động request đã gửi. AC: fake disconnect/error tests, không loading vô hạn. Evidence mục 18: targeted 8/8, combined 58/58, build/typecheck/lint/contract/diff PASS; 0 live calls.

### F4 — Sessions & Conversation History

- [x] **F4-01 — Session list/New Chat:** REST client hooks + sidebar; không yêu cầu người dùng tự nhập UUID; thiếu/invalid session xử lý rõ. AC: new/open session bằng mock API. Evidence mục 19: targeted 7/7, combined 65/65, build/typecheck/lint/contract/diff PASS; 0 live calls.
- [x] **F4-02 — History/pagination:** load messages theo backend schema và thứ tự ổn định; URL phản ánh current session; refresh phục hồi từ backend, không dùng localStorage như system of record. AC: hai session không bị trộn, pagination đúng nếu có. Evidence mục 20: targeted 13/13, combined 71/71, build/typecheck/lint/contract/diff PASS; 0 live calls.
- [x] **F4-03 — Multi-turn integration:** reuse session_id; đổi session giữa stream không leak deltas; request IDs distinct; validate lại backend persisted messages. AC: 3-turn scripted E2E mock; live smoke khi được phép. Evidence mục 21: multi-turn tests 9/9 trong full regression 80/80, build/typecheck/lint/contract/diff PASS; browser/live smoke NOT RUN, 0 provider calls.

### F5 — Sources & Citations

- [x] **F5-01 — Source mapper:** mapping `[1]` → source position trong metadata của **đúng assistant message** (không phải `chunk_index`); lưu `document_id`, `version_id`, `chunk_id`, `file_name`, `page`; xác minh backend page convention 0/1-based. AC: test sparse/repeated/out-of-range citations; không tạo link giả. Evidence mục 22: targeted 11/11, combined 91/91, PDF loader thực tế xác nhận page 0-based, build/typecheck/lint/contract/diff PASS; 0 provider calls.
- [x] **F5-02 — Citation UI:** clickable citations/source drawer, grouped file/page, state fallback khi metadata thiếu; Markdown text không làm mất citation. AC: click citation đúng nguồn; refresh/history vẫn hiển thị nếu backend persist sources. Evidence mục 23: 10 citation UI fixtures trong full 101/101 regression, build/typecheck/lint/contract/diff PASS; browser click/keyboard/viewport BLOCKED, live smoke NOT RUN; history citations hiển thị không đoán ordinal.

### F6 — Document Management

- [x] **F6-01 — List/detail/status:** fetch/pagination/filter theo routes có thật; hiển thị document status và `active_version_id` riêng biệt. AC: loading/empty/error đúng. Evidence mục 24: targeted 12/12, combined 113/113, build/typecheck/lint/contract/diff PASS; GET-only, 0 provider calls.
- [x] **F6-02 — Upload/progress:** file type/size validation khớp backend, `multipart/form-data` đúng schema; phản hồi UPLOADED/PROCESSING/INDEXED/FAILED thực tế, không giả lập thành công. AC: mocked success/failure, một live file test khi được phép. Evidence mục 25: upload 13 tests trong full 126/126, build/typecheck/lint/contract/diff PASS; live file test NOT RUN (chưa có quyền), 0 provider calls.
- [x] **F6-03 — Versions/reindex/delete:** update/version flows đúng backend contract, confirmations, idempotent delete semantics, preserve active version khi version mới thất bại; không tuyên bố raw files đã xóa nếu soft-delete. AC: tests cho protected actions và stale state. Evidence mục 26: 13 action tests trong full 139/139, build/typecheck/lint/contract/diff PASS; 0 live/provider mutations.

### F7 — UX & Resilience

- [x] **F7-01 — Error/health UX:** lỗi 422, 404, 409 nếu contract có, 429, 503 MongoDB/Qdrant/Groq, network, post-header SSE `error`; safe messages, retry có chủ đích, không request loop. AC: fixture tests và no infinite spinner. Evidence mục 27: targeted 12/12, full 151/151, build/typecheck/lint/contract/diff PASS; health MongoDB/Qdrant manual, Groq readiness không suy đoán; 0 live calls.
- [ ] **F7-02 — UI polish/accessibility:** auto-scroll tôn trọng người đang đọc, copy, responsive drawer, focus/keyboard, skeleton, markdown/code rendering, optional theme; không scope creep PDF viewer nếu backend không hỗ trợ. AC: manual UX/accessibility checklist.
  - Implementation và automated checks PASS; manual checklist có tại `docs/frontend-accessibility-checklist.md`, manual nghiệm thu NOT RUN/BLOCKED, chưa đánh dấu COMPLETED.
  - Browser blocker đã xác định là package/runtime incompatibility; Chrome/Edge mock-only handoff có tại `docs/frontend-browser-qa-blocker.md` và `frontend/scripts/qa-mock-api.mjs`. Tất cả manual AC vẫn NOT RUN.

### F7-03 — Functional Completeness & API Integration

- [x] **F7-03-01 — API Capability Audit & Functional Gap Analysis:** source/OpenAPI/client/UI/tests audit đầy đủ Session/Chat/Documents/Integration; Functional Capability Matrix, backlog có scope/dependencies/AC/tests/out-of-scope và technical debt. Evidence mục31; chỉ sửa documentation.
- [ ] **F7-03-02 — Session Actions:** nối PATCH title/DELETE có thật, accessible menu/dialog, current-session navigation, backend409 guard, list pagination/refresh và mutation reconciliation. IN PROGRESS: implementation/checks PASS, browser keyboard/focus/mobile NOT RUN; chi tiết mục31.4/32.
- [ ] **F7-03-03 — Chat Actions Completion:** nối session creation từ composer với sidebar, làm rõ deferred URL/recovery và history PENDING/STREAMING không có live stream; giữ Stop/copy/citations/SSE hiện có. IN PROGRESS: implementation/checks PASS; mock browser interaction NOT RUN/BLOCKED, mục33; không Edit/Regenerate/Delete Message.
- [ ] **F7-03-04 — Document Actions Completion:** nghiệm thu và sửa gap có bằng chứng trong wired F6 actions, refresh/reconciliation/status/confirm dialogs; không triển khai lại upload/version/re-index/delete. IN PROGRESS: automated verification PASS, sửa aborted-page slot có regression; browser confirm/Escape/focus/mobile NOT RUN/BLOCKED, mục34.
- [ ] **F7-03-05 — Functional QA & Regression:** mock end-to-end CRUD/session streaming/document lifecycle, actual browser/manual acceptance, contract/error/keyboard/mobile checks; resolve hoặc accept rõ technical debt trước F8. IN PROGRESS: frontend193/193 PASS, backend80/81 PASS/1 FAIL BUG-STREAM-001; browser/manual BLOCKED/NOT RUN; gate chưa đạt, mục35 và QA report.

### F8 — Final Verification & Demo

- [ ] **F8-01 — Automated tests:** TypeScript/build/lint, unit parser/client/mapper, component/integration tests, Playwright mock E2E cho session/chat/doc/error/cancel; 0 live provider calls mặc định. AC: reported counts, no hidden blockers.
- [ ] **F8-02 — Controlled live E2E:** verify health; new chat → multi-turn same session → refresh history → citation → document operation (on test namespace); small Groq request budget approved by user; cleanup; capture TTFT/latency if timing available. AC: all relevant tests PASS or explicit BLOCKED, no test leftovers.
- [ ] **F8-03 — Demo readiness:** README frontend run instructions, `.env.example`, CORS note, deployment/runtime assumptions, smoke checklist, known limitations and screenshot/video only if requested. AC: clean dev startup and reproducible demo.

**MVP gate:** F0–F4. **Full demo gate:** F0–F8. Do not mark entire backend validated solely by three successful chat requests; they are manual happy-path evidence.

## 5. Implementation priorities / edge cases

- SSE: fetch POST, UTF-8 streaming decode, `\n\n` / CRLF event boundaries, multiple/split chunks, empty/non-text deltas, `sequence` ordering, done vs error, AbortController, status and usage. UI buffering can reduce excessive rerenders without altering backend chunk content.
- Session: validate backend behavior for omitted `session_id`; use `POST /sessions` if required. Do not fabricate UUID or auto-create an unknown requested session.
- Citations: message-local source order, mapping to document/version/chunk, no unsupported PDF preview/download links.
- Documents: active version, index failures, soft-delete and stale/in-flight operations must be rendered accurately.
- UI testing: fixtures reflect **actual** SSE payload such as `start` IDs/mode, `metadata` model/sources, `delta.content`, `done.status/usage`.

## 6. Task completion report template

```text
Task: Fx-yy
Scope: ...
Changed files: ...
Tests: [command] — PASS/FAIL/BLOCKED/NOT RUN; live requests: N
Acceptance criteria: ...
Known issues/blockers: ...
Docs: FRONTEND_PLAN.md checkbox/dashboard; CURRENT_CHANGE.md entry
Next task (NOT STARTED): ...
```

## 7. Prompt khởi động duy nhất — F0-01

```text
Đọc FRONTEND_PLAN.md, mục frontend mới nhất trong CURRENT_CHANGE.md, README.md, PROJECT_LOG_V2.md và inspect source thực tế.
Chỉ thực hiện F0-01 Baseline Audit. Tôi đã cài Next.js, shadcn/ui, một số components và tạo cấu trúc frontend; KHÔNG khởi tạo lại hoặc ghi đè.
Audit file tree/config/dependencies/scripts, Next build/typecheck/lint, routes/backend Pydantic/OpenAPI và contract SSE, sessions, documents. Không gọi external LLM/embedding.
Ghi implemented/missing/conflicts, những điểm cần giữ nguyên, file dự kiến cho F1-01, test results. Cập nhật dashboard/checklist và CURRENT_CHANGE.md. Không triển khai F1-01; dừng sau khi báo cáo.
```

## 8. Evidence F0-01 — Baseline Audit (2026-10-13)

Phạm vi: đọc source/config/dependencies hiện tại, đối chiếu contract và chạy quality gates; chỉ sửa tài liệu. Không reinitialize, cài dependency, sửa component/config/backend hoặc gọi Groq/Gemini. F0-01 COMPLETED vì audit đã có bằng chứng; các quality gates FAIL/BLOCKED vẫn được giữ nguyên bên dưới.

### 8.1. Frontend thực tế

- Runtime: Node `24.20.0`, npm `11.19.0`. `npm.cmd ls --depth=0` PASS, không báo missing/invalid dependency. Phiên bản thực cài: Next `16.4.0`, React/React DOM `19.3.0`, TypeScript `5.9.3`, ESLint `9.39.5`, eslint-config-next `16.4.0`, Tailwind/@tailwindcss/turbopack `4.3.3`, shadcn `4.21.4`, @base-ui/react `1.9.0`, lucide-react `1.56.0`, cn `0.4.0`, class-variance-authority `0.7.1`, tw-animate-css `1.4.0`. Markdown đã có react-markdown `10.1.0`, remark-gfm `4.0.1`, rehype-highlight `7.0.2`; chưa dùng trong UI.
- App Router ở `frontend/app/`, không dùng `src/`. `/` vẫn là starter Next; layout dùng Geist/Geist Mono qua `next/font/google`, metadata Create Next App, `lang=en`, global `LayoutProps<"/">`. `app/chat/[sessionId]/page.tsx` và `app/documents/page.tsx` tồn tại nhưng **0 byte**, chưa phải route triển khai hợp lệ.
- `components.json`: `base-nova`, Base UI, RSC/TSX, neutral, Lucide; alias `@/*` trỏ root frontend. Giữ nguyên 14 components: avatar, badge, button, card, dialog, dropdown-menu, input, scroll-area, separator, sheet, sidebar, skeleton, textarea, tooltip. `lib/utils.ts` export `cn` từ package `cn`; `hooks/use-mobile.ts` đã có implementation.
- Các file **0 byte**: `types/{api,chat,document,sessions}.ts`, `lib/api/{client,chat,documents,sessions}.ts`, `lib/sse/parser.ts`, `hooks/{use-chat-stream,use-sessions}.ts`. Thư mục `components/{chat,citations,documents,layout,sessions}` và `tests/` trống. Không coi file/thư mục scaffold là chức năng đã triển khai.
- Scripts có `dev/build/start/lint`; không có script typecheck/test hoặc test runner. `tsconfig.json` strict/noEmit, có `.next/types` và `.next/dev/types`; chạy trực tiếp compiler đã cài để typecheck. ESLint dùng Next core-web-vitals + TypeScript. `next.config.ts` giữ `agentFeedback`, `cacheComponents`, `partialPrefetching` và CSS loader Turbopack. CSS đã có Tailwind imports, theme tokens/light-dark, shadcn; chưa có application shell.
- Không có `.env*` trong frontend; không tìm thấy `NEXT_PUBLIC_*`, `process.env` hoặc API `fetch` trong source frontend/config. Không có biến `NEXT_PUBLIC_*` trong môi trường shell audit. Root `.env.example` chỉ có cấu hình backend, chưa có public API base URL; không đọc/in giá trị secrets root `.env`. `frontend/.gitignore` bỏ qua `.env*`, nên khi F1-01 tạo `.env.example` cần exception hẹp cho đúng file example.
- Git đầu lượt đã dirty: CURRENT_CHANGE, PROJECT_LOG_V2, README, docs/changelog/phase-02; FRONTEND_PLAN, backend/scripts/verify_m06.py, backend/tests/test_m06_verification.py, frontend là untracked. Có thay đổi staging trong lúc audit; không stage/unstage/revert các thay đổi đó. Thay đổi task này chỉ ở FRONTEND_PLAN và CURRENT_CHANGE; build sinh artifact ignored trong `.next`/Next type declarations.

### 8.2. Mapping contract FastAPI → frontend

Evidence: `backend/app/{main,schemas,conversation_schemas,conversation_models,document_models,sse_schema}.py`, `backend/app/api/{chat,sessions,documents}.py`, README và PROJECT_LOG_V2. Đã đối chiếu route decorators, request/response models, khai báo OpenAPI của endpoint; **chưa xác minh OpenAPI JSON runtime** do interpreter lỗi. Không chạy lifespan (có kết nối cloud và khởi tạo indexes).

| Nhóm / trạng thái | Contract thực tế | Frontend hiện tại / thiếu / điều chỉnh |
| --- | --- | --- |
| Foundation — đã có / thiếu | Backend hướng dẫn port 8000; frontend README port 3000. `main.py` không có CORS middleware; Next config không có rewrite/proxy. | Giữ app/config hiện hữu. Thiếu base URL/types/client; browser gọi trực tiếp khác origin sẽ cần CORS hoặc proxy. F0 chỉ ghi nhận, không sửa backend. |
| Health — thiếu client | `GET /health` trả status và llm_model; `GET /health/dependencies` trả status/dependencies, HTTP 200 hoặc 503 và thực hiện kiểm tra cloud. | Chưa có client/health UX; không gọi readiness trong audit này. |
| Chat — thiếu types/client | `POST /chat` và `/chat/stream` nhận `{question, session_id?: UUID | null}`; question trim và từ chối blank. Bỏ session_id là STATELESS, **không tự tạo session**. Session đã xóa 410, không tồn tại 404, generation conflict 409; validation 422, dependency/persistence 503. | Tạo chat bền vững qua `POST /sessions` rồi gửi ID có thật; không tự sinh UUID hay gửi history/scope từ browser. Types/chat API hiện rỗng. |
| JSON reply — thiếu | ChatResponse gồm request/session/user_message/assistant_message IDs, answer nullable, sources[], citations[], metadata `{mode,model}`, usage nullable `{input_tokens,output_tokens,total_tokens}`, status COMPLETED/PARTIAL/FAILED, error nullable `{code,message,retryable}`. Stateless session/message IDs null. | Phải giữ nullability và các arrays; lỗi generation HTTP 502 có thể là full ChatResponse FAILED; lỗi trước logical reply dùng FastAPI `detail`, không chỉ một error envelope. |
| SSE — thiếu / giới hạn runtime | POST qua fetch/ReadableStream, `event:` + JSON `data:` + dòng trống. start IDs/mode, metadata model/sources, delta.content, done COMPLETED/usage hoặc error FAILED/PARTIAL/error/usage; mọi data có sequence từ 1 liên tục. Typed schema có citation event, nhưng runtime hiện chỉ start→metadata→delta*→done/error, không phát citation realtime. Headers no-cache/no-transform, X-Accel-Buffering no. | Parser/hook rỗng. Cần decode UTF-8 streaming, event boundaries LF/CRLF và abort; ghép nguyên delta.content. Cancel/disconnect không nhận terminal frame; persist best-effort RAG_STREAM_CANCELLED, status phụ thuộc đã có content. Không chờ citation event để kết thúc. |
| Sessions/history — thiếu | POST `/sessions` nhận body `{title?: string | null}` (title tối đa 200), trả 201 SessionResponse. GET `/sessions` offset=0/limit=50, max=200, envelope items/offset/limit/total; GET `/{id}`; PATCH `/{id}` body title; GET `/{id}/messages` offset=0/limit=100, max=500; DELETE `/{id}`. Scope response ALL_ACTIVE hoặc SELECTED_DOCUMENTS; API chỉ tạo mặc định ALL_ACTIVE, chưa có endpoint đổi scope. | Types/sessions, client và hook rỗng. History tăng theo sequence, role USER/ASSISTANT, status PENDING/STREAMING/COMPLETED/PARTIAL/FAILED; fields gồm content, citations, model/usage, request/error IDs và timestamps. DELETE soft-delete session, hard-delete messages, giữ tombstone; lặp lại idempotent. Chưa có auth/multi-tenant. |
| Citations — thiếu / giới hạn history | Source fields file_name/source/document_id/version_id/chunk_id/chunk_index/page đều nullable. Citation có UUID chunk/document/version + file_name/page, không có ordinal. `[n]` map vào source thứ n của đúng reply, không phải chunk_index. History trả citations nhưng **không trả sources hoặc ordinal mapping**. | Không thể phục hồi đầy đủ mapping `[n]`→source từ citations array lịch sử; trước mắt chỉ có thể trình bày references đã lưu, không giả định citation thứ n là `[n]`. Muốn parity sau refresh cần chốt contract riêng, không tự sửa backend. PDF page 0-based theo PyPDFLoader và parser cài tại `.venv/Lib/site-packages/langchain_community/document_loaders/parsers/pdf.py` (`enumerate`, page=page_number); UI PDF hiển thị page+1, không đổi ID/page contract; text/page thiếu là null. |
| Documents — thiếu | POST `/documents/upload`, PUT `/documents/{id}` nhận multipart field `file`, trả 201 DocumentIndexInfo `{document_id,version_id,job_id,file_name,num_chunks,status,activated}`; POST `/{id}/re-index` không body, trả 201. GET `/documents` include_deleted=false, offset=0, limit=100 (max 500), trả **array DocumentInfo**, không có total envelope/filter status. GET `/{id}` trả DocumentDetail + versions. | Types/document và client/trang còn rỗng. DocumentInfo có active_version_id nullable, chunk_count/version_count/cleanup_pending và timestamps; version có checksum/size/chunk_count/embedding_model/timestamps. Không nhầm num_chunks của index với chunk_count của list. |
| Upload/delete — giới hạn cần phản ánh | Upload/index đồng bộ: chờ parse/embed/index/verify mới trả INDEXED, chưa có job polling/progress API dù response có job_id. Status enum UPLOADED/PROCESSING/INDEXED/FAILED/DELETED. Hỗ trợ `.pdf/.md/.markdown/.txt/.xlsx` theo loader; không thấy max upload bytes trong route/settings. DELETE document trả 200 hoặc 202 nếu cleanup_pending, retained raw files, retrieval_eligible=false; lặp lại retry cleanup. Candidate version fail giữ active version cũ. | Không giả lập backend progress, không invent size limit/poll/download/PDF route. UI có thể báo request đang xử lý; size limit nếu thêm phải nói rõ là giới hạn client. Thiếu confirmations/status/error UX. |

### 8.3. Quality gates đã chạy

Các lệnh frontend chạy tại `frontend/`. Dùng `npm.cmd` vì PowerShell chặn `npm.ps1`; không đổi execution policy.

| Lệnh / kiểm tra | Kết quả | Evidence / giới hạn |
| --- | --- | --- |
| `npm.cmd ls --depth=0` | PASS | Dependency tree thực cài hợp lệ; không cài/cập nhật package. |
| `npm.cmd run build` | FAIL (exit 1) | Compile thành công 6.6s, typecheck fail: TS2306 hai page.tsx rỗng không phải module; TS2344 ở generated route validator. Không đạt production build. |
| `node node_modules/typescript/bin/tsc --noEmit --incremental false` | FAIL (exit 1), sau build | Cùng TS2306/TS2344 trong `.next/types/validator.ts`. Lần trước khi build sinh route types PASS, không dùng kết quả đó để kết luận baseline type-safe. |
| `npm.cmd run lint` | FAIL (exit 1) | 1 error, 0 warnings: `hooks/use-mobile.ts:14`, react-hooks/set-state-in-effect, setIsMobile đồng bộ trong effect. Không sửa hook hay tắt rule trong F0. |
| `.\.venv\Scripts\python.exe -` để import app và gọi `app.openapi()` với socket network bị chặn | BLOCKED | Interpreter không khởi động: đường dẫn Python310 trong `.venv` không tồn tại. Source/decorator/schema audit hoàn tất; runtime OpenAPI chưa được sinh. Không sửa/recreate venv. |
| UI/E2E, live health/cloud, backend test suite | NOT RUN | Không có frontend test runner; task baseline không chạy provider/cloud smoke. Groq=0, Gemini=0; không mutate cloud data. |

### 8.4. Điều chỉnh đề xuất — chưa triển khai

- F1-01: xác nhận public API base URL và origins localhost/127.0.0.1:3000→8000, chọn CORS hoặc proxy trong phạm vi được giao; tạo `frontend/.env.example` placeholder và exception `.gitignore`; điền `frontend/types/{api,chat,document,sessions}.ts` từ mapping trên. Không đưa Groq/Gemini/Mongo/Qdrant secrets vào NEXT_PUBLIC. Giữ Next/shadcn/Tailwind config, aliases và components hiện hữu; chưa cần thêm dependency. `lib/api/client.ts` triển khai ở F1-02, parser ở F1-03.
- Baseline repairs cần phạm vi riêng: hai page.tsx cần default component hợp lệ, use-mobile cần xử lý lint phù hợp, Python venv cần interpreter tương thích. Không xóa route scaffold hoặc ignore type/lint errors để làm giả PASS; F0 không sửa những file này.
- Chốt riêng giới hạn history citations và progress/file APIs trước các task F5/F6; contract đã có đủ cho foundations, các thiếu hụt không được tự mở rộng backend. `CURRENT_CHANGE` phần trạng thái trước audit còn P5-04 trong khi entry mới nhất/PROJECT_LOG_V2 là M-06 completed; đã cập nhật trạng thái chung theo evidence tài liệu, không rerun hoặc sửa backend roadmap.
- **F1-01 NOT STARTED. Dừng sau F0-01.**

## 9. Evidence F1-STAB — Baseline Stabilization (2026-10-13)

- **COMPLETED:** Frontend build, typecheck sau build và lint đều PASS. Task bổ sung stabilization tách biệt F1-01; F0-01 vẫn COMPLETED, mục 8 là snapshot lịch sử trước sửa.
- **Frontend:** `app/chat/[sessionId]/page.tsx` và `app/documents/page.tsx` có default-export Server Components tối thiểu, chỉ heading và thông báo đang chuẩn bị. Không request backend, không composer/list/upload UI. `hooks/use-mobile.ts` bỏ setState đồng bộ trong effect; `useSyncExternalStore` đọc `matchMedia('(max-width: 767px)')`, subscribe/unsubscribe change listener với callbacks ổn định; server/hydration snapshot false, browser snapshot phản ánh breakpoint hiện tại. Giữ nguyên 14 shadcn components, Next/Tailwind config, dependency manifests và ESLint rules.
- **Backend evidence trước khôi phục:** `.venv/pyvenv.cfg` chỉ rõ CPython 3.10.11; README và changelog xác nhận cùng phiên bản. Launcher hiện có lỗi vì home Python310 mất; không có interpreter/py/uv/conda dùng được trong PATH kiểm tra. `backend/requirements.txt` có 18 requirements, site-packages hiện có metadata/dependencies nên không recreate venv hoặc pip install/update.
- **Khôi phục local environment:** Tải archive CPython 3.10.11 Windows AMD64 chính thức từ `https://www.python.org/ftp/python/3.10.11/python-3.10.11-embed-amd64.zip` sau network approval. Giải nén vào `.venv/runtime/python310`; đổi tên `python310._pth` thành `python310._pth.disabled` để interpreter dùng cơ chế site/venv thông thường. Giữ bản gốc `.venv/pyvenv.cfg.baseline-backup`, chỉ đổi home thành `D:\Project\rag-demo\.venv\runtime\python310`. Launcher `.venv/Scripts/python.exe` chạy đúng 3.10.11 64-bit, sys.prefix là `.venv`, base_prefix là runtime mới, SSL import được. Các file này nằm trong `.venv/` đã gitignore; không cài Python hệ thống, không sửa secrets, requirements hoặc backend source. Khôi phục này dành cho workspace hiện tại; khi chuyển máy/đường dẫn phải cấu hình lại home. Rollback dùng bản cfg backup (sẽ trở lại home cũ đang thiếu interpreter).

| Kiểm tra đã chạy | Kết quả | Evidence |
| --- | --- | --- |
| `npm.cmd run build` (frontend) | PASS, exit 0 | Compile, TypeScript, prerender 6/6 và finalize; có `/`, `/documents`, `/chat/[sessionId]`. |
| `node node_modules/typescript/bin/tsc --noEmit --incremental false` (frontend, sau build) | PASS, exit 0 | Bao gồm generated Next route validators, không diagnostic. |
| `npm.cmd run lint` (frontend) | PASS, exit 0 | Không lỗi/warning; không đổi config hoặc disable rule. |
| Node inline hook verification, transpile bằng TypeScript đã cài | PASS | React server render không có window trả false; mocked media snapshots desktop/mobile, notifications hai chiều và listener cleanup. Kiểm tra có giới hạn: không thay thế browser interaction E2E. Không thêm test dependency. |
| `.venv/Scripts/python.exe` version/prefix/SSL | PASS | CPython 3.10.11 AMD64, đúng venv/base runtime/site-packages. |
| `.venv/Scripts/python.exe -m pip check` | PASS | No broken requirements found; không thay đổi package. |
| Inline importlib.metadata + packaging kiểm tra `backend/requirements.txt` | PASS 18/18 | Tất cả versions thực cài thỏa constraints; requirements không có lock exact, giữ nguyên các package ngoài requirements đang tồn tại. |
| Inline import `app.main` + `app.openapi()` với socket connect/connect_ex/create_connection bị chặn | PASS | 11 paths, 32 schemas; xác nhận chat/stream/session/upload routes. Không chạy lifespan, cloud readiness hoặc generation. |
| `git diff --check` | PASS | Không whitespace errors. |
| Browser E2E, backend full tests, cloud/provider smoke | NOT RUN | Ngoài scope stabilization; Groq=0, Gemini=0. |

**Files task:** hai page.tsx, use-mobile.ts, FRONTEND_PLAN.md, CURRENT_CHANGE.md; archive hai entry cũ sang `docs/changelog/phase-03-04.md` để nhật ký giữ 15 entry theo quy tắc, không xóa lịch sử. Local ignored environment: `.venv/pyvenv.cfg`, backup và runtime archive/interpreter. **Blocker stabilization:** không còn. API base URL/CORS/types/client và giới hạn history/citations/progress của audit vẫn chờ task tương ứng, chưa triển khai. **F1-01 NOT STARTED; dừng sau F1-STAB.**

## 10. Evidence F1-01 — API Contract & TypeScript Types (2026-10-13)

**COMPLETED theo phạm vi task được giao.** Chỉ điền bốn `frontend/types/*.ts` hiện hữu và thêm kiểm tra contract không cần dependency mới. Không sửa backend business logic/config, shadcn components, UI, manifests hoặc local environment; `lib/api/*.ts` và `lib/sse/parser.ts` vẫn 0 byte. Giữ các thay đổi F1-STAB có sẵn trong working tree. Environment/base URL/CORS/env example chưa triển khai trong task types này.

### 10.1. Nguồn và quy ước DTO

- Offline import `app.main`, `app.openapi()` với socket connect/connect_ex/create_connection bị chặn, không lifespan: 11 paths, 32 REST schemas. Đối chiếu `api/{chat,sessions,documents}.py`, `schemas.py`, `conversation_schemas.py`, enum models, `sse_schema.py`, `main.py` và `cloud_connections.py`.
- `api.ts`: UUID/date-time wire strings (không brand hoặc Date object), pagination query/envelope, HealthResponse/ConnectionStatus/DependencyHealthResponse, ValidationError/HTTPValidationError/HTTPErrorResponse và union các known error bodies. Không có UI-only loading/draft/abort state. Error bodies chưa được normalize hoặc gắn HTTP status bởi client.
- `sessions.ts`: CreateSessionRequest/UpdateSessionTitleRequest, scope/session/page DTOs, role/status enums, MessageResponse/MessagePageResponse, CitationResponse/UsageResponse và DeleteSessionResponse. `chat.ts`: request/response/metadata/status/mode/source/citation/usage/error và 6 SSE data/event types; SSEEvent union dùng `event` làm discriminator, bao gồm citation theo schema dù runtime chưa emit.
- `document.ts`: DocumentStatus, info/detail/version/index/delete, list query/array response và multipart DocumentUploadRequest `{file: File}`. OpenAPI FastAPI hiện dùng string + contentMediaType=application/octet-stream cho file, browser dùng File qua multipart, không JSON string. `job_id` là field của synchronous result, không tạo type cho job polling/progress API chưa có.
- REST optionality khớp **required list của OpenAPI**: defaulted fields là optional (ví dụ `Citation.page?: number|null`, `ChatError.retryable?: boolean`, `DocumentInfo.active_version_id?: string|null`, delete policy/status fields optional). Required nullable giữ bắt buộc (`MessageResponse.model/usage/completed_at`, mọi top-level ChatResponse, SessionResponse.user_id). Serializer hiện emit defaults nhưng DTO không giả định field mà OpenAPI cho phép bỏ qua luôn có. CreateSessionRequest.title và ChatRequest.session_id optional nullable; query pagination optional nhưng không nullable.
- SSE envelope là biểu diễn của **wire event: line + JSON data:**, không phải JSON object được gửi trực tiếp. `event` bắt buộc để discriminate; `done.status` bắt buộc COMPLETED vì encoder hiện serialize default. Các nullables/usage/sequence theo Pydantic. Test ghi rõ hai khác biệt này so với required list của Pydantic input schema. Integer bounds, UUID/date-time formats, nonblank strings, usage totals, source provenance, sequence/ordering và mode/ID correlations vẫn do backend/runtime validation kiểm tra; TypeScript thuần không xác thực JSON nhận từ mạng.

### 10.2. REST mapping đã đối chiếu

| Routes | Request/query → response DTO | Semantics/status từ source |
| --- | --- | --- |
| GET `/health`, GET `/health/dependencies` | Không body → HealthResponse / DependencyHealthResponse | Health 200; dependencies 200 hoặc 503. Dependencies keys mongodb/qdrant, service/ok/code/message. OpenAPI health chỉ string map, readiness thiếu payload schema; DTO dựa source và deterministic handler fixtures. |
| POST `/sessions` | CreateSessionRequest (JSON body bắt buộc, `{}` hợp lệ) → SessionResponse | 201; default scope ALL_ACTIVE, không API đổi scope. |
| GET `/sessions`; GET `/sessions/{session_id}`; PATCH `/sessions/{session_id}` | ListSessionsQuery; UUID path; UpdateSessionTitleRequest → SessionPageResponse / SessionResponse | List offset=0/limit=50, max=200; details/title 200. |
| GET `/sessions/{session_id}/messages`; DELETE `/sessions/{session_id}` | UUID path, ListMessagesQuery cho GET → MessagePageResponse / DeleteSessionResponse | History offset=0/limit=100, max=500, sequence-order; DELETE soft-delete session/hard-delete messages, tombstone, idempotent. Session handlers có 404/410/409/503; validation 422. |
| POST `/chat`; POST `/chat/stream` | ChatRequest → ChatResponse / SSEEvent wire stream | Stateless khi omit/null session_id; persistent cần ID có thật. JSON generation failure 502 có thể full ChatResponse; pre-reply/pre-header session/dependency errors dùng detail. SSE sau headers terminal error thay done, không đổi HTTP status. Không định nghĩa HTTP 429 như status đảm bảo của provider path; handler normalize provider lỗi. |
| GET `/documents`; GET `/documents/{document_id}` | ListDocumentsQuery; UUID path → DocumentListResponse (array) / DocumentDetail | include_deleted=false, offset=0/limit=100, max=500; không total/status filter/download route. |
| POST `/documents/upload`; PUT `/documents/{document_id}`; POST `/documents/{document_id}/re-index` | Multipart DocumentUploadRequest cho upload/update; re-index không body → DocumentIndexInfo | 201 sau ingestion sync; num_chunks khác chunk_count của list/version. Candidate fail không thay active version cũ. |
| DELETE `/documents/{document_id}` | UUID path → DeleteDocumentResponse | 200 hoặc 202 cleanup pending, giữ raw files, retrieval_eligible=false; document handlers có 400/404/409/500/503, validation 422. |

### 10.3. Contract gaps được giữ rõ

- **Citation history:** MessageResponse chỉ có citations, không sources/ordinal/source-position mapping; CitationResponse cũng không có ordinal. Không thể map `[n]` theo vị trí citations array hoặc bảo đảm inline citation parity sau refresh. DTO history không thêm field sources giả. Source thứ n của live metadata/JSON reply khác chunk_index. PDF page zero-based, nullable/absent cho loader khác.
- **SSE:** Typed schema hỗ trợ citation event trước delta, runtime hiện không phát realtime citation; client tương lai phải chấp nhận transcript không có citation. Cancel/disconnect không có terminal frame tới client đã rời kết nối; durable state best-effort. Chưa có parser/runtime JSON validation trong task này.
- **OpenAPI không đầy đủ:** SSE 200 khai báo string text/event-stream chứ không event schemas; health/readiness thiếu chi tiết; dynamic DELETE document 202 và các HTTPException statuses trong source không liệt kê đầy đủ trong responses. Generation 502 có thể ChatResponse hoặc detail tùy giai đoạn lỗi; validation detail array khác HTTPException detail string. ApiErrorResponse chỉ các known JSON shapes, không đảm bảo network/proxy failures có JSON và không thay safe parsing của F1-02.
- **Documents/sessions:** Không có job polling/progress, max-size contract, raw-file preview/download hoặc scope mutation endpoint; thiếu auth/multi-tenant. Không thêm endpoint/type giả để lấp gap.

### 10.4. Verification

| Lệnh (frontend/) | Kết quả |
| --- | --- |
| `node tests/verify-api-contract.mjs` | PASS — 45 REST/SSE/health schemas, bidirectional structural assignability và property keys; queries, multipart upload/update, document array, SSE discriminator/narrowing/exhaustiveness, required/optional nullable, absence of history sources. Negative compile fixtures bắt missing question/model, sai done status và event/payload mismatch. Health/dependencies handler fixtures PASS cho 200/503 với threadpool/cloud stub, network blocked; không lifespan. |
| `node node_modules/typescript/bin/tsc --noEmit --incremental false` | PASS sau build, exit 0. |
| `npm.cmd run build` | PASS, exit 0; compile/typecheck/prerender 6/6/finalize. |
| `npm.cmd run lint` | PASS, exit 0; không disable rule. |
| `git diff --check` (root) | PASS. |
| Browser E2E/provider/cloud smoke | NOT RUN — chưa có client/UI; Groq=0, Gemini=0. |

Test tự lấy OpenAPI và Pydantic SSE schemas từ interpreter hiện có, sinh expected TS trong virtual compiler file (không ghi generated types hoặc OpenAPI snapshot vào repo), dùng TypeScript đã cài; chạy lại bằng lệnh trên. Không cài test library. Files changed: `frontend/types/{api,chat,document,sessions}.ts`, `frontend/tests/verify-api-contract.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md và archive nhật ký phase-03-04 (chuyển entry cũ nguyên vẹn để giữ 15 entry). **Blocker:** không có cho F1-01. **F1-02 NOT STARTED; dừng sau F1-01.**

## 11. Evidence F1-02 — API client/errors (2026-10-13)

**COMPLETED.** `frontend/lib/api/client.ts` cung cấp `createApiClient({baseUrl, timeoutMs?, fetch?})` và `request<T>(path, options?)`. baseUrl HTTP(S) được truyền rõ ràng, không mặc định env/port hay tự thêm endpoint. Path/query nối với base path, không nhận URL khác thay cho route. Có thể inject fake fetch; default dùng global fetch tại lúc request.

- Options hỗ trợ RequestInit/headers/method, JSON body hoặc BodyInit (FormData), signal và timeout. Không cho json/body cùng lúc. JSON tự set Content-Type; multipart để fetch sinh boundary. Mặc định Accept application/json và cache no-store; caller có thể override cache. Không retry tự động, không auth orchestration, không domain hooks/client methods hoặc SSE parser/UI.
- Return `ApiResponse<T> = {data: T|undefined, status, headers}` giữ nguyên 201/202 và các success status; 204/205 hoặc zero-length body trả undefined, JSON null giữ null. JSON decode lỗi trên 2xx là invalid_response, không giả định success DTO đã runtime-validated. Generic T là compile-time annotation; safe validation DTO đầy đủ chưa triển khai trong wrapper này.
- `ApiClientError` là client state tách API DTO: kind http/network/timeout/aborted/invalid_response, status nullable, message generic an toàn, code nullable và retryable. HTTP failures giữ status kể cả HTML/malformed/empty body và body-read failure sau headers. FastAPI detail string/validation array không đưa raw detail/input/ctx vào error; ChatResponse error chỉ lấy code có định dạng cho phép và retryable boolean, không lưu answer/provider message/body/cause. Không suy ra tự retry chỉ từ HTTP status.
- Timeout default 30s, per-request override (0 tắt) bao gồm fetch và body read. Caller abort/pre-abort được phân biệt với timeout; clear timer và remove listener trong finally. Caller cần timeout lớn hơn cho ingestion đồng bộ khi triển khai document client sau này; hiện chưa gọi ingestion. Configuration/path/JSON serialization errors được báo như lỗi lập trình trước network, không đổi thành network error.
- Không sửa types/backend/config/components/manifests; `lib/api/{chat,sessions,documents}.ts` và `lib/sse/parser.ts` vẫn rỗng. Giữ các thay đổi task trước trong working tree. Không thêm dependency.

Ví dụ dùng DTO đã có (chưa tích hợp vào UI):

```ts
import { createApiClient } from "@/lib/api/client";
import type { HealthResponse } from "@/types/api";

const api = createApiClient({ baseUrl: "http://127.0.0.1:8000" });
const { data, status } = await api.request<HealthResponse>("/health");
```

| Kiểm tra (frontend/) | Kết quả |
| --- | --- |
| `node --test tests/api-client.test.mjs` | PASS 20/20: 2xx/201/202/204/null, JSON/headers/cache, multipart boundary, 400/404/409/410/422/429/500/502/503, malformed/HTML/empty errors, invalid success JSON, network/body failure, pre-abort/cancel/timeout/body deadline, cleanup và base path/query/config. Tất cả dùng fake fetch; 0 external calls. |
| `npm.cmd run build` | PASS, exit 0; compile/typecheck/prerender 6/6/finalize. |
| `node node_modules/typescript/bin/tsc --noEmit --incremental false` | PASS sau build, exit 0. |
| `npm.cmd run lint` | PASS, exit 0. |
| `git diff --check` (root), whitespace check new test/archive files | PASS. |
| Manual Node smoke dùng actual client: GET `http://127.0.0.1:8000/health`, timeout 3s | PASS — một request, HTTP 200, status=ok và llm_model string. Không in model/body; không khởi động backend hoặc gọi dependencies/chat/documents. |
| Browser CORS/connectivity, UI E2E, cloud readiness/provider smoke | NOT RUN. Không có env/CORS configuration từ task này; Node health PASS không thay browser gate. Groq=0, Gemini=0. |

Files changed: `frontend/lib/api/client.ts`, `frontend/tests/api-client.test.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md, archive `docs/changelog/phase-03-04.md` (entry cũ giữ nguyên, nhật ký 15 entry). **Blocker F1-02:** không có. **F1-03 NOT STARTED; dừng sau F1-02.**

## 12. Evidence F1-03 — SSE parser foundation (2026-10-13)

**COMPLETED.** `frontend/lib/sse/parser.ts` là parser transport thuần, không fetch, React state, retry, session lifecycle hoặc UI. `SSEParser.push(Uint8Array)` nhận arbitrary network chunks; `finish()` flush decoder/event cuối; helper `parseSSE(iterable)` phục vụ fixture/batch. Dùng `TextDecoder('utf-8', {fatal:true})` streaming nên ký tự đa byte bị chia qua chunks vẫn được phục hồi chính xác và invalid/incomplete UTF-8 bị từ chối.

- Line parser xử lý LF, CRLF kể cả CR/LF nằm ở hai chunks, mixed endings, BOM, comment heartbeat, optional single space sau colon, nhiều `data:` lines ghép bằng LF, nhiều events trong một chunk và event cuối không có blank delimiter. `id`, `retry` và extension fields bị bỏ qua vì backend contract không dùng; frame không có data bị bỏ theo SSE semantics. Không coi một `reader.read()` là một event và không thay đổi whitespace của `delta.content`.
- Known event names `start|metadata|citation|delta|done|error` được parse JSON rồi runtime-check theo Pydantic SSE contract: exact top-level event-data fields, sequence safe integer >=1, UUID shapes và stateless/persistent ID invariant, mode/model/source/citation fields, delta non-empty/max 1,000,000 chars, terminal status, usage nonnegative/total invariant và safe error fields. Kết quả `{recognized:true,event:SSEEvent}` giữ discriminated union F1-01.
- Unknown event names không bị giả thành known event: trả `{recognized:false,event,data:unknown}` sau JSON parsing; event field thiếu dùng SSE default `message`. Invalid JSON, UTF-8, known payload contract hoặc push sau finish tạo `SSEParserError` với kind/event an toàn, không giữ raw payload hay original error. Sau parse error parser không tiếp tục sử dụng.
- Parser cố ý chỉ xác minh **một frame**. Nó không ép `start→metadata→citation*→delta*→done|error`, sequence liên tục, terminal duy nhất, done cần delta, error FAILED/PARTIAL theo content, citation thuộc metadata source hoặc duplicate citation. Các rule transcript/state này phụ thuộc toàn request và thuộc F3-01 stream client; F1-03 không reorder/drop/synthesize frames. Không có aggregate frame-size cap vì backend chưa quy định max metadata event; transport resilience/limit cần quyết định ở F3/F7 thay vì invent contract.
- Không sửa backend/types/API client/config/components/manifests hoặc thêm dependency. `hooks/use-chat-stream.ts` và domain API clients vẫn rỗng; chưa đọc `ReadableStream`, chưa abort request hoặc tích hợp Chat UI. Runtime backend hiện không emit citation realtime dù schema/parser hỗ trợ.

| Kiểm tra (frontend/) | Kết quả |
| --- | --- |
| `node --test tests/sse-parser.test.mjs` | PASS 18/18: backend LF transcript, Python `encode_sse_event` fixture với network bị chặn, mọi two-chunk byte split, one-byte chunks, exact Unicode/whitespace, split CRLF/mixed endings, multi-event/multiline data, BOM/comment/ignored fields, unknown/default event, EOF, all known variants, safe errors và contract invariants. |
| `node --test tests/api-client.test.mjs tests/sse-parser.test.mjs` | PASS 38/38 regression; không external calls. |
| `node tests/verify-api-contract.mjs` | PASS 45 REST/SSE/health schemas; network blocked. |
| `npm.cmd run build` | PASS, exit 0; compile/typecheck/prerender 6/6/finalize. |
| `node node_modules/typescript/bin/tsc --noEmit --incremental false` | PASS sau build, exit 0. |
| `npm.cmd run lint` | PASS, exit 0. |
| `git diff --check` và new-file whitespace checks | PASS. |
| Live `/chat/stream`, browser/UI E2E, provider/cloud smoke | NOT RUN — ngoài F1-03; Groq=0, Gemini=0. |

Files changed: `frontend/lib/sse/parser.ts`, `frontend/tests/sse-parser.test.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md và archive `docs/changelog/phase-03-04.md` (entry cũ giữ nguyên, nhật ký 15 entry). **Blocker F1-03:** không có. **F2-01 NOT STARTED; dừng sau F1-03.**

## 13. Evidence F2-01 — Application shell (2026-10-13)

**COMPLETED.** Root layout dùng application shell chung với shadcn `SidebarProvider`, `Sidebar`, `SidebarInset`, menu và trigger đã có sẵn; không cài hoặc sinh lại component/dependency. Desktop có sidebar thu gọn và phím Ctrl/Cmd+B; breakpoint mobile dùng `Sheet` do component hiện hữu cung cấp, trigger luôn nằm trong header và menu tự đóng khi chọn route. Header sticky, content co giãn với `min-w-0`, padding responsive và mỗi route có vùng nội dung giới hạn chiều rộng.

- Thêm App Router route `/chat`, giữ `/chat/[sessionId]`, giữ `/documents`; `/` redirect 307 sang `/chat`. Sidebar dùng `next/link`, active state theo `usePathname`, `aria-current="page"`; hai phần đọc URL nằm dưới `Suspense` nhỏ để tương thích Next 16 `cacheComponents` và partial prerender route động.
- Keyboard/accessibility: có skip link tới một `main#main-content`, `nav` có accessible name, heading/section liên kết bằng `aria-labelledby`, trigger có nhãn tiếng Việt, focus-visible styles từ shadcn và icon trang trí `aria-hidden`. Root metadata và `lang="vi"` thay scaffold mặc định.
- `/chat` và `/documents` chỉ là placeholder shell-level. Không tạo composer, message bubble, session list, upload/list/detail document, API hook, SSE transport hoặc backend mutation; F2-02/F2-03 và các phase tích hợp chưa bắt đầu.
- Không sửa component shadcn hiện có, manifests, API/SSE code hoặc backend; live Groq/Gemini calls = 0.

| Kiểm tra (frontend/) | Kết quả |
| --- | --- |
| `npm.cmd run build` | PASS, exit 0; `/`, `/chat`, `/documents` static và `/chat/[sessionId]` partial-prerender. Lần đầu FAIL có ghi nhận do `usePathname` ngoài Suspense; đã sửa đúng hướng dẫn Next 16 và rerun PASS. |
| `npm.cmd exec tsc -- --noEmit` | PASS, exit 0. |
| `npm.cmd run lint` | PASS, exit 0. |
| `node --test tests/api-client.test.mjs tests/sse-parser.test.mjs` | PASS 38/38 regression; không external calls. |
| `node tests/verify-api-contract.mjs` | PASS 45 schemas; network disabled. |
| Dev HTTP route smoke | PASS: `/` 307 → `/chat`; `/chat`, `/documents`, `/chat/demo-session` HTTP 200. Rendered HTML có `lang=vi`, skip link, named nav, `main#main-content`, active `aria-current` và route heading. |
| Browser desktop/mobile/keyboard interaction | BLOCKED/NOT RUN: Browser plugin Node REPL lỗi khởi tạo môi trường `The system cannot find the path specified` ngay cả với lệnh tối thiểu; không đánh dấu PASS. Responsive behavior được cung cấp bởi shadcn Sidebar/Sheet source đã audit, nhưng viewport/click/tab visual QA vẫn cần rerun khi công cụ hoạt động. |
| `git diff --check` | PASS. |

Files changed: `frontend/components/layout/app-shell.tsx`, `frontend/app/layout.tsx`, `frontend/app/page.tsx`, `frontend/app/chat/page.tsx`, `frontend/app/chat/[sessionId]/page.tsx`, `frontend/app/documents/page.tsx`, FRONTEND_PLAN.md, CURRENT_CHANGE.md và archive `docs/changelog/phase-03-04.md`. **Blocker F2-01 implementation:** không có. **F2-02 NOT STARTED; dừng sau F2-01.**

## 14. Evidence F2-02 — Chat static components (2026-10-13)

**COMPLETED.** `/chat` và `/chat/[sessionId]` dùng chung `ChatPreview`, chỉ đọc fixture cục bộ. Preview có bốn trạng thái chuyển bằng nhóm button có `aria-pressed`: hội thoại, trống, đang tải và lỗi. Không fetch, không import API client/SSE parser, không dùng session hook và không gọi backend/provider.

- Hội thoại mẫu tách `ChatMessage` với bubble user/assistant, avatar/icon và accessible label. Assistant content render Markdown/GFM bằng `react-markdown` + `remark-gfm` đã có sẵn; mapping paragraph/list/blockquote/code/pre/link cung cấp style cơ bản mà không thêm plugin/dependency.
- `ChatComposer` là client boundary nhỏ: textarea có label/help text, nhận nhập liệu local DOM, form chặn submit và nút gửi luôn disabled. Loading fixture disable textarea; error retry cũng disabled. UI ghi rõ đây là bản xem trước chưa kết nối API.
- Empty/loading/error fixtures có heading/copy riêng; loading dùng `aria-busy` và Skeleton hiện có, error dùng `role=alert`. Chat surface responsive, có vùng cuộn riêng và composer cố định ở đáy panel.
- Fixture type nằm riêng trong `frontend/fixtures/chat.ts`, không trộn với API DTO. Không sửa contract, API/SSE libraries, shadcn components, manifests hoặc backend; live Groq/Gemini calls = 0.

| Kiểm tra (frontend/) | Kết quả |
| --- | --- |
| `npm.cmd run build` | PASS, exit 0; `/chat` static và `/chat/[sessionId]` partial-prerender. |
| `npm.cmd exec tsc -- --noEmit` | PASS, exit 0. |
| `npm.cmd run lint` | PASS, exit 0. |
| `node --test tests/api-client.test.mjs tests/sse-parser.test.mjs` | PASS 38/38 regression; không external calls. |
| `node tests/verify-api-contract.mjs` | PASS 45 schemas; network disabled. |
| Dev HTTP rendered-content smoke | PASS: `/chat` và `/chat/demo-session` HTTP 200; default fixture render badge, user/assistant accessible labels, Markdown ordered list, composer, disabled submit và state-selector group. |
| Browser state switching/responsive interaction | BLOCKED/NOT RUN: Browser plugin Node REPL vẫn lỗi khởi tạo path trước khi chạy browser code; không đánh dấu PASS. Static state implementations được typecheck/lint/build nhưng click/visual QA cần rerun khi công cụ hoạt động. |
| `git diff --check` và whitespace checks cho file mới | PASS. |

Files changed cho F2-02: `frontend/fixtures/chat.ts`, `frontend/components/chat/{chat-message,chat-composer,chat-preview}.tsx`, `frontend/app/chat/page.tsx`, `frontend/app/chat/[sessionId]/page.tsx`, FRONTEND_PLAN.md, CURRENT_CHANGE.md và archive `docs/changelog/phase-01.md`. **Blocker F2-02 implementation:** không có. **F2-03 NOT STARTED; dừng sau F2-02.**

## 15. Evidence F2-03 — Documents static components (2026-10-13)

**COMPLETED.** `/documents` dùng `DocumentsPreview` với ba `DocumentDetail` fixtures typed trực tiếp theo contract F1-01. Responsive master/detail layout xếp một cột dưới `lg`, hai cột từ `lg`; danh sách là các button chọn local có `aria-pressed`, detail cập nhật client-side mà không fetch hay mutate backend.

- List hiển thị file name, `DocumentStatus`, active `chunk_count` và `version_count`. Detail tách `active_version_id`, thời gian cập nhật, trạng thái retrieval, các version bất biến, size, chunk count, indexed timestamp và version ID; không nhầm `num_chunks` response ingestion với `chunk_count` list/version.
- `DocumentStatusBadge` hỗ trợ đủ `UPLOADED|PROCESSING|INDEXED|FAILED|DELETED`. Fixture thể hiện indexed, processing và failed; processing copy ghi rõ backend đồng bộ và không có polling API, failed không tự bịa raw error.
- Dialog upload/create-version dùng file accept đúng `.pdf/.md/.markdown/.txt/.xlsx`, không invent max size; file input không được đọc/gửi và CTA mutation disabled. Re-index disabled. Delete confirmation mô tả đúng soft-delete/unpublish, Qdrant cleanup có thể pending và raw/audit retention; nút xác nhận disabled.
- Không tạo progress percentage, polling/download route, status filter hoặc total envelope chưa có trong contract. Không sửa API client/types, shadcn components, manifests hoặc backend; live Groq/Gemini calls = 0.

| Kiểm tra (frontend/) | Kết quả |
| --- | --- |
| `npm.cmd run build` | PASS, exit 0; `/documents` static. |
| `npm.cmd exec tsc -- --noEmit` | PASS, exit 0; fixtures satisfy `DocumentDetail[]`. |
| `npm.cmd run lint` | PASS, exit 0, 0 warnings sau khi tách `role=listitem` khỏi toggle button. |
| `node --test tests/api-client.test.mjs tests/sse-parser.test.mjs` | PASS 38/38 regression; không external calls. |
| `node tests/verify-api-contract.mjs` | PASS 45 schemas; network disabled. |
| Dev HTTP rendered-content smoke | PASS: `/documents` HTTP 200; fixture badge, document list/selected item, indexed status, detail, active version, version history, upload/new-version/delete triggers và disabled re-index đều render. |
| Browser list/dialog/responsive interaction | BLOCKED/NOT RUN: Browser plugin Node REPL vẫn lỗi khởi tạo path trước browser code; không đánh dấu PASS. Local interaction source được typecheck/lint/build nhưng click/dialog/viewport visual QA cần rerun khi công cụ hoạt động. |
| `git diff --check` và whitespace checks cho file mới | PASS. |

Files changed cho F2-03: `frontend/fixtures/documents.ts`, `frontend/components/documents/{document-status-badge,document-dialogs,documents-preview}.tsx`, `frontend/app/documents/page.tsx`, FRONTEND_PLAN.md, CURRENT_CHANGE.md và archive `docs/changelog/phase-01.md`. **Blocker F2-03 implementation:** không có. **F3-01 NOT STARTED; dừng sau F2-03.**

## 16. Evidence F3-01 — Stream client (2026-10-13)

**COMPLETED.** `createChatStreamClient({baseUrl, fetch?}).stream(payload, {signal?, onEvent?})` POST JSON tới `/chat/stream` với `Accept: text/event-stream`, đọc `Response.body.getReader()` và đưa từng byte chunk qua `SSEParser` F1-03. Callback chỉ nhận logical event hoàn chỉnh sau parse/validation; một `reader.read()` có thể chứa một phần, một hoặc nhiều event và không được dùng làm event boundary.

- `ChatStreamResult` giữ toàn bộ typed events theo wire order cùng `sequence`, `start` chứa request/session/user-message/assistant-message IDs và mode, metadata/citations/deltas, terminal, exact delta concatenation và terminal usage nullable. Delta được coi là arbitrary content fragment; không đếm như token hoặc từ và không trim/normalize whitespace.
- Incremental transcript validator mirror `SSETranscript`: sequence liên tục từ 1, đúng một start đầu tiên, tối đa một metadata, metadata trước citation/delta/done, citation trước delta và tham chiếu source thật/không trùng, terminal duy nhất/cuối cùng, done cần content delta, error `FAILED` nếu chưa delta và `PARTIAL` nếu đã có delta. Unknown/malformed/frame-contract event bị từ chối; premature EOF là `incomplete`.
- `ChatStreamClientError` phân biệt `stage=before_response` cho HTTP khác 200, network và pre-abort; `stage=stream` cho invalid content-type/body, reader transport, post-200 abort, parser/protocol/incomplete và consumer callback. Error không giữ raw response/event/question. SSE `error` hợp lệ là terminal result với safe code/status/usage, không bị đổi thành transport exception.
- Client không retry request đã gửi, không đặt stream timeout hay nối UI state. AbortController lifecycle/recovery UX thuộc F3-03; browser base URL/CORS và UI consumption thuộc task sau. Không sửa backend/parser/types/components/manifests và không thêm dependency.

| Kiểm tra (frontend/) | Kết quả |
| --- | --- |
| `node --test tests/chat-stream-client.test.mjs` | PASS 12/12: POST headers/body; one-byte chunks; arbitrary chunk/event boundaries; exact multi-delta whitespace; persistent/stateless IDs; usage; FAILED/PARTIAL terminal; HTTP/network/abort stages; invalid 200; reader failure; malformed/unknown/contract/order/sequence/terminal/citation errors; consumer failure/base URL. Mock fetch/ReadableStream only. |
| `node --test tests/chat-stream-client.test.mjs tests/sse-parser.test.mjs tests/api-client.test.mjs` | PASS 50/50 combined regression; không external calls. |
| `node tests/verify-api-contract.mjs` | PASS 45 REST/SSE/health schemas; network disabled. |
| `npm.cmd exec tsc -- --noEmit` | PASS, exit 0. |
| `npm.cmd run lint` | PASS, exit 0. |
| `npm.cmd run build` | PASS, exit 0; compile/typecheck/prerender/finalize. |
| Live `/chat/stream`, browser CORS, UI E2E, provider/cloud smoke | NOT RUN — ngoài F3-01; Groq=0, Gemini=0. |
| `git diff --check` và new-file whitespace check | PASS. |

Files changed: `frontend/lib/api/chat.ts`, `frontend/tests/chat-stream-client.test.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md và archive `docs/changelog/phase-02.md`. **Blocker F3-01:** không có. **F3-02 NOT STARTED; dừng sau F3-01.**

## 17. Evidence F3-02 — Chat state/UI integration (2026-10-13)

**COMPLETED.** Chat pages thay fixture preview bằng state/UI dùng `ChatController`. `/chat` gọi đúng `POST /sessions` body `{}` trước lượt gửi đầu rồi truyền UUID backend cấp vào stream; `/chat/[sessionId]` tái dùng route ID và không tạo session mới. `NEXT_PUBLIC_API_BASE_URL` được đọc ở server page rồi truyền rõ ràng cho client; khi thiếu cấu hình, UI hiển thị lỗi cấu hình và không phát request.

- Controller tạo user `PENDING` và assistant draft `PENDING`, khóa active turn đồng bộ trước await để chặn submit trùng, rồi kiểm tra persistent `start` khớp session/request/user-message/assistant-message IDs. Metadata/model/sources, citation, usage và terminal status được gắn vào đúng assistant message.
- Mỗi `delta.content` được append trực tiếp, không trim/chèn separator/đếm token. `done` chuyển draft sang `COMPLETED`; SSE error giữ `FAILED|PARTIAL`, safe error và usage. Lỗi trước terminal chuyển thành `FAILED` hoặc `PARTIAL` tùy đã có content và luôn mở khóa composer.
- Composer controlled hỗ trợ Enter gửi, Shift+Enter xuống dòng, disable trong generation và label/help text accessible. Message UI hiển thị trạng thái draft/stream/completed/partial/failed, Markdown hiện có và safe error. Không load history/session list, không đổi URL sau create, không tự retry/cancel/timeout; các phần đó thuộc F3-03/F4.
- Session create client chỉ triển khai route cần cho F3-02, yêu cầu HTTP 201 và runtime-check `SessionResponse`; không thêm dependency hoặc sửa backend. Browser live request còn phụ thuộc API base URL/CORS đã ghi từ audit.

| Kiểm tra (frontend/) | Kết quả |
| --- | --- |
| `node --test tests/chat-controller.test.mjs` | PASS 4/4: create-before-stream, reuse route session, synchronous duplicate guard, exact delta whitespace/COMPLETED, PARTIAL/error, failure unlock và POST `/sessions` 201 contract. Mock services only. |
| `node --test tests/chat-controller.test.mjs tests/chat-stream-client.test.mjs tests/sse-parser.test.mjs tests/api-client.test.mjs` | PASS 54/54 combined regression; không external calls. |
| `node tests/verify-api-contract.mjs` | PASS 45 REST/SSE/health schemas; network disabled. |
| `npm.cmd exec tsc -- --noEmit` | PASS, exit 0. |
| `npm.cmd run lint` | PASS, exit 0. |
| `npm.cmd run build` | PASS, exit 0; `/chat` static và `/chat/[sessionId]` partial prerender. |
| Live browser SSE/CORS/backend/provider smoke | NOT RUN; cần public API base/CORS runtime. Groq=0, Gemini=0. |
| `git diff --check` và new-file whitespace check | PASS. |

Files changed: `frontend/lib/api/sessions.ts`, `frontend/lib/chat/controller.ts`, `frontend/components/chat/{chat-composer,chat-message,chat-preview}.tsx`, `frontend/app/chat/{page,[sessionId]/page}.tsx`, `frontend/tests/chat-controller.test.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md và archive `docs/changelog/phase-02.md`. **Blocker F3-02 implementation:** không có. **F3-03 NOT STARTED; dừng sau F3-02.**

## 18. Evidence F3-03 — Cancel/recovery (2026-10-14)

**COMPLETED.** Mỗi accepted turn sở hữu đúng một `AbortController`; cùng signal được truyền qua session creation và `createChatStreamClient.stream`. Stop button gọi `controller.stop()`, còn effect cleanup gọi `controller.dispose()` khi component unmount/navigation. Cả hai idempotent, không abort turn đã terminal và không phát request retry.

- Stop trong lúc generation abort fetch/reader, giữ nguyên mọi delta đã nhận và chốt local assistant `PARTIAL`; stop trước content chốt `FAILED`. Safe local cancellation dùng `RAG_STREAM_CANCELLED`, khớp backend persistence semantics khi disconnect, với `retryable=false`.
- Transport/disconnect không do người dùng giữ mã `CLIENT_STREAM_ERROR`, thành `PARTIAL` khi đã có content hoặc `FAILED` khi chưa có. SSE terminal từ backend tiếp tục giữ nguyên status/error/usage kể cả transport lỗi sau terminal. `finally` luôn xóa active turn và hạ `isGenerating`, nên composer không kẹt loading sau reject/abort.
- Composer đổi send control thành keyboard-accessible Stop control trong lúc generate; textarea giữ disabled để chặn submit trùng. Sau terminal/failure/cancel, lượt gửi mới chỉ bắt đầu khi người dùng chủ động submit; không có automatic retry.
- Backend source xác nhận disconnect finalize persistent turn với `RAG_STREAM_CANCELLED` và `PARTIAL|FAILED` theo content. Không sửa backend, không thêm dependency hoặc timeout policy mới. Browser live cancellation vẫn phụ thuộc API base/CORS runtime.

| Kiểm tra (frontend/) | Kết quả |
| --- | --- |
| `node --test tests/chat-controller.test.mjs` | PASS 8/8: success/terminal, duplicate guard, Stop partial/no retry, dispose during session creation, fake disconnect partial/unlock/no retry, terminal preservation, failure recovery và session contract. |
| `node --test tests/chat-controller.test.mjs tests/chat-stream-client.test.mjs tests/sse-parser.test.mjs tests/api-client.test.mjs` | PASS 58/58 combined regression; không external calls. |
| `node tests/verify-api-contract.mjs` | PASS 45 REST/SSE/health schemas; network disabled. |
| `npm.cmd exec tsc -- --noEmit` | PASS, exit 0. |
| `npm.cmd run lint` | PASS, exit 0. |
| `npm.cmd run build` | PASS, exit 0; `/chat` static và `/chat/[sessionId]` partial prerender. |
| Live browser SSE/cancel/CORS/backend/provider smoke | NOT RUN; cần public API base/CORS runtime. Groq=0, Gemini=0. |
| `git diff --check` và new-file whitespace check | PASS. |

Files changed cho F3-03: `frontend/lib/chat/controller.ts`, `frontend/components/chat/{chat-composer,chat-preview}.tsx`, `frontend/tests/chat-controller.test.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md và archive `docs/changelog/phase-02.md`. **Blocker F3-03 implementation:** không có. **F4-01 NOT STARTED; dừng sau F3-03.**

## 19. Evidence F4-01 — Session list/New Chat (2026-10-14)

**COMPLETED.** Session domain client hỗ trợ đúng phạm vi `GET /sessions?offset=0&limit=50`, `POST /sessions` body `{}` và `GET /sessions/{session_id}`. Success response yêu cầu đúng HTTP 200/201 và được runtime-check theo `SessionResponse`/`SessionPageResponse`; UUID sai bị chặn trước request. Pagination tiếp theo và message history chưa triển khai.

- `useSessions` và `useSession` dùng external-store controllers với immutable snapshot, AbortController cleanup, safe loading/error state và explicit user retry. Strict-mode remount/stale response không ghi đè request mới. Create guard chỉ cho một New Chat request; success thêm session backend trả về lên đầu list và trả ID cho router.
- Application sidebar có New Chat action, loading/empty/error/retry states và tối đa 50 session links theo thứ tự backend `updated_at` giảm dần. Click New Chat POST session rồi điều hướng `/chat/{backend_id}`; click item mở route tương ứng. Không có ô nhập UUID và không tự sinh ID phía frontend.
- `/chat/[sessionId]` kiểm tra định dạng trước network, GET session trước khi dựng Chat UI và dùng canonical ID backend trả về. Invalid ID, 404/410 missing/deleted, network/API error và thiếu base URL có thông báo/action rõ; link quay về `/chat`, lỗi network có retry chủ động.
- Root layout truyền cùng `NEXT_PUBLIC_API_BASE_URL` cho shell/sidebar. Khi thiếu config, session action fail-closed. Không load messages/history, không localStorage, không đổi session title/delete/scope, không sửa backend hoặc thêm dependency.

| Kiểm tra (frontend/) | Kết quả |
| --- | --- |
| `node --test tests/sessions.test.mjs` | PASS 7/7: exact list/create/get routes, response guards, invalid ID no request, ordered list, single create, safe errors, mock open, 404/410 và retry recovery. |
| `node --test tests/sessions.test.mjs tests/chat-controller.test.mjs tests/chat-stream-client.test.mjs tests/sse-parser.test.mjs tests/api-client.test.mjs` | PASS 65/65 combined regression; không external calls. |
| `node tests/verify-api-contract.mjs` | PASS 45 REST/SSE/health schemas; network disabled. |
| `npm.cmd exec tsc -- --noEmit` | PASS, exit 0. |
| `npm.cmd run lint` | PASS, exit 0. |
| `npm.cmd run build` | PASS, exit 0; `/chat` static và `/chat/[sessionId]` partial prerender. |
| Live browser session/CORS/backend/provider smoke | NOT RUN; cần public API base/CORS runtime. Groq=0, Gemini=0. |
| `git diff --check` và new-file whitespace check | PASS. |

Files changed: `frontend/lib/api/sessions.ts`, `frontend/lib/sessions/controller.ts`, `frontend/hooks/use-sessions.ts`, `frontend/components/layout/{app-shell,session-navigation}.tsx`, `frontend/components/chat/session-chat.tsx`, `frontend/app/{layout,chat/[sessionId]/page}.tsx`, `frontend/tests/sessions.test.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md và archive `docs/changelog/phase-02.md`. **Blocker F4-01 implementation:** không có. **F4-02 NOT STARTED; dừng sau F4-01.**

## 20. Evidence F4-02 — History/pagination (2026-10-14)

**COMPLETED.** Session message client gọi đúng `GET /sessions/{session_id}/messages?offset={offset}&limit={limit}`, yêu cầu HTTP 200 và runtime-check toàn bộ `MessagePageResponse`/`MessageResponse`. Query bị giới hạn theo backend (`offset >= 0`, `1 <= limit <= 500`); response phải phản ánh đúng offset/limit, không vượt page size và mọi message phải thuộc session đang mở.

- `HistoryController` tự tải tuần tự các page 100 message cho tới `total`, yêu cầu offset liên tục, page không rỗng trước khi đủ total, tổng item đúng `total`, không trùng `message_id` hoặc `sequence`; kết quả được sắp ổn định theo `(sequence, message_id)`. Bất kỳ page lỗi/mixed-session nào đều trả error và danh sách rỗng, không lộ partial history.
- Mỗi `/chat/[sessionId]` xác minh session rồi tải đủ history trước khi dựng `ChatPreview`; retry gọi lại backend và thay snapshot cũ. Hai controller giữ state/AbortController riêng, nên response của session này không đi vào session khác. Không đọc/ghi `localStorage`; refresh phục hồi từ REST API.
- History DTO được đổi sang UI message với content/status/model/citations/usage/request/message IDs nguyên vẹn. Contract history không chứa `sources`, nên frontend không tự dựng source metadata hoặc citation ordinal; giới hạn refresh citation này được giữ cho F5.
- `ChatController` nhận initial history. Khi gửi lượt đầu từ `/chat`, sau khi backend tạo session và stream kết thúc, route dùng `router.replace('/chat/{session_id}')`; URL phản ánh session hiện tại và dynamic route tải lại canonical history từ backend. Navigation chỉ diễn ra sau terminal để không abort stream đang chạy.
- Không triển khai switching/multi-turn leak validation của F4-03, không sửa backend, không thêm dependency và không gọi API/provider thật.

| Kiểm tra (frontend/) | Kết quả |
| --- | --- |
| `node --test tests/sessions.test.mjs` | PASS 13/13: exact pagination route/query/guards, multi-page offsets/order, hai session tách biệt, mixed-page fail closed, refresh thay state từ API và DTO mapping không tự dựng sources. Mock API only. |
| `node --test tests/sessions.test.mjs tests/chat-controller.test.mjs tests/chat-stream-client.test.mjs tests/sse-parser.test.mjs tests/api-client.test.mjs` | PASS 71/71 combined regression; không external calls. |
| `node tests/verify-api-contract.mjs` | PASS 45 REST/SSE/health schemas; network disabled. |
| `npm.cmd exec tsc -- --noEmit` | PASS, exit 0. |
| `npm.cmd run lint` | PASS, exit 0. |
| `npm.cmd run build` | PASS, exit 0; `/chat` static và `/chat/[sessionId]` partial prerender. |
| Live browser refresh/navigation/CORS/backend/provider smoke | NOT RUN; cần public API base/CORS runtime. Groq=0, Gemini=0. |
| `git diff --check` và new-file whitespace check | PASS. |

Files changed cho F4-02: `frontend/lib/api/sessions.ts`, `frontend/lib/sessions/history.ts`, `frontend/hooks/use-sessions.ts`, `frontend/lib/chat/controller.ts`, `frontend/components/chat/{chat-preview,session-chat,chat-message}.tsx`, `frontend/tests/sessions.test.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md và archive `docs/changelog/phase-02.md`. **Blocker F4-02 implementation:** không có. **F4-03 NOT STARTED; dừng sau F4-02.**

## 21. Evidence F4-03 — Multi-turn integration (2026-10-14)

**COMPLETED.** Mỗi accepted turn tiếp tục dùng backend `session_id`; frontend không gửi tự tạo request/message IDs hoặc history trong chat payload. SSE `start` phải có đúng persistent session, user/assistant IDs khác nhau và không reuse request/message IDs từ history. Backend source xác nhận `begin_streaming_turn` cấp IDs riêng; `finalize_streaming_turn` persist exact content/status/usage và recompute citations trước terminal SSE.

- Session boundary dùng React key theo API base/session ID ở `ConfiguredSessionChat` và `ChatWorkspace`, nên controller/composer/history cũ không được tái dùng cho session khác. Callback SSE capture đúng active turn; callback cũ, aborted hoặc sau terminal bị bỏ qua. Unmount abort cả stream lẫn post-terminal history read; completion callback chỉ replace URL khi workspace còn mounted và persistence check thành công.
- Sau terminal SSE, workspace đọc paginated `GET /sessions/{id}/messages` đúng một lượt xác minh, dùng chung `loadMessageHistory` với F4-02. Đối chiếu current user/assistant message IDs, request ID, role, exact content, status và assistant model/usage/error code. Success thay state bằng backend history, giữ live sources theo message ID và nhận citations backend đã recompute. Không yêu cầu history citations phải bằng SSE citation events.
- Composer khóa submit cho tới khi read hoàn tất; UI hiển thị riêng trạng thái xác minh thay vì Stop sau terminal. History read lỗi hoặc mismatch giữ terminal SSE/content, hiện safe persistence warning và link mở lịch sử đã lưu; không tự retry chat/read, không gán false FAILED cho generation đã terminal. Navigation/read abort không publish late history.
- `tests/multi-turn.test.mjs` chạy production controller → REST client/stream client/parser → mock fetch/ReadableStream → persisted message fixture → paginated history/controller. Script gồm 3 lượt cùng session, refresh/reopen trước lượt 2, distinct request IDs và 6 distinct message IDs, exact whitespace và pagination 2/page. Đây là E2E tại ranh giới controller/HTTP mock, **không phải browser DOM E2E hoặc bằng chứng MongoDB/live persistence**.
- Không sửa backend hoặc thêm dependency. Read toàn history sau mỗi terminal là lựa chọn MVP với API offset/limit hiện có; session dài tăng số request. API không có snapshot/cursor nên concurrent tab có thể làm pagination thay đổi; invalid/incomplete pages được báo lỗi, không retry tự động. Cancel/disconnect chưa có terminal không được suy diễn persisted thành công; mở lại session đọc backend khi cleanup hoàn tất. History vẫn thiếu `sources`/ordinal mapping, chờ F5 contract fallback.

| Kiểm tra (frontend/) | Kết quả |
| --- | --- |
| `node --test tests/*.test.mjs` | PASS 80/80, gồm 9 multi-turn tests: 3-turn scripted HTTP E2E mock; reuse/refresh/pagination/IDs; switching và late callback isolation; reused request rejection; persisted content/ID/request/role/status/usage mismatch và API failure; recomputed citations; navigation abort trong reconciliation. |
| `node tests/verify-api-contract.mjs` | PASS 45 REST/SSE/health schemas, network disabled. |
| `npm.cmd exec tsc -- --noEmit` (sau build) | PASS, exit 0. |
| `npm.cmd run lint` | PASS, exit 0. |
| `npm.cmd run build` | PASS, exit 0; `/chat` static và `/chat/[sessionId]` partial prerender. |
| Browser DOM navigation E2E / live backend persistence / Groq-Gemini smoke | NOT RUN; live provider chưa được cho phép. Groq=0, Gemini=0. |
| `git diff --check` và whitespace file mới | PASS. |

Files changed F4-03: `frontend/lib/chat/controller.ts`, `frontend/lib/sessions/history.ts`, `frontend/components/chat/{chat-preview,session-chat}.tsx`, `frontend/tests/multi-turn.test.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md và `docs/changelog/phase-02.md`. **Blocker implementation:** không có. **F4 COMPLETED; F5-01 NOT STARTED; dừng sau F4-03.**

## 22. Evidence F5-01 — Source mapper (2026-10-14)

**COMPLETED.** Pure `mapMessageSources(message)` / `resolveCitationOrdinal(message, ordinal)` tạo derived UI data từ `key`, `messageId`, `role`, `content` và **sources của chính message đó**. Không global source cache hoặc lookup qua message/session khác; không đổi DTO, chat state, Markdown renderer hoặc backend.

- Backend `citation_mapping.py` dùng `[n]` → `sources[n-1]`, bỏ invalid/out-of-range/ineligible references và deduplicate theo `chunk_id`, first-mention order. `rag/prompt.py` đánh số context từ 1; `rag/pipeline.py` tạo metadata sources theo đúng selected document order sau budget. `chunk_index` là vị trí chunk trong document, không phải citation ordinal.
- Mapper giữ mỗi marker occurrence cùng exact text offsets và discriminated resolved/unavailable result; riêng danh sách citations deduplicate theo chunk ID. Không lọc/compact metadata trước khi resolve, nên sparse ordinals và source không đủ IDs không dịch vị trí các source sau. UUID/page/file-name eligibility theo backend; IDs được canonicalize, file name trim, page giữ nguyên. Invalid ordinal, missing metadata, out-of-range, ineligible source và user message có lý do rõ.
- `MappedSource` giữ ordinal, `document_id`, `version_id`, `chunk_id`, `file_name`, `page` và `pdf_page_number`. `rag/loader.py` dùng `PyPDFLoader(mode='page')`; installed parser enumerate pages từ 0, truyền `page_number` vào metadata. Fixture tạo PDF 2 trang rồi chạy **load_document thực tế** xác nhận `[0,1]`. Chỉ file `.pdf` có display page = raw page + 1; Excel/text/unknown hoặc page null không suy đoán convention. API không expose PDF `page_label` (nhãn in trên trang).
- Không có href/download/preview URL trong mapper; bỏ raw `source` path và không lấy IDs từ model text. History citations không có ordinal, nên không dùng vị trí mảng citations để tái dựng `[n]`; khi history sources rỗng, result là missing_metadata. F5-02 sẽ dùng mapper cho Markdown/source drawer và fallback; chưa triển khai UI.

| Kiểm tra (frontend/) | Kết quả |
| --- | --- |
| `node --test tests/source-mapper.test.mjs` | PASS 11/11: sparse/repeated/out-of-range/unsafe ordinals, chunk_index độc lập, message isolation, history fallback, eligibility/no renumbering, duplicate chunks, raw/display PDF pages, no fake URL/user mapping; offline parity với backend và real PDF loader, network blocked. |
| `node --test tests/*.test.mjs` | PASS 91/91 full regression; test assertion projection sau đó được làm rõ và targeted 11/11 rerun PASS. |
| `npm.cmd exec tsc -- --noEmit` | PASS, exit 0. |
| `npm.cmd run lint` | PASS, exit 0, 0 warnings sau chỉnh assertion projection. |
| `npm.cmd run build` | PASS, exit 0. |
| `node tests/verify-api-contract.mjs` | PASS 45 schemas; network disabled. |
| `git diff --check` và whitespace file mới | PASS. |
| Browser citation UI / live backend/provider smoke | NOT RUN; ngoài F5-01. Groq=0, Gemini=0. |

Files changed: `frontend/lib/chat/source-mapper.ts`, `frontend/tests/source-mapper.test.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md và archive `docs/changelog/phase-02.md`. **Blocker implementation:** không có. **F5-02 NOT STARTED; dừng sau F5-01.**

## 23. Evidence F5-02 — Citation UI (2026-10-14)

**COMPLETED.** `ChatMessage` render assistant content bằng `CitationContent`, giữ user text nguyên vẹn. Rehype plugin biến `[n]` trong parsed Markdown text nodes thành citation triggers; bold/list/blockquote/GFM table giữ formatting và marker. Không xử lý marker trong link/code/pre, không rewrite raw answer hoặc dùng network chunk làm citation boundary; marker streaming chưa đủ `]` vẫn hiển thị text bình thường.

- Mỗi `CitationMarker` resolve trực tiếp trên message hiện tại bằng F5-01 mapper. Resolved marker là labelled keyboard button/SheetTrigger, callback chọn source identity `(document_id, version_id, chunk_id, page)`. Không có global selection; drawer state nằm trong message-keyed component. Unresolved marker giữ text và explanation, không tạo link/button tới nguồn giả.
- Sheet/shadcn hiện có cung cấp dialog, title/description và close control `Đóng`. Drawer full width trên mobile, tối đa 28rem trên desktop, body scroll riêng; nhóm theo document/version/file và page, nên file trùng tên/version khác không bị nhập nhằng. Click target đưa group/page/source được chọn lên đầu và highlight `Đang xem`, không đổi ordinal. Raw PDF page giữ nguyên; hiển thị page +1, non-PDF không suy đoán convention.
- `buildCitationPanel` kết hợp mapped citations với persisted citations, deduplicate source identity. Citations có metadata IDs/file/page vẫn hiển thị sau history DTO restore; khi không có ordered sources, ghi `Trích dẫn đã lưu`, ordinal=null và hiện missing mapping fallback. Không ghép vị trí citations array với `[n]`; nếu message được cung cấp ordered metadata, inline markers resolve bình thường. Với REST history hiện tại, inline click mapping sau reload **chưa thể phục hồi** vì backend không persist/expose sources order.
- Không thêm preview/download URL, fetch source endpoint, PDF viewer, localStorage, backend logic hoặc dependency. Source identity nằm trong expandable details, không expose raw filesystem path. Drawer báo chưa có preview/link thực khi backend không cung cấp.

| Kiểm tra (frontend/) | Kết quả |
| --- | --- |
| `node --test tests/citation-ui.test.mjs` (lần đầu) | PASS 8/8; sau đó thêm 2 integration/streaming tests, được chạy trong full suite bên dưới. |
| `node --test tests/*.test.mjs` | PASS 101/101 gồm 10 citation UI tests: exact click callback chọn nguồn của hai assistant, real ReactMarkdown/Rehype/SSR rendering, bold/list/quote/table/code/link behavior, group/version/page/selected identity, history DTO persisted citations/fallback, restored ordered metadata, dedupe/no false ordinal, ChatMessage assistant-only integration và partial marker completion. Đây là callback/SSR tests, không phải browser DOM click E2E. |
| `npm.cmd run build` | PASS, exit 0. |
| `npm.cmd exec tsc -- --noEmit` (sau build) | PASS, không diagnostics. |
| `npm.cmd run lint` | PASS, exit 0, 0 warnings sau bỏ unused test import. |
| `node tests/verify-api-contract.mjs` | PASS 45 schemas; network disabled. |
| `git diff --check` và new-file whitespace | PASS. |
| Browser desktop/mobile click, Escape, focus return, keyboard traversal/visual QA | BLOCKED/NOT RUN: Browser skill đã đọc và bootstrap đã thử; công cụ lỗi `Cannot redefine property: process` trước khi có browser session. Không cài automation khác để thay thế và không đánh dấu PASS. |
| Live backend/provider citation smoke | NOT RUN; Groq=0, Gemini=0. |

Files changed F5-02: `frontend/components/chat/{chat-message,citation-content}.tsx`, `frontend/lib/chat/{citation-panel,citation-markdown}.ts`, `frontend/tests/citation-ui.test.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md và `docs/changelog/phase-02.md`. **Implementation blocker:** không có; browser QA còn BLOCKED. **F5 COMPLETED; F6-01 NOT STARTED; dừng sau F5-02.**

## 24. Evidence F6-01 — List/detail/status (2026-10-14)

**COMPLETED.** `/documents` truyền public API base cho Documents UI, bỏ fixture data khỏi live list/detail. Domain client chỉ hỗ trợ `GET /documents?offset={offset}&limit={limit}&include_deleted={boolean}` và `GET /documents/{document_id}`. Runtime-check HTTP 200, plain array/list và detail/versions DTO, enum/count/date/optional-nullable fields, ID ownership, response size/duplicate IDs và deleted filter. Không giả items/total envelope hoặc status/search route.

- Source contract: `api/documents.py` offset>=0, limit 1..500 (default 100), include_deleted=false; repository sort created_at DESC, exclude DELETED mặc định. UI dùng page size 20, accumulates theo backend order và next offset là số items thực trả về. `hasMore` chỉ là tín hiệu page đầy đủ limit; trang cuối đúng limit cần thêm GET rỗng để kết thúc. Không hiển thị tổng số giả hoặc tự động tải mọi trang.
- `DocumentsController` / `useDocuments` giữ list/detail state riêng, AbortController cleanup, immutable snapshots và request-identity guards. Đổi include_deleted/Làm mới reset pages/selection/detail, abort request cũ; chọn tài liệu xóa detail cũ trước loading. Response đến muộn không ghi đè filter hoặc selected document mới. Error tải thêm giữ items đã tải và explicit retry dùng cùng offset, không duplicate submit/retry loop. Overlap document IDs giữa pages bị báo lỗi; offset API không có snapshot nên concurrent changes vẫn là giới hạn backend.
- List có loading/empty/error/retry, checkbox filter thật `Bao gồm tài liệu đã xóa`, Tải thêm và count `đã tải` không phải total. Detail có idle chọn tài liệu, loading, 404 missing, safe error/retry và ready từ GET; khi thiếu base URL, UI fail-closed và không phát request. Chưa có server status filter nên không thêm status query giả.
- Status badge giữ đủ UPLOADED/PROCESSING/INDEXED/FAILED/DELETED. List/detail hiển thị status và active_version_id riêng, versions có status và active marker từ đúng ID. PROCESSING/FAILED không tự xóa active cũ, INDEXED không suy diễn có active nếu ID null; readiness notice yêu cầu active version thật INDEXED. DELETED/cleanup_pending có thông báo riêng. Làm mới chủ động, không tạo polling/progress endpoint.
- Tận dụng Card/Badge/Button/dialogs hiện có, responsive list/detail layout. Upload/new-version/delete dialogs vẫn placeholder với mutation CTA disabled, re-index disabled; không triển khai F6-02/F6-03, không thêm dependency, không đổi backend/storage/schema/RAG.

| Kiểm tra (frontend/) | Kết quả |
| --- | --- |
| `node --test tests/documents.test.mjs` | PASS 12/12: exact GET query/routes/plain array, input/response guards, deleted filter, optional/nullables/old active, safe mock 404/503/no mutations/retries, pagination empty final probe, filter abort, load-more retry/duplicate guard, stale selection, error recovery/dispose, SSR loading/empty/error/config, independent status/active/cleanup và overlap pages. |
| `node --test tests/*.test.mjs` | PASS 113/113 regression; mock/offline fixtures only. |
| `npm.cmd run build` | PASS, exit 0; `/documents` prerender static shell, data load phía client. |
| `npm.cmd exec tsc -- --noEmit` (sau build) | PASS, exit 0; validator narrowing đã sửa đúng shape return. |
| `npm.cmd run lint` | PASS, exit 0, 0 warnings. |
| `node tests/verify-api-contract.mjs` | PASS 45 schemas; network disabled. |
| `git diff --check` và new-file whitespace | PASS. |
| Browser DOM/viewport interactions, live document GET/CORS/cloud smoke | NOT RUN; không dùng SSR tests làm bằng chứng browser/live API. Groq=0, Gemini=0. |

Files changed F6-01: `frontend/lib/api/documents.ts`, `frontend/lib/documents/controller.ts`, `frontend/hooks/use-documents.ts`, `frontend/components/documents/documents-preview.tsx`, `frontend/app/documents/page.tsx`, `frontend/tests/documents.test.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md và archive `docs/changelog/phase-02.md`. **Implementation blocker:** không có. **F6-02 NOT STARTED; dừng sau F6-01.**

## 25. Evidence F6-02 — Upload/progress (2026-10-14)

**COMPLETED.** Thêm create-document upload dialog từ UI Documents dùng `POST /documents/upload`, `FormData` chỉ chứa field `file`, giữ File/name/content; không tự đặt Content-Type để browser sinh multipart boundary. HTTP 201 và `DocumentIndexInfo` được runtime-check, giữ document/version/job IDs, file name, num_chunks, optional status và activated riêng biệt. Không triển khai PUT version/re-index/delete thuộc F6-03.

- Source audit: `api/documents.py` / `ingestion.py` kiểm tra tên file/basename, suffix từ loader và content không rỗng; `_process` mark PROCESSING, parse/embed/index/verify rồi activate trước response. `_index_response` hiện trả schema default INDEXED; ingestion failure là HTTPException, có thể đã persist FAILED document/version nhưng error không trả document IDs. Không có upload max-byte setting, polling/job progress route, hoặc upload-byte progress contract.
- `validateUploadFile` chấp nhận `.pdf/.md/.markdown/.txt/.xlsx` không phân biệt case, reject empty/invalid filename/path/extension và size<=0. MIME không được dùng như server policy, không áp max bytes tùy tiện; UI nói rõ dịch vụ chưa công bố max dung lượng. Offline fixture so khớp supported extensions và filename eligibility bằng helper FastAPI thật với network disabled.
- `UploadController` dùng immutable external-store snapshots, guard submit/file replacement trong request, AbortSignal cleanup và không tự retry. Pending là local `submitting`, không gán giả backend UPLOADED/PROCESSING hoặc phần trăm. Response giữ status thật; optional status thiếu vẫn unknown. Chỉ status INDEXED + activated=true có thông báo index/kích hoạt. UPLOADED/PROCESSING/FAILED fixtures hiển thị status được trả về, không biến thành success hoặc polling; runtime hiện tại đồng bộ thường trả final INDEXED.
- HTTP error hiển thị safe request failure, không giả document FAILED khi chưa có DTO. Timeout/network/5xx/malformed response là uncertain outcome; nút gửi không tự bật retry request đã gửi, hướng người dùng làm mới list trước khi chọn/gửi lại chủ động. Không hứa backend rollback hoặc request chưa đến server. Client ingestion wait deadline 5 phút thay default REST 30s, gồm upload/body read; đây là policy chờ của frontend, không phải server timeout/job cancellation.
- Dialog có labelled file input, size/name, aria-busy/status/error, close/submit controls, nút Làm mới danh sách và Dừng chờ phản hồi. Dừng chờ/unmount abort chờ phía client và chuyển uncertain ngay; late success không kích hoạt callback/refresh. Sau valid receipt, mounted UI refresh list bằng GET; failure/uncertain dùng refresh chủ động. New-version/delete placeholders vẫn giữ; không sửa backend/dependencies/schema/RAG.

| Kiểm tra (frontend/) | Kết quả |
| --- | --- |
| `node --test tests/document-upload.test.mjs tests/documents.test.mjs` (trước thêm late-success test) | PASS 24/24, gồm 12 upload + 12 documents. |
| `node --test tests/*.test.mjs` (final) | PASS 126/126, gồm 13 upload tests: extension/size/no max/MIME invention, exact multipart/field/content/HTTP201/deadline, browser-generated boundary, invalid-file no POST, malformed/non201 guards, optional status, duplicate submit, returned status/activation, safe HTTP failure/no retry, uncertain outcomes, navigation abort/late success và SSR no fake percent/backend state; offline backend filename parity. |
| `npm.cmd run build` | PASS, exit 0. |
| `npm.cmd exec tsc -- --noEmit` (sau build) | PASS, exit 0. |
| `npm.cmd run lint` | PASS, exit 0, 0 warnings. |
| `node tests/verify-api-contract.mjs` | PASS 45 schemas; network disabled. |
| `git diff --check` và new-file whitespace | PASS. |
| Browser picker/form/keyboard/mobile/CORS interaction | NOT RUN; SSR/controller mocks không chứng minh browser/live upload. |
| Một live file upload/index/embed/storage smoke | NOT RUN — chưa được cho phép gọi provider hoặc mutate live test document. Groq=0, Gemini=0; không tạo live test artifact. |

Files changed F6-02: `frontend/lib/api/documents.ts`, `frontend/lib/documents/{upload-validation,upload-controller}.ts`, `frontend/components/documents/{document-upload,documents-preview}.tsx`, `frontend/tests/document-upload.test.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md và `docs/changelog/phase-02.md`. **Implementation blocker:** không có. **F6-03 NOT STARTED; dừng sau F6-02.**

## 26. Evidence F6-03 — Versions/reindex/delete (2026-10-14)

**COMPLETED.** Documents detail dùng `DocumentActions` với explicit confirmation cho version/re-index/delete. Client bổ sung `PUT /documents/{id}` multipart field file, `POST /documents/{id}/re-index` không body và `DELETE /documents/{id}`. Update/reindex yêu cầu HTTP201, runtime-check ingestion DTO và đúng document ID; chia sẻ validation/FormData/deadline 5 phút với F6-02. Delete giữ HTTP200/202 riêng với response DTO, runtime-check cleanup_pending/status/raw-retention/retrieval-ineligible semantics; không giả raw files đã xóa.

- Backend source xác nhận update tạo immutable version, reindex đọc raw file của active version; ingestion activate sau index/verification và failure không promote candidate. DocumentService.delete unpublish trước vector cleanup, giữ raw files/history, trả cleanup_pending=true nếu vector failure; DELETE lại idempotent để retry cleanup. UI không có rollback/activate-old-version API giả.
- `DocumentActionsController.run` chỉ chạy với confirmed=true; lock trước await, không cho duplicate/mutation khác trong cùng controller. Preflight GET kiểm tra document ID/updated_at/status/active ID/version_count/file name so với snapshot lúc mở confirmation. Stale snapshot refresh detail rồi dừng mutation, yêu cầu xem lại/xác nhận mới. Deleted/PROCESSING không được update/reindex; reindex cần active ID. Backend không có atomic If-Match nên concurrent changes giữa preflight và mutation vẫn có thể xảy ra; client không tuyên bố đã khóa backend.
- Sau mutation response **hoặc lỗi đã gửi**, GET detail lại để reconcile từ backend. Không optimistic-promote result.version_id, không xóa active cũ khi candidate fail. Mock failure có persisted FAILED version và old active giữ nguyên. Receipt và refreshError tách riêng: GET lỗi vẫn giữ receipt nhưng nói detail là lần tải trước. Request failure sau gửi là uncertain, không tự retry; abort/navigation giữ uncertainty và late result không apply.
- `DocumentsController.reconcile` chỉ cập nhật selected ID hiện tại, abort competing list/detail reads, cập nhật list summary hoặc bỏ soft-deleted item khỏi include_deleted=false list, giữ deleted detail/audit cho người dùng. Stale selection/list response không ghi đè detail mới. Offset giảm khi item bị bỏ; các giới hạn offset pagination/concurrent changes từ F6-01 vẫn áp dụng.
- Confirmation hiển thị filename/document/active version snapshot và ảnh hưởng thực tế. Version có validated file input; re-index nói tạo version mới từ raw active; delete nói unpublish/vector cleanup/raw retention. Receipt202 báo pending, toolbar của deleted+pending cho `Thử cleanup lại` với confirmation mới; deleted+complete disable delete. Không polling/retry tự động. Stop waiting không đảm bảo hủy server operation. Dialog có title/description/close controls, safe status/error feedback.
- Không sửa FastAPI/business logic, database/storage/RAG hoặc dependency. Live mutation/provider smoke chưa được cho phép và không chạy; không tạo/xóa test data thật.

| Kiểm tra (frontend/) | Kết quả |
| --- | --- |
| `node --test tests/*.test.mjs` | PASS 139/139 gồm 13 document-action tests: exact PUT multipart/POST re-index/DELETE routes; ownership/HTTP/raw-policy guards; one-attempt conflict handling; explicit confirmation; stale revision/active/status/count; deleted/processing/no-active protection; failed-version preserve active; authoritative reconciliation; repeated DELETE202→200 with retained files/zero chunks; duplicate/abort/late result; refresh failure; stale selection/list isolation và SSR soft-delete semantics. |
| `npm.cmd run build` | PASS, exit 0. |
| `npm.cmd exec tsc -- --noEmit` (sau build) | PASS, exit 0. |
| `npm.cmd run lint` | PASS, exit 0, 0 warnings. |
| `node tests/verify-api-contract.mjs` | PASS 45 schemas; network disabled. |
| `git diff --check` và new-file whitespace | PASS. |
| Browser confirmation/click/Escape/focus/mobile interaction | NOT RUN; callback/controller/SSR tests không chứng minh browser DOM interaction. |
| Live version/reindex/delete/storage/provider smoke | NOT RUN; chưa được cho phép live mutation/provider. Groq=0, Gemini=0. |

Files changed F6-03: `frontend/lib/api/documents.ts`, `frontend/lib/documents/{actions-controller,controller}.ts`, `frontend/components/documents/{document-actions,documents-preview}.tsx`, `frontend/tests/document-actions.test.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md và `docs/changelog/phase-02.md`. **Implementation blocker:** không có. **F6 COMPLETED; F7-01 NOT STARTED; dừng sau F6-03.**

## 27. Evidence F7-01 — Error/health UX (2026-10-14)

**COMPLETED.** Thêm safe error copy theo HTTP status/kind cho REST read/chat/mutations, safe SSE error message mapping và header `Trạng thái dịch vụ` với health check chủ động. Không sửa backend, config, credentials hoặc dependency; không polling/automatic retry.

- `safeApiErrorMessage` phân biệt 400/404/409/410/422/429/502/503, network/transport/timeout/abort/protocol/incomplete/invalid-response; không dùng raw Error.message/HTTP detail/validation input/ctx. Sessions list/create/lookup/history và documents list/detail/upload/action UI giữ thông báo cụ thể thay vì bỏ HTTP status thành generic. Mutation errors tiếp tục nhắc kiểm tra persisted state, không coi failed request là rollback và không replay.
- Chat pre-header HTTP/network failure giữ safe status-specific copy, local assistant FAILED/PARTIAL và unlock composer. User draft chưa nhận start không còn PENDING mãi, hiển thị chưa xác nhận đã xử lý. Post-header SSE error giữ backend code/retryable/usage/terminal status và exact partial content, thay arbitrary message bằng allowlisted generic copy; unknown codes không echo private text. Retried turn chỉ bắt đầu từ submit chủ động, không dùng server retryable như lệnh tự retry. Error/reconciliation warning có full route reload link để đọc backend history, không replay chat.
- Thêm client turn wait deadline **180s**, gồm session creation/stream/post-terminal history verification; policy frontend, không giả là backend timeout. Guarded wait giải phóng state ngay cả khi mock/transport không hợp tác abort; callback của aborted/old turn không apply. Timeout abort reader/fetch, giữ content/status đúng local semantics, terminal backend không bị hạ FAILED. Hung history giữ terminal và hiển thị persistence warning, luôn hạ isGenerating/isVerifyingHistory. Stream reader có abort cancellation/listener cleanup để thoát pending reader.read(). REST vẫn có deadline 30s, upload/action 300s như F6.
- `checkHealth` gọi GET `/health` rồi `/health/dependencies`, 20s deadline mỗi GET, runtime-check DTO/status/service/ok và consistency 200/503. REST wrapper thêm opt-in acceptedStatuses cho typed health503 body; default HTTP error handling vẫn nguyên. Kết quả UI được reconstruct theo allowlist, không giữ arbitrary dependency messages/extra fields hoặc model/config. Header manual disclosure hiển thị API, MongoDB và Qdrant readiness, safe failure reason và button check/recheck; không request trên mount/open, duplicate check bị khóa, unmount abort và bỏ late response.
- Contract gap: `main.py` health/dependencies chỉ expose MongoDB/Qdrant và connect_all, không expose Groq health. UI ghi Groq chưa được kiểm tra; không gọi model catalog/generation/embedding để giả readiness. Generic REST503 không chỉ ra dependency, provider failure hiện có thể là pre-header502 hoặc SSE RAG_STREAM_ERROR/TIMEOUT; UI không suy đoán đó là MongoDB/Qdrant/Groq quota cụ thể. Dependency check không đảm bảo generation thành công.

| Kiểm tra (frontend/) | Kết quả |
| --- | --- |
| `node --test tests/error-health.test.mjs` | PASS 12/12: safe status/network/prototype/unknown-code copy, exact health GETs, preserved503 degraded/invalid/default REST guards, manual/duplicate/error/unmount/no-loop state, session/document/history errors, pre-header chat failure/no resend, post-header SSE partial/usage/sanitization, hung stream/session/history deadlines và actual pending SSE reader cancellation. |
| `node --test tests/*.test.mjs` | PASS 151/151 regression; fixture/mock/offline only. |
| `npm.cmd run build` | PASS, exit 0, rerun sau full history reload link adjustment. |
| `npm.cmd exec tsc -- --noEmit` | PASS, exit 0; standalone và Next build typecheck. |
| `npm.cmd run lint` | PASS, exit 0, 0 warnings. |
| `node tests/verify-api-contract.mjs` | PASS 45 schemas; network disabled. |
| `git diff --check` và new-file whitespace | PASS. |
| Browser health disclosure/retry/keyboard/CORS interaction, live cloud/provider health/error smoke | NOT RUN; fixtures không chứng minh browser/live operational readiness. Groq=0, Gemini=0. |

Files changed F7-01: `frontend/lib/api/{error-ux,health,client,chat}.ts`, `frontend/lib/health/controller.ts`, `frontend/lib/chat/controller.ts`, `frontend/lib/sessions/{controller,history}.ts`, `frontend/lib/documents/{controller,upload-controller,actions-controller}.ts`, `frontend/components/layout/{app-shell,service-health}.tsx`, `frontend/components/chat/{chat-preview,chat-message,session-chat}.tsx`, `frontend/components/documents/documents-preview.tsx`, `frontend/tests/{error-health,chat-controller,sessions}.test.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md và `docs/changelog/phase-02.md`. **Implementation blocker:** không có. **F7-02 NOT STARTED; dừng sau F7-01.**

## 28. Evidence F7-02 — UI polish/accessibility (2026-10-14)

**IN PROGRESS — implementation hoàn tất; chờ manual acceptance.** Tái sử dụng shadcn/Base UI hiện có, không cài thư viện/config/project mới, không sửa backend hoặc thêm PDF viewer. Theme switch là optional, chưa thêm.

- Chat có viewport 70dvh/min-height và vùng keyboard-scrollable. Scroll controller bám cuối khi đang theo nội dung, giữ vị trí khi người đọc cuộn lên; nút “Nội dung mới — Về cuối” bật lại follow. ResizeObserver theo content/viewport, detach/disconnect khi unmount; workspace keyed theo session. Scroll tức thời, không smooth-scroll từng delta.
- Copy message terminal/user và code giữ nguyên chuỗi/whitespace; clipboard unavailable/denied hiển thị lỗi thay vì thành công giả; cleanup timer khi unmount. Message PENDING/STREAMING không cho copy toàn response đang phát.
- Composer read-only khi generate, giữ focus/chọn text và chặn edit/submit; Enter/Shift+Enter/IME/Stop semantics giữ nguyên. Transcript không dùng aria-live đọc toàn nội dung mỗi delta; có status riêng.
- Markdown có headings rõ, code block language label/copy/keyboard overflow, GFM table overflow riêng, external link focus và thông báo tab mới. Không execute raw HTML; code/link không bị thay citation marker.
- Drawer full-width mobile/max-width desktop, long filename wrap, initial focus vào nút Đóng, dùng Base UI modal semantics cho focus trap/return/Escape (chưa browser-verified). Documents detail có labelled region/aria-controls; dialog cao giới hạn dvh và cuộn được.
- Skeleton dùng component có sẵn, aria-hidden, giữ nhãn loading ngoài skeleton. Spinner/skeleton tắt animation khi prefers-reduced-motion.

| Kiểm tra | Kết quả thực tế |
| --- | --- |
| `node --test tests/ui-polish.test.mjs` | PASS 6/6: scroll reader intent/resume/resize/detach, exact clipboard/error, production Markdown SSR, keyboard composer, skeleton accessibility. |
| `node --test tests/*.test.mjs` | PASS 157/157, mock/offline fixtures; không live provider. |
| `npm.cmd run build` | PASS, production build và các App Router routes. |
| `node node_modules/typescript/bin/tsc --noEmit` | PASS. Dùng trực tiếp node vì npx.ps1 bị PowerShell ExecutionPolicy chặn; không thay policy. |
| `npm.cmd run lint` | PASS; không vô hiệu hóa rules. |
| `node tests/verify-api-contract.mjs` | PASS 45 REST/SSE/health schemas; network disabled. |
| `git diff --check` và new-file whitespace | PASS. |
| Manual browser/mobile/keyboard/screen reader/clipboard | NOT RUN/BLOCKED: Browser bootstrap lỗi `Cannot redefine property: process`; troubleshooting API chưa khả dụng. Checklist `docs/frontend-accessibility-checklist.md` phân biệt unit/SSR/source review khỏi manual. |
| Live backend/mutation/Groq/Gemini | NOT RUN; Groq=0, Gemini=0. |

Files changed F7-02: `frontend/lib/chat/{scroll,clipboard}.ts`, `frontend/components/chat/{copy-button,code-block,chat-preview,chat-message,chat-composer,citation-content,session-chat}.tsx`, `frontend/components/layout/loading-skeleton.tsx`, `frontend/components/documents/{documents-preview,document-upload,document-actions}.tsx`, `frontend/app/globals.css`, `frontend/tests/ui-polish.test.mjs`, `docs/frontend-accessibility-checklist.md`, FRONTEND_PLAN.md, CURRENT_CHANGE.md và `docs/changelog/phase-02.md`. F2-01 archive nguyên vẹn, CURRENT_CHANGE giữ 15 entries. **Implementation blocker:** không có. **Acceptance blocker:** Browser/manual QA chưa chạy. **F7-02 giữ IN PROGRESS; dừng, không triển khai F8-01.**

### 28.1. Resolve Browser QA Blocker — 2026-10-14

- Next.js port3000/node listener, IPv4 `/chat`200, IPv6 `/documents`200, root307→chat, invalid-session route200 và client asset200/javascript đã kiểm tra từ Agent. HTTP chứng minh delivery, không chứng minh hydration hoặc manual UX.
- Basic execution và builtin import PASS; Browser package26.602.30954 import FAIL trước setup/navigation tại dòng33 `globalThis.process = processShim`. Runtime khóa ambient process bằng writable/configurable=false; source/stack xác nhận incompatibility tool, không phải localhost/frontend connection failure. Không patch vendor/security binding hoặc refactor UI.
- Thêm `frontend/scripts/qa-mock-api.mjs` (127.0.0.1:4011, RAM-only, no outbound/backend/provider, mutation503/no persisted files) và `frontend/tests/qa-mock-api.test.mjs`; Chrome/Edge commands/env restore/mock scenarios/evidence template ở `docs/frontend-browser-qa-blocker.md`, linked từ checklist.
- Lần diagnosis: mock harness4/4, full regression161/161, lint0 warnings và git diff/new-file whitespace PASS. Build/typecheck/contract NOT RUN lại; baseline PASS ở mục28 giữ nguyên. Manual browser/mobile/keyboard/screen reader **NOT RUN/BLOCKED**. Groq=0, Gemini=0.
- Files changed chỉ QA script/test và documentation (plan/current/checklist/diagnosis/archive). Chưa thu được acceptance evidence; **F7-02 IN PROGRESS**, dừng trước F8-01.

## 29. Evidence — Next.js/FastAPI development CORS (2026-10-14)

**COMPLETED sau kiểm tra HTTP trên server thực có Origin và preflight.** Đây là integration fix; F7-02 manual accessibility vẫn IN PROGRESS, chưa chuyển F8.

Audit trước sửa: `backend/app/main.py` không đăng ký CORSMiddleware; không có CORS config ở settings/env example. Agent tái hiện trên `127.0.0.1:8000`: GET sessions/documents200 thiếu Access-Control-Allow-Origin, OPTIONS chat/stream với Origin localhost:3000 + request-method POST + content-type trả405. API URL đúng không tự tạo quyền cross-origin trong browser.

Thay đổi tối thiểu: import/register FastAPI CORSMiddleware ở entrypoint, exact allowlist `http://localhost:3000` và `http://127.0.0.1:3000`; allow GET/POST/PUT/PATCH/DELETE theo routers có thật, Content-Type theo JSON/multipart clients, credentials=false. Starlette tự thêm safelisted Accept/Accept-Language/Content-Language. Không wildcard origin/method/header, không sửa API DTO/OpenAPI/routes/RAG/frontend architecture hoặc .env. Đây là allowlist development; origins/ports khác chưa được cho phép.

| Phép kiểm tra thực tế | Kết quả |
| --- | --- |
| GET /sessions + Origin localhost:3000 | PASS HTTP200, ACAO khớp origin, Vary Origin. |
| GET /documents + Origin localhost:3000 | PASS HTTP200, ACAO khớp origin, Vary Origin. |
| OPTIONS /chat/stream + Origin localhost:3000, request-method POST, request-headers content-type | PASS HTTP200, ACAO khớp, allow-methods gồm POST, allow-headers gồm Content-Type. Không gửi actual chat POST. |
| Hai GET + OPTIONS tương tự với Origin127.0.0.1:3000 | PASS cả3 requests, HTTP200 và ACAO đúng origin tương ứng. |
| OPTIONS với Origin localhost:3001 | PASS expected HTTP400, không ACAO. |
| GET /documents với Origin https://example.test | PASS expected HTTP200 không ACAO; CORS không phải authentication hoặc HTTP access control. |
| CORS regression trên actual FastAPI app | PASS6/6; GET body shapes, hai origins, preflight/no-service-call, wrong origins/scheme/port/suffix, disallowed method/header, no-Origin GET và handled503/422 headers. No lifespan/cloud/provider calls. |
| CORS + sessions + documents + chat-stream API suites | PASS26/26, Python3.10.11; socket guard chặn external network, cho loopback IPC Windows. |
| `node tests/verify-api-contract.mjs` | PASS45 REST/SSE/health schemas; network disabled. |
| `git diff --check` và new-file whitespace | PASS. |
| Frontend build/typecheck/lint, full backend suites, browser interaction/live generation | NOT RUN lại trong CORS fix; không cần thay frontend. Groq=0, Gemini=0. |

Initial runs ghi nhận FAIL: test helper dùng unittest.enterContext không có trong Python3.10 (sửa bằng ExitStack), runner block mọi socket.connect chặn asyncio Windows self-pipe (sửa guard chỉ chặn external network). Final26/26 PASS sau các sửa test/runner; không đổi middleware để che failures. Actual port8000 đã phản ánh middleware sau cập nhật source; Agent không kill/restart process thủ công.

Lệnh HTTP dùng để tái hiện/xác minh (root PowerShell; `-o NUL` không in response data):
```powershell
curl.exe --noproxy '*' --max-time 10 -s -o NUL -D - -H 'Origin: http://localhost:3000' http://127.0.0.1:8000/sessions
curl.exe --noproxy '*' --max-time 10 -s -o NUL -D - -H 'Origin: http://localhost:3000' http://127.0.0.1:8000/documents
curl.exe --noproxy '*' --max-time 10 -s -o NUL -D - -X OPTIONS -H 'Origin: http://localhost:3000' -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers: content-type' http://127.0.0.1:8000/chat/stream
```

Actual positive requests được kiểm tra thêm bằng Invoke-WebRequest với assertions status200/ACAO exact/POST/Content-Type cho cả2 origins; chỉ GET list và OPTIONS, không mutation/generation. Offline test suites: `tests.test_cors tests.test_sessions_api tests.test_documents_api tests.test_chat_stream` qua unittest runner với external-network guard.

Files changed: `backend/app/main.py`, `backend/tests/test_cors.py`, FRONTEND_PLAN.md, CURRENT_CHANGE.md, `docs/changelog/phase-02.md` (archive F2-03 nguyên vẹn, giữ15 current entries). **CORS blocker resolved.** Browser tool incompatibility và F7-02 manual AC độc lập, chưa nghiệm thu. **Dừng, không triển khai F8.**

## 30. Evidence — SessionNavigation Suspense bugfix (2026-10-14)

**Implementation/automated verification hoàn tất; browser smoke BLOCKED, task giữ IN PROGRESS.** F7-02 chưa có manual acceptance; không chuyển F8.

Audit: `ConfiguredSessions` trong `components/layout/session-navigation.tsx` gọi `usePathname()` để set isActive/aria-current. AppShell chỉ bọc AppNavigation và RouteLabel trong các sibling Suspense boundaries; chúng không bao phủ SessionNavigation. Với cacheComponents/partialPrefetching hiện có, URL của /chat/[sessionId] không biết tại prerender, hook suspends. Local installed Next16 `use-pathname.md` mô tả đúng trường hợp dynamic params chưa có generateStaticParams.

Reproduction trước sửa: production build với process-scoped NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 compile/typecheck xong nhưng prerender /chat/[sessionId] FAIL `CLIENT_HOOK_DYNAMIC`, stack chỉ tới ConfiguredSessions. Những build trước đó có thể chỉ exercise unconfigured branch; không coi build API-null là coverage cho configured sessions.

Fix nhỏ nhất: SessionNavigation bọc riêng nhánh ConfiguredSessions bằng Suspense, fallback SessionNavigationFallback chỉ dùng static SidebarGroup/label/status “Đang tải điều hướng phiên…”. Fallback không đọc URL/router/session hook, không báo sai API chưa cấu hình và không có active session giả. Unconfigured branch nguyên vẹn. Không sửa AppShell/RootLayout, fetching/createNew/router.push/Link handlers/session matching, API contract, Next config, dependency hoặc whole-route dynamic/blocking rendering.

| Kiểm tra | Kết quả |
| --- | --- |
| `node --test tests/session-navigation.test.mjs` | PASS4/4: thực thi React Suspense với pending pathname; fallback không đọc runtime URL/session state; exact active item cho từng hai session; /documents và unmatched session không false active; API-null không đọc URL/hook. Next hooks/session data mocked, không browser interaction. |
| `node --test tests/*.test.mjs` | PASS165/165 regression, fixtures/offline/mock only. |
| `npm.cmd run build`, API env non-null | PASS7/7 prerender, exit0. /chat/[sessionId] vẫn ◐ partial prerender; /documents vẫn ○ static. Env override chỉ trong process build, finally restore; không viết .env. |
| `node node_modules/typescript/bin/tsc --noEmit` sau build | PASS exit0. |
| `npm.cmd run lint` | PASS exit0, 0 warnings. |
| GET /chat/[existing-session] và /documents, dev3000 | PASS200, main landmark, không CLIENT_HOOK_DYNAMIC trong HTML. Existing session ID đọc từ REST list, không log history/private contents. |
| GET hai routes tương tự, temporary production3012 | PASS200/main/no hook error; HTTP delivery only, không chứng minh hydration hoặc cross-origin fetching trong browser. Production server do Agent tạo đã dừng đúng PID; dev/backend không bị kill/restart. |
| `git diff --check` và new-file whitespace | PASS. |
| Browser trực tiếp trên hai routes | NOT RUN/BLOCKED: skill Browser bootstrap retry vẫn fail khi import `Cannot redefine property: process`, trước setup/tab/navigation. Không chạy standalone browser automation fallback. |
| Live chat/provider, API contract verification lại | NOT RUN; không thay API. Groq=0, Gemini=0. |

Initial route HTTP probe trả404 vì PowerShell array expression nối sai URL; sửa probe bằng parenthesized path list, rerun cả4 HTTP requests PASS; không sửa UI theo lỗi của probe. Test runner/browser limits được giữ rõ. Server tạm không dừng bằng Ctrl+C; PID lookup trong sandbox bị Access denied, đọc lại với escalation và Stop-Process chỉ đúng PID của helper3012 đã xác minh, session thoát. Không thay global permissions hoặc server developer.

Browser handoff cho bugfix: trên dev localhost:3000, mở URL của existing session từ sidebar, hard refresh, xác nhận history/error state phù hợp và chỉ session đó aria-current=page; đổi session rồi mở /documents, session links còn dùng được và không có session nào falsely active. Kiểm tra console không có URL-data-outside-Suspense/hydration error. Dùng mock nếu cần create/generation theo `docs/frontend-browser-qa-blocker.md`, không gọi Groq/Gemini. Ghi browser/version và observations trước khi nghiệm thu browser smoke.

Files changed: `frontend/components/layout/session-navigation.tsx`, `frontend/tests/session-navigation.test.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md, `docs/changelog/phase-02.md` (archive F3-01 nguyên vẹn, giữ15 entries). **Không blocker code/build; browser smoke chưa chạy. Dừng sau bugfix, chưa triển khai F8.**

## 31. F7-03-01 — API Capability Audit & Functional Gap Analysis (2026-10-14)

**COMPLETED — audit/documentation only.** Đã đọc FRONTEND_PLAN, PROJECT_LOG_V2, CURRENT_CHANGE, README/env-example keys; audit source/test hiện tại và GET localhost8000/openapi.json. Không sửa implementation, tạo API mới, thêm library, đổi database/SSE/RAG hoặc chạy mutation/provider. Những source changes có sẵn trong worktree từ task trước được giữ nguyên.

### 31.1. Quy ước evidence và kết luận contract

IMPLEMENTED = có đường API/client/UI cần thiết và source/tests tương ứng; không có nghĩa đã live/browser nghiệm thu. PARTIAL = một phần capability còn thiếu hoặc giới hạn contract/coverage cụ thể. MISSING = chưa có phần cần thiết cho feature MVP. BLOCKED = có implementation nhưng phép nghiệm thu tương tác chưa chạy do công cụ. NOT REQUIRED FOR MVP = không có public API/UI tương ứng hoặc không cần cho streaming MVP; không đưa vào backlog implementation.

Các mã trong matrix là links đến source/tests bên dưới. Tests hiện có và đã chạy được ghi riêng; không coi test controller/SSR là browser acceptance. Status tổng hợp feature, còn cột Backend/Client/UI ghi rõ lớp nào đã có.

**Inventory từ source + OpenAPI runtime: 16 operations trên 11 paths**, không tính OPTIONS do middleware:
- Sessions: POST/GET /sessions; GET/PATCH/DELETE /sessions/{session_id}; GET /sessions/{session_id}/messages.
- Chat: POST /chat (JSON), POST /chat/stream (text/event-stream). Event payloads đối chiếu [E], không suy ra từ response string của OpenAPI.
- Documents: POST /documents/upload; GET /documents; GET/PUT/DELETE /documents/{document_id}; POST /documents/{document_id}/re-index.
- System: GET /health; GET /health/dependencies.
- Một số errors 404/409/410/503 đến từ router/repository, không được OpenAPI khai báo đầy đủ; dùng source làm evidence, không suy đoán chỉ từ schema responses.

**Rename/delete session không thiếu backend API.** PATCH title yêu cầu JSON title, min1/max200, trim và reject whitespace-only; trả SessionResponse200. DELETE trả200 DeleteSessionResponse: session tombstone retained, messages hard-deleted, deleted_messages, already_deleted, deleted_at; GET/history của tombstone trả410, unknown404, malformed UUID422, active generation409. Delete repository có atomic predicate active_generation_id=None; repeat DELETE vẫn thử xóa messages còn sót. Rename không check active generation trong predicate. Frontend đã có DTO UpdateSessionTitleRequest/DeleteSessionResponse nhưng chưa có request functions hoặc UI/actions.

**Giới hạn public API:** SessionResponse không expose active_generation_id; client không thể biết lock của browser khác, backend409 là authority. Scope đọc được nhưng không có endpoint đổi scope. History có citations, không có ordered sources/citation ordinal. Document detail chứa versions, không có version-selection/rollback/failed-version-retry route. Ingestion chạy synchronous; job_id không phải polling URL. Không có raw-file download/PDF-preview route, server cancel endpoint hoặc per-message mutation API.

### 31.2. Functional Capability Matrix

#### Session Management

| Feature | Backend API | Frontend API Client | UI | Tests | Status | Required Action |
| --- | --- | --- | --- | --- | --- | --- |
| Create session / New Chat | POST /sessions201, body {} hoặc title [S] [SS] | createSession, runtime validation [SF] | Sidebar createNew → router.push; composer cũng tạo trước stream [SN] [CW] | [TS] [TB] [TCHAT] PASS | IMPLEMENTED | Giữ existing flow; synchronization gap ghi riêng. |
| List sessions | GET /sessions200, items/offset/limit/total [S] | listSessions accepts pagination [SF] | Sidebar loading/empty/error và titles [SN] | [TS] [TNAV] PASS | IMPLEMENTED | Không tạo lại list UI. |
| Session list pagination | offset≥0, limit1..200/default50; updated_at DESC, _id DESC [S] [SR] | Có query params [SF] | Hook hardcode offset0/limit50; chỉ “Hiển thị n/total”, không Load More [SH] [SN] | [TS] chỉ load first page; chưa có sidebar >50 test | PARTIAL | F7-03-02: load more/refresh, ổn định IDs, chống overlap/reset. |
| Get session / current URL / missing | GET /sessions/{id};404/410/422 [S] | getSession + lookup controller [SF] [SC] | SessionChat kiểm tra trước history, có invalid/missing/error; active item theo exact href [HC] [SN] | [TS] [TNAV] PASS | IMPLEMENTED | Giữ behavior, thêm integration với delete. |
| Rename/update title | PATCH /sessions/{id}200, validated title [S] [SS] | Chỉ DTO; không update/rename function [SF] | Không action/menu/title dialog [SN] | [TB] fake-service PATCH happy path; FE tests thiếu | MISSING | F7-03-02: client+mutation state+existing dropdown/dialog, validate đúng payload. |
| Delete session | DELETE /sessions/{id}200, tombstone/messages-hard-delete [S] [SR] [SS] | DTO có, delete function chưa có [SF] | Không confirmation/action [SN] | [TB] fake-service delete/410 có; FE/repeat-delete repo tests thiếu | MISSING | F7-03-02: typed delete/confirm/reconcile, không nhầm với document raw-file policy. |
| Delete session đang mở | Backend contract như trên [SR] | Chưa có mutation [SF] | Chưa navigate khỏi route đã xóa hoặc clear loaded history [SN] [HC] | Chưa có FE active-delete test | MISSING | Sau confirmed200 đúng ID: abort read/draft cũ, remove list, replace /chat; xóa session khác không đổi current. |
| Delete khi stream đang chạy / remote race | Repository rejects active lock409, atomic predicate; rename không bị cấm bởi lock [SR] | Error layer đã giữ409, chưa có session action [API] [ERR] | Sidebar không nhận ChatController isGenerating; chưa có policy action [SN] [C] | [TLOCK] cover concurrent generations/cancel; chưa thấy dedicated delete-vs-generation repo test | PARTIAL | F7-03-02: safe409/no-auto-retry; nếu biết local activity thì block delete, không invent active field; test atomic guard. |
| Get messages/history pagination | GET messages, limit1..500/default100, stable sequence/_id [S] [SR] | listSessionMessages + loadMessageHistory load all pages, reject duplicate/mixed IDs [SF] [H] | History restored backend, không localStorage system of record [HC] | [TS] [TMULTI] PASS | IMPLEMENTED | Giữ contract; đây là eager page loading, không có infinite-scroll history UI. |

#### Chat Management

| Feature | Backend API | Frontend API Client | UI | Tests | Status | Required Action |
| --- | --- | --- | --- | --- | --- | --- |
| Session trước question / multi-turn | Optional session_id; persistent mode dùng IDs backend [B] [BC] | ChatController createSession trước stream, reuse session_id [C] | Không nhập UUID; question composer và duplicate guard [CW] | [TCHAT] [TMULTI] PASS | IMPLEMENTED | Không rebuild streaming integration. |
| Composer-created session → sidebar | POST /sessions có thật [S] | Chat workspace gọi createSession riêng, không dùng sidebar controller [C] [SH] | Sidebar hook chỉ load mount; không invalidation/subscription với create từ composer [CW] [SN] [SH] | Chưa có cross-component sidebar test; controller tests không cover gap | PARTIAL | F7-03-03: narrowly scoped synchronization; một create/turn, cập nhật đúng session list. |
| URL sau first question / refresh trong lượt | Backend tạo session trước headers [BC] | submit promise kết thúc sau stream+history verification [C] | router.replace trong then, còn bị chặn khi persistenceError [CW] | [TMULTI] controller persistence có; early-refresh URL chưa tested | PARTIAL | F7-03-03: make timing/recovery rõ; không naive route replace làm dispose stream. Ghi policy deferred URL nếu giữ. |
| POST /chat/stream & events | start/metadata/delta/done/error; schema có citation nhưng runtime không emit [B] [E] | fetch ReadableStream+UTF8/SSE parser/order/sequence/IDs/usage [STREAM] | Assistant draft cập nhật incremental [C] [CW] | [TSTREAM] [TPARSER] [TBSSE] PASS | IMPLEMENTED | Giữ whitespace và không coi read chunk/delta là event/token/từ. |
| Stop / unmount / session switch | Disconnect cleanup finalize+release guard; không có cancel REST endpoint [B] [BC] | AbortController stop/dispose + ignore late callbacks [C] [STREAM] | Stop Generating; component cleanup khi đổi route [CW] | [TCHAT] [TMULTI] [TBSTREAM] PASS | IMPLEMENTED | Stop là client abort; persisted status cần reread, không tự retry request đã gửi. |
| Persistence / reconciliation | Persist user trước SSE; finalize assistant trước terminal, citations recomputed [BC] | Sau terminal read history và check IDs/content/status/model/usage [C] [H] | persistence warning + link reload giữ terminal text [CW] | [TMULTI] [TPERSIST] [TBSTREAM] PASS | IMPLEMENTED | Giữ nguồn backend; không giả nhận thành công khi reread fail. |
| Empty/loading/error/terminal UI | COMPLETED/PARTIAL/FAILED và pre-header HTTP/post-header SSE errors [B] | Deadline180s, safe errors, generation lock cleanup [C] [ERR] | Empty, loading, failure/partial text, intentional recovery [CW] [M] | [TCHAT] [TERR] PASS | IMPLEMENTED | Historical nonterminal gap ghi dòng kế. |
| Historical PENDING/STREAMING không có live stream | GET messages expose mọi MessageStatus [S] [SS] | history mapper giữ status; new ChatController isGenerating=false [H] [C] | Bubble vẫn “Đang gửi/Đang trả lời” + animate spinner dựa status; không poll history [M] | Chưa có regression phân biệt historical nonterminal/live status | PARTIAL | F7-03-03: UI-only history provenance/status explanation + explicit reload; không tự sửa backend status hoặc resume generation. |
| Copy message/code; Markdown | Không cần endpoint | Clipboard helper giữ exact text [COPY] | Message terminal/câu hỏi và code copy, denied fallback; code/table overflow [M] [CIT] | [TPOLISH] helper/SSR PASS, clipboard browser chưa chạy | IMPLEMENTED | Browser/permission/whitespace paste QA ở F7-03-05, không tạo AI action mới. |
| Live citations / source drawer | Metadata ordered sources; page loader0-based, persisted cited identities [B] [BC] | Ordinal [n]→metadata position, đúng assistant; không chunk_index [MAP] | Click callback đúng source, file/page grouped; no fake links [CIT] | [TMAP] [TCITE] PASS | IMPLEMENTED | Browser click/focus cần QA, không PDF viewer. |
| Citation sau refresh/history | History chỉ citations, không sources/ordinal [SS] | sources=[] khi restore, không invent ordinal [H] [MAP] | Saved-source list+missing metadata fallback; [n] không còn clickable mapping nếu thiếu metadata [CIT] | [TS] [TCITE] [TMAP] PASS fallback | PARTIAL | Chấp nhận explicit fallback MVP; full ordinal restore cần backend contract change được giao riêng. |
| Non-stream POST /chat UI | JSON endpoint còn nguyên [B] | DTO có; không dedicated /chat client function | UI chọn SSE transport | API backend tests; FE không có JSON chat UI | NOT REQUIRED FOR MVP | Không xây song song transport UI. |
| Edit/Regenerate/Delete individual message | Không public route trong inventory [S] [B] | Không client | Không UI | Không tests capability này | NOT REQUIRED FOR MVP | Không đề xuất hoặc triển khai trong F7-03. |

#### Document Management

| Feature | Backend API | Frontend API Client | UI | Tests | Status | Required Action |
| --- | --- | --- | --- | --- | --- | --- |
| List / pagination / filter | GET documents plain array; offset/limit1..500/default100, include_deleted [D] | get/list runtime DTO checks [DF] | Page size20, Load More, include-deleted checkbox [DL] [DC] | [TDLIST] [TBDOC] PASS | IMPLEMENTED | Không invent status/search filter hoặc total envelope; full cuối cần empty probe. |
| Upload multipart & file validation | POST upload201, file field; supported suffix/nonempty, không max size public [D] | uploadDocument FormData không set boundary; validator đúng extensions [DF] [VALID] | Wired UploadController/dialog, không fake progress [DU] | [TUPLOAD] [TBDOC] PASS | IMPLEMENTED | Manual mock success/failure ở F7-03-04/05; live upload chưa cho phép vì embedding. |
| Detail / versions | GET id200, versions[] trong detail [D] | getDocument [DF] | Active-version ID tách khỏi document/version status, immutable history [DL] | [TDLIST] [TBDOC] PASS | IMPLEMENTED | Không cần versions-list API riêng. |
| Update/new version | PUT id multipart201, immutable candidate [D] [ING] | updateDocument [DF] | Phiên bản mới + confirm, validation và duplicate guard [DA] [DAC] | [TDA] [TBING] PASS | IMPLEMENTED | Đã nối F6-03, không triển khai lại. |
| Re-index | POST id/re-index201, raw active version → new candidate [D] [DS] | reindexDocument [DF] | Confirm; disabled PROCESSING/DELETED/no-active [DA] [DAC] | [TDA] [TBDOC] [TBING] PASS | IMPLEMENTED | Không gọi retry/version-select endpoint giả. |
| Delete / cleanup / raw retention | DELETE id200/202, metadata unpublish, vector cleanup, raw/history retained [D] [DS] | deleteDocument validates status/cleanup_pending [DF] | Soft-delete wording, confirm, intentional cleanup retry [DA] [DAC] | [TDA] [TBDOC] [TBING] PASS | IMPLEMENTED | Giữ receipt semantics, không tuyên bố raw files đã xóa. |
| Ingestion status vs active version | UPLOADED/PROCESSING/INDEXED/FAILED/DELETED metadata; failure không promote candidate [ING] [DS] | Optional receipt.status không default giả; reread detail [DF] [DAC] | Status badge+active ID riêng, manual refresh [DL] [DU] [DA] | [TUPLOAD] [TDLIST] [TDA] [TBING] PASS | IMPLEMENTED | Synchronous request, job_id không có polling/progress API; không chuyển background. |
| Loading/empty/error; refresh sau mutation | List/get+safe handled errors [D] | List reset/select cancellation; action check/send/reread [DC] [DAC] | Upload success reload list; action reconcile selected detail/list, warn stale/uncertain [DL] [DU] [DA] | [TDLIST] [TUPLOAD] [TDA] PASS | IMPLEMENTED | F7-03-04 kiểm tra actual UI composition; không blind promote receipt version. |
| Destructive confirms / stale state | Backend authoritative lifecycle [DS] | Snapshot check trước mutation; abort/unmount; no replay [DAC] | Đã có Dialog/confirmation; pending close guard + Stop waiting [DA] | [TDA] controller/receipt SSR PASS; browser chưa chạy | IMPLEMENTED | Nghiệm thu focus/Escape/mobile ở F7-03-04/05; chỉ fix khi có evidence. |
| Rollback/select active/failed-version retry/download/PDF preview | Public routes không có; ingestion.retry là internal method [D] [ING] | Không client endpoint tương ứng | Không wired controls; source drawer ghi chưa có preview [CIT] | Không public-capability tests | NOT REQUIRED FOR MVP | Không xây API mới; recover bằng existing new-version flow khi hợp lệ. |
| Legacy static dialog/hook files | Không liên quan router runtime | use-chat-stream.ts rỗng, không import; production dùng ChatController | document-dialogs.tsx static controls không được route hiện tại import | rg imports/source reachability | NOT REQUIRED FOR MVP | Dead scaffolding không phải missing live UI; cleanup optional sau phạm vi này. |

#### Integration & UX

| Feature | Backend API | Frontend API Client | UI | Tests | Status | Required Action |
| --- | --- | --- | --- | --- | --- | --- |
| Public API URL / configuration | Backend8000; credentials giữ server-side [MAIN] | Validate HTTP(S), no credentials/query/fragment; public base from layout/pages [API] | Missing-config state, không runtime input secrets | [TAPI] PASS; prior configured build PASS mục30 | IMPLEMENTED | Setup docs có ở mục29/30; root env.example chưa có frontend variable, frontend env-example chưa có: bổ sung placeholder/docs trong F7-03-05 nếu cần. |
| CORS dev origins | localhost3000/127.0.0.1:3000 exact; GET/POST/PUT/PATCH/DELETE, Content-Type [MAIN] | Không cần frontend proxy/CORS bypass | Same direct Browser→FastAPI architecture | [TCORS] PASS lần audit; actual Origin/preflight PASS mục29 | IMPLEMENTED | Origins/ports khác không tự được phép; không auth assumption. |
| HTTP/API errors / retry | source 400/404/409/410/422/429/502/503; unknown status preserved [S] [D] [B] | Safe status/kind copy; abort/deadlines; no automatic mutation replay [API] [ERR] | Loading unlock và explicit retry/reload controls | [TAPI] [TERR] PASS | IMPLEMENTED | Session action clients mới reuse wrapper; 429 không giả là Groq-specific nếu server không nói. |
| Health UX | health/dependencies expose MongoDB/Qdrant200/503, không Groq readiness [MAIN] | checkHealth validate DTO and503 [HEALTH] | Header manual check, no mount polling | [TERR] PASS | IMPLEMENTED | Không provider call để giả readiness; health không đảm bảo generation. |
| Create/rename/delete navigation & refresh toàn shell | API có CRUD [S] | Create local sidebar state; workspace/sidebar controllers độc lập [SC] [C] | New Chat sidebar push có; rename/delete chưa có; composer/list invalidation gap | [TS] [TNAV] cover subset; missing cross-component CRUD | PARTIAL | F7-03-02 quản lý mutation-list/current route; F7-03-03 quản lý composer event, không duplicate owner. |
| Suspense/session active route | Backend contract không bị đổi | Runtime pathname chỉ để active links [SN] | Local boundary/fallback đã sửa; shell bố cục khác giữ nguyên | [TNAV] PASS4/4; configured build/prerender + HTTP mục30 | IMPLEMENTED | Không force-dynamic/instant=false; browser hydration vẫn chưa nghiệm thu. |
| Responsive/keyboard/dropdown/confirm/browser | API không quyết định focus | Existing Base UI/shadcn DropdownMenu/Dialog/Sheet có sẵn | Source đã có dialogs/initial focus; session menu còn thiếu [SN] [DA] [CIT] | [TPOLISH] [TNAV] [TDA] SSR/controller only; checklist manual NOT RUN | BLOCKED | F7-03-02 tạo menu bằng existing primitives; F7-03-05 browser hoặc developer evidence, không coi SSR là focus/keyboard PASS. |
| Auth/multi-tenant, session-scope editor, Groq health API | Không public auth/scope mutation/provider-readiness routes [S] [MAIN] | Không client | Không UI | Không MVP feature tests | NOT REQUIRED FOR MVP | Giữ single-user dev/ALL_ACTIVE creation; không mở rộng kiến trúc. |

### 31.3. Gaps và technical debt trước F8

**Phải xử lý chức năng/coverage:** missing session PATCH/DELETE UI/client; current-session delete navigation; 409/no replay; sidebar >50 reachability; list mutation reconciliation; composer→sidebar invalidation; historical nonterminal message không giả đang live; mock functional flow/menu/dialog/browser acceptance.

**Coverage gap backend session actions:** test_sessions_api PATCH/DELETE dùng FakeConversationService; test_conversation_concurrency cover generation lock/cancel, chưa thấy direct regression cho delete_session active-lock/atomic race/repeated tombstone cleanup. Source đã implement guard, không kết luận API thiếu; thêm offline repository/transport tests trong F7-03-02/05.

**Debt cần ghi rõ hoặc chốt MVP:**
- History citation ordinal: accepted baseline fallback (mục23), không giả source link. Muốn restore exact [n] sau refresh cần persist ordered sources/ordinal với contract/schema change riêng; không nằm trong F7-03 frontend completion.
- Session URL deferred: hiện first question ở /chat chỉ canonicalize sau submit+verification. Refresh mid-stream có thể mất route của session mới; giữ safe no-replay + recovery link. F7-03-03 phải chốt rõ timing và test, không đổi route sớm khiến keyed workspace unmount/abort.
- History PENDING/STREAMING: status API phải được giữ; presentation tách historical state khỏi local active request. Manual reread hợp lệ; không auto-resume/generate/poll loop.
- Upload/index đồng bộ, không byte maximum công bố, không server cancellation/job polling: giữ explicit uncertainty/no fake progress; không áp giới hạn server tưởng tượng. Nếu muốn async jobs/quota/API cancel phải giao backend scope riêng.
- Source inference cần fixture trước khi sửa: backend SSE error dùng emitted_delta để chọn PARTIAL, còn finalize_streaming_turn dùng content.strip() để chọn persisted FAILED/PARTIAL. Whitespace-only error có khả năng khác status; chưa có test cụ thể xác minh case này. F7-03-05 bổ sung fixture parity; nếu reproduce thì mở bugfix transport/persistence được giao riêng, không sửa RAG/API trong audit.
- History eager-load all pages có thể tốn RAM/latency với conversation dài; current stable-order/mixed-session guards đã có. Không thêm infinite history pagination UI nếu chưa có nhu cầu MVP.
- Offset pagination trên list updated_at thay đổi có thể overlap khi có concurrent writes; reconcile/reset từ backend sau mutation, detect duplicate IDs, không tuyên bố snapshot isolation.
- Browser/tool limitation và live mutation/provider tests chưa chạy: F7-02/Suspense browser state vẫn IN PROGRESS. Không tự nâng COMPLETED vì CORS/prerender đã sửa. Full F7 trước F8 cần manual evidence hoặc user explicitly chốt debt/coverage có thể chấp nhận.
- Static document-dialogs.tsx và empty unused use-chat-stream.ts là scaffolding; không ưu tiên refactor/xóa ở task audit.

**Không cần architectural approval để dùng PATCH/DELETE hiện có.** Giữ SSE-first, synchronous ingestion, single-user dev, MongoDB làm record. Các ý tưởng đổi citation persistence/schema, async ingestion, auth/scope editor, raw-file viewer hoặc cancellation API đều cần task/authorization riêng nếu muốn; không tự đề xuất chúng như prerequisite MVP.

### 31.4. Implementation backlog đề xuất — chưa triển khai

#### F7-03-02 — Session Actions (ưu tiên 1)

- **Scope:** typed PATCH title/DELETE đúng existing response/error contracts; session menu+rename/confirm delete bằng DropdownMenu/Dialog/Input đã có; mutation state/duplicate guards, list pagination/refresh/reconciliation và active-route cleanup. Backend409 là authority cho active generation; không auto-cancel stream rồi replay DELETE. Rename được backend cho phép trong generation, không invent server restriction.
- **Files dự kiến:** frontend/lib/api/sessions.ts; lib/sessions/controller.ts hoặc narrowly scoped actions-controller.ts; hooks/use-sessions.ts; components/layout/session-navigation.tsx và session-actions.tsx nếu cần; types/sessions.ts chỉ UI-only state/guards phù hợp; tests/sessions.test.mjs/session-navigation.test.mjs + session action fixtures. Backend tests/test_sessions_api.py và dedicated repo-action test nếu cần, **không sửa backend business logic**.
- **Dependencies:** F7-03-01 complete; reuse error wrapper, CORS, local Suspense, existing shadcn. Không phụ thuộc API mới hoặc F8. Owner của list/current-session mutation nằm trong task này; composer synchronization thuộc task03.
- **AC:** rename trim/nonempty/≤200 theo actual request contract, send one PATCH, update đúng ID/title/order từ response/reload; cancel dialog không request. Delete explicit confirm, correct returned ID, status/already_deleted/message_policy/tombstone/deleted_at preserved; success current session → /chat và không history/delta cũ, other-session delete giữ current. 404/410/409/422/429/503/network/unknown outcome rõ; không local success trước receipt, không replay. Repeat DELETE200/already_deleted được hiểu đúng; không gọi session delete là giữ messages. >50 sessions reach được bằng pagination; reset/dedupe và refresh sau mutation, stale late response không revive deleted row.
- **Required tests:** exact PATCH/DELETE methods/JSON/200 shapes/ID validation; blank/whitespace/long/Unicode title; confirm/cancel/duplicate; current/other delete; remote409 while generating/no-replay; atomic delete-vs-generation repo fixture, repeated delete/tombstone cleanup; stale list+pagination pages; dropdown Enter/Space/arrows/Escape, dialog focus trap/return trên browser hoặc developer evidence.
- **Out-of-scope:** backend endpoint mới, individual messages CRUD, bulk delete, search/scope/auth, global state library, auto retry/timers.

#### F7-03-03 — Chat Actions Completion (ưu tiên 2)

- **Scope:** synchronize session mới tạo từ composer với existing sidebar list owner; explicit first-turn URL/recovery timing; historical nonterminal status UX vs local live stream; deliberate reload history khi cần. Reuse Stop/copy/source drawer và controller generation checks đã có, sửa chỉ gap này.
- **Files dự kiến:** components/chat/chat-preview.tsx, session-chat.tsx, chat-message.tsx; lib/chat/controller.ts; lib/sessions/history.ts; existing session hook/sidebar connection từ task02; types/UI-only provenance khi cần. Tests/chat-controller, multi-turn, sessions, citation-ui, ui-polish và component integration fixtures.
- **Dependencies:** task02 cho list mutation/invalidation ownership; F3/F4/F5 existing contracts. Không cần event/SSE/backend schema mới. Kết nối hẹp giữa components/controller, không refactor toàn application architecture.
- **AC:** một question tạo đúng một backend session; composer-created session xuất hiện sidebar sau reconciliation, same IDs/reuse3 turns; successful canonical URL/history refresh không mất current; deferred URL policy/recovery được hiển thị/test nếu giữ, không route change vô tình abort turn. Historical PENDING/STREAMING không hiển thị như local live connection vô hạn; preserved backend status và explicit reread, không fake COMPLETED/PARTIAL. Stop/unmount/switch không leak text/session IDs, no duplicate/no generation auto retry. Copy exact text, sources đúng assistant, history fallback ordinal giữ nguyên.
- **Required tests:** mock shell sidebar+workspace creation/list sync; stream/verification failure và reload; refresh với historical PENDING/STREAMING/FAILED/PARTIAL; delayed backend terminal/409;3-turn reused session distinct request IDs; Stop/disconnect/route switch late deltas; citation missing/sparse/repeated/history; copy denied/exact whitespace. Browser tests dùng mock, không live providers.
- **Out-of-scope:** Edit Message/Regenerate/Delete Individual Message, stream resume, auto resend/polling loop, persist citations ordinal/source order backend, model/theme/PDF scope.

#### F7-03-04 — Document Actions Completion (ưu tiên 3, verification-first)

- **Lý do điều chỉnh:** F6-02/F6-03 đã nối đầy đủ API/client/controller/UI; task này không xây lại actions, chỉ nghiệm thu assembled UI và sửa failures có evidence.
- **Scope:** list→detail→upload/version/re-index/delete/cleanup flow bằng mock; refreshed list/detail, status/active separation, stale snapshots, uncertain response và actual dialog usability. Đảm bảo action receipts và backend read authoritative.
- **Files dự kiến:** components/documents/documents-preview.tsx, document-upload.tsx, document-actions.tsx; lib/documents controllers và lib/api/documents.ts **chỉ nếu test chứng minh lỗi**; tests/document-upload, document-actions, documents + mock fixtures.
- **Dependencies:** existing F6 implementation, F7-02 responsive/focus work, stable errors/CORS. Không phụ thuộc session action business logic; ưu tiên theo requested ordering nhưng verification có thể độc lập.
- **AC:** multipart field file/boundary đúng; no empty/unsupported file request; pending status không fake%/INDEXED; actual201/status/activated và reread dùng đúng contract. Version failure preserve active cũ, re-index đúng /re-index và creates new version, delete200/202 ghi raw retention, cleanup retry explicit confirm. Selection/filter/navigation không bị late action overwrite; refresh fail warn stale. Confirm/cancel/Escape/focus/mobile hoạt động; sync upload không biến thành job polling.
- **Required tests:** reuse13 upload +13 actions +12 list/detail fixtures, thêm composition tests nếu thiếu (upload triggers list reload, mutation updates selected detail/removes row, include_deleted/cleanup warning, busy modal/no duplicate, unmount uncertain). Browser keyboard/viewport/mock success/failure; live ingestion NOT RUN trừ task riêng cho phép Gemini.
- **Out-of-scope:** new version endpoints, rollback/version select, retries bằng job_id, raw-file/PDF download/preview, async jobs, hard-delete raw, thêm library/refactor.

#### F7-03-05 — Functional QA & Regression (ưu tiên 4, gate trước F8)

- **Scope:** integration fixtures cho completed task02/03/04, source/OpenAPI/DTO drift check, HTTP CORS/prerender, browser/manual entire critical flows và technical-debt disposition. Không tự phát triển features mới.
- **Files dự kiến:** frontend/tests existing/new functional fixtures; frontend/scripts/qa-mock-api.mjs mở rộng PATCH/DELETE/list pagination/successful mock document mutation có authoritative reads (harness hiện chưa cover các actions success này); backend selected tests, docs/frontend-accessibility-checklist.md, docs/frontend-browser-qa-blocker.md, FRONTEND_PLAN/CURRENT_CHANGE. Frontend env placeholder/setup docs nếu cần, không edit secret .env.
- **Dependencies:** task02/03/04 hoặc recorded NOT REQUIRED decisions; Browser runtime tương thích hoặc developer Chrome/Edge evidence. Gate không được “PASS” từ SSR alone; F7-02/Suspense outstanding browser checks được tích hợp để tránh double QA tasks.
- **AC:** complete matrix required rows không còn MISSING, PARTIAL nào giữ lại có reason/decision; create/list/load-more/rename/delete-current/other+409-stream;3-turn history/Stop/disconnect/copy/citation fallback; documents lifecycle/active preservation/cleanup+stale; clear loading/errors/no request loops; keyboard/focus/320–375px/zoom/reduced motion/screen reader checklist có actual outcomes. Expected whitespace-only error parity được fixture kiểm tra, mismatch ghi bugfix task riêng trước khi chốt; không tự sửa contract để test pass.
- **Required tests:** frontend complete regression, targeted backend sessions/concurrency/documents/ingestion/chat/SSE,45-schema verifier, configured API build/prerender/typecheck/lint/diff; actual Origin GET sessions/documents/preflight chat, browser refresh/routing/hydration/menu/dialog. REST/SSE mocks không gọi Groq/Gemini; production/live mutation tests chờ authorization riêng.
- **Out-of-scope:** F8 implementation/demo/publish/deploy, backend/schema/API expansion, live generation/embedding mặc định, broad refactor.

### 31.5. Checks đã chạy trong audit và giới hạn

| Check | Kết quả thực tế |
| --- | --- |
| GET localhost8000/openapi.json, chỉ print path/method inventory | PASS16 operations/11 paths khớp routers. Không đọc/in private history hoặc mutate data. |
| node --test tests/*.test.mjs (frontend) | PASS165/165 existing regression. Không thêm/sửa test code trong audit. |
| Selected backend unittest suites | PASS73/73: test_sessions_api, test_conversation_models, test_conversation_concurrency, test_documents_api, test_ingestion, test_chat_stream, test_chat_persistence, test_sse_schema, test_cors. External TCP connect/connect_ex blocked, loopback IPC Windows allowed; mocked/local services. |
| node tests/verify-api-contract.mjs | PASS45 REST/SSE/health schemas, network disabled. |
| git diff --check / new-file whitespace / source snapshot hash | PASS; tracked+untracked nonignored backend/frontend files không đổi sau documentation work. |
| Build/typecheck/lint/browser/manual/new-feature tests/live cloud mutation/provider | NOT RUN trong audit documentation-only; previous evidence ở các mục cũ không thay thế nghiệm thu features chưa có. Groq=0, Gemini=0. |

Local Qdrant fixture phát warning payload indexes không có tác dụng trên local client; tests vẫn PASS. Đây không phải verification cloud Qdrant readiness. Browser tool blocker giữ theo evidence28.1/30, không thử hoặc tự nhận khôi phục trong task audit này.

Files changed chỉ FRONTEND_PLAN.md, CURRENT_CHANGE.md và docs/changelog/phase-02.md. Không đổi PROJECT_LOG_V2, source/dependencies/config/API/DB/RAG/SSE; preserved dirty changes từ task trước. F7-03-01 đáp ứng full audit/matrix/gaps/backlog/docs, **COMPLETED**; F7-03-02…05 **NOT STARTED**. Dừng, không tự triển khai actions hoặc F8.

### 31.6. Source/test references dùng trong matrix

Các mã source và tests trong từng ô matrix đều là links đến file thực tế của checkout. Nhóm S/SF/SH/SC/SN là sessions; B/BC/E/C/CW/H là chat/history; D/DS/ING/DF/DC/DU/DA/DAC là documents; API/ERR/MAIN/HEALTH là integration. Mã T… trỏ đúng existing test file, kết quả rerun ở mục31.5; không ám chỉ missing-feature tests đã tồn tại.

[S]: ./backend/app/api/sessions.py
[SS]: ./backend/app/conversation_schemas.py
[SR]: ./backend/app/conversation_repository.py
[SF]: ./frontend/lib/api/sessions.ts
[SH]: ./frontend/hooks/use-sessions.ts
[SC]: ./frontend/lib/sessions/controller.ts
[SN]: ./frontend/components/layout/session-navigation.tsx
[H]: ./frontend/lib/sessions/history.ts
[HC]: ./frontend/components/chat/session-chat.tsx
[B]: ./backend/app/api/chat.py
[BC]: ./backend/app/conversation_service.py
[E]: ./backend/app/sse_schema.py
[C]: ./frontend/lib/chat/controller.ts
[CW]: ./frontend/components/chat/chat-preview.tsx
[M]: ./frontend/components/chat/chat-message.tsx
[STREAM]: ./frontend/lib/api/chat.ts
[COPY]: ./frontend/components/chat/copy-button.tsx
[MAP]: ./frontend/lib/chat/source-mapper.ts
[CIT]: ./frontend/components/chat/citation-content.tsx
[D]: ./backend/app/api/documents.py
[DS]: ./backend/app/document_service.py
[ING]: ./backend/app/ingestion.py
[DF]: ./frontend/lib/api/documents.ts
[DC]: ./frontend/lib/documents/controller.ts
[DL]: ./frontend/components/documents/documents-preview.tsx
[DU]: ./frontend/components/documents/document-upload.tsx
[DA]: ./frontend/components/documents/document-actions.tsx
[DAC]: ./frontend/lib/documents/actions-controller.ts
[VALID]: ./frontend/lib/documents/upload-validation.ts
[MAIN]: ./backend/app/main.py
[API]: ./frontend/lib/api/client.ts
[ERR]: ./frontend/lib/api/error-ux.ts
[HEALTH]: ./frontend/lib/api/health.ts
[TS]: ./frontend/tests/sessions.test.mjs
[TB]: ./backend/tests/test_sessions_api.py
[TCHAT]: ./frontend/tests/chat-controller.test.mjs
[TNAV]: ./frontend/tests/session-navigation.test.mjs
[TLOCK]: ./backend/tests/test_conversation_concurrency.py
[TMULTI]: ./frontend/tests/multi-turn.test.mjs
[TSTREAM]: ./frontend/tests/chat-stream-client.test.mjs
[TPARSER]: ./frontend/tests/sse-parser.test.mjs
[TBSSE]: ./backend/tests/test_sse_schema.py
[TBSTREAM]: ./backend/tests/test_chat_stream.py
[TPERSIST]: ./backend/tests/test_chat_persistence.py
[TERR]: ./frontend/tests/error-health.test.mjs
[TPOLISH]: ./frontend/tests/ui-polish.test.mjs
[TMAP]: ./frontend/tests/source-mapper.test.mjs
[TCITE]: ./frontend/tests/citation-ui.test.mjs
[TDLIST]: ./frontend/tests/documents.test.mjs
[TBDOC]: ./backend/tests/test_documents_api.py
[TUPLOAD]: ./frontend/tests/document-upload.test.mjs
[TDA]: ./frontend/tests/document-actions.test.mjs
[TBING]: ./backend/tests/test_ingestion.py
[TAPI]: ./frontend/tests/api-client.test.mjs
[TCORS]: ./backend/tests/test_cors.py

## 32. Evidence F7-03-02 — Session Actions (2026-10-14)

**Implementation/automated verification hoàn tất; IN PROGRESS cho manual menu/dialog accessibility.** Không triển khai F7-03-03 hoặc F8. Backend routes/schema/RAG/SSE và các completed tasks giữ nguyên.

Audit đầu lượt thấy `frontend/lib/api/sessions.ts` đã có validateSessionTitle/updateSessionTitle/deleteSession và list DTO hardening; tái dùng, không ghi đè/nhận là code mới của lượt này. Đối chiếu PATCH title200/DELETE200 và DeleteSessionResponse hiện hữu, field defaults optional trong DTO nhưng server serialize các defaults. User/API client work có sẵn được giữ nguyên.

- `SessionsController` thêm load-more offset/limit50, explicit refresh, pagination shape/duplicate/no-progress guards và stale-request abort. Mutations có busy/duplicate guards; cancel confirmation không request; receipt đúng session mới apply. Rename reorder/update rồi reread first page; delete remove row/total rồi authoritative reread, không late list revive deleted session. Create abort stale list để tránh overwrite; load/load-more bị khóa khi mutation/create active.
- useSessions nối typed clients. Sidebar có menu theo từng session dùng existing DropdownMenu/Button, refresh/load-more; link và action button là siblings, tránh button trong anchor. Suspense boundary/fallback không đổi. Tên validate nonempty/trim/max200 code points, không giới hạn sai emoji bằng UTF-16 maxLength.
- Controlled Dialog: rename initial focus input; delete initial focus Hủy; request pending khóa confirmation/close, safe errors giữ dialog và không tự replay; muốn retry delete phải xem lại/confirmation mới hoặc refresh. Final focus quay opener còn tồn tại, fallback New Chat/main khi row đã bị xóa. Dialog max-height/dvh và title wrap cho mobile; actual focus trap/arrows/Escape chưa được browser-tested.
- Xóa current session chỉ router.replace('/chat') sau confirmed receipt đúng ID; other-session delete giữ current. Current pathname ref cập nhật khi route đổi để giảm stale callback navigation, UUID comparison case-insensitive. Existing Chat workspace/read unmount cleanup xử lý route exit; không sửa streaming controller. Không gọi Stop hoặc retry DELETE tự động khi backend409.
- Backend active_generation_id không public: UI không giả rằng biết remote lock hoặc thêm field mới. DELETE409 có safe conflict message và không remove/navigate; PATCH rename trong generation được phép đúng existing repo contract. Tests mới chứng minh atomic delete predicate, repeated tombstone/message cleanup và HTTP409 mapping; không sửa repo/business logic.
- Mock API RAM-only thêm PATCH/DELETE session, tombstone410/history-empty, idempotent receipt,409 khi mock stream active, `/many`60 sessions và CORS allow-method PATCH. Documents mock vẫn không persist mutations. Chỉ fixture requests, không live user-session writes.

### 32.1. Verification

| Check | Kết quả thực tế |
| --- | --- |
| `node --test tests/session-actions.test.mjs` | PASS7/7 (trong full run): exact PATCH/title Unicode/DELETE, invalid response ownership/status/policy, pagination>50/overlap, confirmation/duplicate/stale list,409/network/HTTP failures/no replay, dispose/late results. |
| `node --test tests/session-navigation-ui.test.mjs` | PASS2/2: named menu/refresh/load-more/no nested buttons trong links; actual parent onDeleted callback navigate current, other-session giữ route. Mock hooks/dialog, SSR/callback evidence only. |
| `node --test tests/qa-mock-api.test.mjs` | PASS6/6 sau final mock CORS PATCH adjustment; production REST/SSE clients,60-session pagination, rename/idempotent delete/410-history, actual local HTTP409 while stream and PATCH allowed. Không browser enforcement. |
| `node --test tests/*.test.mjs` | PASS176/176 regression. Final mock-only header/assert adjustment được kiểm tra lại bằng6/6 harness; không thay UI behavior trong adjustment. |
| `python -m unittest tests.test_session_actions tests.test_sessions_api tests.test_conversation_concurrency` (backend/.venv Python3.10.11) | PASS11/11, in-memory/mocked: active lock/no deletion, atomic race, repeat DELETE cleanup/tombstone, rename preserves generation guard, router409; existing CRUD/concurrency. |
| configured API `npm.cmd run build` | PASS7/7 prerender; chat dynamic partial prerender/documents static giữ nguyên. Process env override restore, không viết .env. |
| `node node_modules/typescript/bin/tsc --noEmit` | PASS, sau build. |
| `npm.cmd run lint` | PASS0 warnings. |
| `node tests/verify-api-contract.mjs` | PASS45 schemas, network disabled. |
| `git diff --check` và new-file whitespace | PASS. |
| Browser menu/dialog keyboard/mobile/focus/screen reader; live session PATCH/DELETE/provider | NOT RUN/BLOCKED: Browser import retry lỗi `Cannot redefine property: process` trước navigation. Groq=0, Gemini=0. |

Menu/dialog source sử dụng Base UI semantics và focus refs không phải bằng chứng manual PASS. `docs/frontend-browser-qa-blocker.md` có extension F7-03-02: chạy local mock với API base `http://127.0.0.1:4011/many`, keyboard/arrows/Escape/focus-return, rename/cancel, delete current/other, pending request/back navigation, DELETE409 trong mock stream và mobile320/375px. Chưa tự đánh dấu các AC browser đã nghiệm thu.

### 32.2. Browser acceptance retry (2026-10-14)

Tiếp tục đúng F7-03-02, không triển khai lại code đã PASS. Bootstrap Browser chính thức thất bại tại bước import với `TypeError: Cannot redefine property: process`; reset phiên công cụ rồi retry vẫn cùng lỗi, trước setup/connection/navigation. Basic execution trả2 và builtin platform trảwin32. Packaged troubleshooting không có cách phục hồi lỗi này trong workspace; không sửa plugin/runtime hoặc dùng cơ chế browser-control thay thế.

- HTTP từ Agent: `127.0.0.1:3000/chat` và `localhost:3000/documents` đều200. Đây là delivery evidence, không phải hydration/accessibility acceptance.
- Rerun `node --test tests/session-actions.test.mjs tests/session-navigation-ui.test.mjs tests/qa-mock-api.test.mjs`: PASS15/15, gồm production-client mock HTTP,409/idempotence/pagination/reconciliation và SSR/navigation callbacks.
- Keyboard/focus/mobile/menu/dialog trong browser: **NOT RUN/BLOCKED**. Build/typecheck/lint/backend/contract không chạy lại trong lượt retry chỉ cập nhật docs; evidence trước ở32.1 giữ nguyên.
- Không sửa UI/API/config, không restart/kill server developer, không live mutations hoặc Groq/Gemini. Task giữ **IN PROGRESS**; handoff Chrome/Edge với mock `/many` và evidence template trong `docs/frontend-browser-qa-blocker.md` vẫn áp dụng. Không chuyển F7-03-03/F8.

### 32.3. Current capability delta so với audit snapshot mục31

| Capability | Implementation hiện tại | Remaining acceptance |
| --- | --- | --- |
| PATCH title/DELETE client → UI | Wired, safe validated receipt/state | Browser menu/dialog QA |
| Current vs other session deletion | Confirmation/callback routing implemented/tested | Browser hydration/Back/session switching |
| Active-generation delete/idempotence | Backend behavior preserved, repository/router/mock regression PASS | Manual mock conflict/recovery |
| Session list>50/refresh/mutation reconciliation | Implemented/tested | Browser long list/loading/mobile |
| Composer-created session → sidebar/history nonterminal/URL timing | Chưa đổi | F7-03-03 NOT STARTED |

Files changed: `frontend/lib/sessions/controller.ts`, `frontend/hooks/use-sessions.ts`, `frontend/components/layout/{session-navigation,session-actions}.tsx`, `frontend/tests/{session-actions,session-navigation-ui,qa-mock-api}.test.mjs`, `frontend/scripts/qa-mock-api.mjs`, `backend/tests/test_session_actions.py`, `docs/frontend-browser-qa-blocker.md`, FRONTEND_PLAN.md, CURRENT_CHANGE.md và `docs/changelog/phase-02.md` (F3-03 archive nguyên vẹn,15 entries). API client source đã có đầu lượt được tái dùng; không thêm library hoặc đổi backend logic. **Dừng ở F7-03-02; chờ manual evidence, chưa chuyển F7-03-03/F8.**

## 33. Evidence F7-03-03 — Chat Actions Completion (2026-10-15)

**IN PROGRESS chỉ ở browser acceptance; implementation/automated checks PASS.** Người dùng giao task03 riêng, không coi task02/browser acceptance cũ là COMPLETED. Matrix mục31 và evidence mục32 là snapshot lịch sử; phần này ghi current delta.

- Composer dùng `createChatServices`: POST `/sessions` đúng client/DTO có sẵn, một lần trước turn đầu; confirmed creation phát scoped in-memory list invalidation. `useSessions` vẫn sở hữu sidebar list, subscribe trước initial load và unsubscribe/dispose khi unmount. List được reread sau stream kết thúc/thất bại; không cache session/localStorage, không replay POST. Invalidation khi sidebar create/mutation đang pending được coalesce và xử lý sau mutation, không bị bỏ mất hoặc ghi đè receipt bằng stale read. Không thêm Context/provider/state library.
- Giữ policy **deferred URL** vì route mới remount keyed workspace, có thể abort stream. Chỉ replace `/chat/{id}` sau terminal + persisted-history verification thành công; `historyVerified` là UI state, reset mỗi accepted turn. Stop/disconnect/pre-header error/failed verification không tự chuyển URL. Một turn chủ động tiếp theo xác minh thành công vẫn canonicalize được, sửa gap `hadSession` trước đó. Mounted guard/unmount cleanup và turn-ID guards giữ nguyên.
- Banner ngay khi có confirmed session ID: giải thích refresh `/chat` giữa lượt không restore route; link đúng ID mở tab mới để đọc/lưu lịch sử mà không abort tab đang stream. Không claim tab mới có thể resume. Error/persistence recovery links cũ giữ nguyên. ID chưa nhận do create response uncertainty vẫn phải dùng sidebar reload chủ động, không tự tạo lại.
- `ChatViewMessage.origin=history` chỉ ở UI mapper, không đổi API DTO. Historical PENDING/STREAMING giữ status/content/request/message IDs, hiển thị nhãn snapshot + giải thích không có live connection, không spinner/“Đang chuẩn bị” vô hạn. Explicit full-page “Tải lại lịch sử”, ẩn trong local generation/verification; không polling, auto-resume hoặc fake terminal status. Backend có thể còn xử lý từ tab/client khác; submit chủ động vẫn để backend409 quyết định.
- Stop/copy/citation/Markdown/SSE implementation giữ nguyên; chỉ đổi nonterminal presentation. Sources còn được preserve theo đúng message khi verification; history REST vẫn không expose ordered sources, ordinal fallback không suy đoán. Empty terminal response không còn ghi “Đang chuẩn bị”. Không thêm Edit/Regenerate/Delete Message, model/theme/PDF, backend/schema/RAG/dependency/config.
- RAM-only mock bổ sung409 trước SSE headers khi session đã STREAMING, đúng existing FastAPI chat409 contract. Không live writes/generation, Groq=0, Gemini=0.

### 33.1. Verification thực tế

| Check | Kết quả |
| --- | --- |
| `node --test tests/chat-actions.test.mjs tests/chat-workspace.test.mjs` | PASS7/7: real hook subscription + workspace submit/SSR/effect harness + production REST/SSE/local HTTP, sidebar before terminal, no duplicate create,3-turn distinct request IDs/history refresh, invalidation scopes/queue/dispose, Stop/disconnect/verification failure/recovery, delayed terminal/remote409 and preserved history statuses. Không phải DOM hydration/browser E2E. |
| `node --test tests/*.test.mjs` | PASS183/183 ngoài sandbox. First sandbox run180/183;3 Python-dependent fixture tests FAIL vì sandbox không truy cập interpreter ngoài workspace. Không đổi/cài lại Python; existing3.10.11 dùng được khi escalation. |
| `node tests/verify-api-contract.mjs` | PASS45 schemas, offline/network blocked, ngoài sandbox. First sandbox attempt FAIL103 do cùng interpreter access. |
| Configured API `npm.cmd run build` | PASS7/7 prerender, exit0. Initial sandbox run FAIL Google Fonts fetch; rerun ngoài sandbox PASS, không sửa font/config. Process-only mock base env override đã restore; không gọi mock/backend trong build. Chat route vẫn partial prerender, documents static. |
| `node node_modules/typescript/bin/tsc --noEmit` | PASS sau production build. |
| `npm.cmd run lint` | PASS0 warnings sau sửa conditional React.useState trong test harness; không disable rule. Harness rerun1/1 PASS sau chỉnh test-only, application source không đổi sau full regression/build. |
| `git diff --check`, new-file whitespace và log archive | PASS; F4-01 archive exact text trước khi bỏ khỏi CURRENT_CHANGE, giữ15 entries. |
| Browser bootstrap | FAIL import `Cannot redefine property: process`, trước setup/connection/navigation; troubleshooting đã đọc. Mock browser keyboard/focus/mobile/URL interactions NOT RUN. |
| Live backend/provider smoke | NOT RUN; không có outbound provider calls. |

Files changed trong task03: `frontend/lib/chat/{controller,recovery,services}.ts`, `frontend/lib/sessions/{controller,history,invalidation}.ts`, `frontend/hooks/use-sessions.ts`, `frontend/components/chat/{chat-preview,chat-message,chat-recovery}.tsx`, `frontend/scripts/qa-mock-api.mjs`, `frontend/tests/{chat-actions,chat-workspace}.test.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md, `docs/frontend-browser-qa-blocker.md`, `docs/changelog/phase-02.md`. Giữ toàn bộ dirty work có trước; không sửa backend hoặc session navigation/action dialogs.

Remaining acceptance: Chrome/Edge mock extension F7-03-03 trong browser QA doc; URL/new-tab/reload/route switching, keyboard/focus/mobile và copy/source drawer trực tiếp. Rủi ro đã công bố: refresh `/chat` trước canonical URL mất current route; cần mở/lưu link hoặc chọn sidebar; uncertain POST creation không thể suy ra receipt bị mất; offset list/history không có snapshot; history thiếu ordered sources. **Dừng tại F7-03-03; chưa triển khai F7-03-04/05/F8.**

## 34. Evidence F7-03-04 — Document Actions Completion (2026-10-15)

**IN PROGRESS cho browser acceptance; automated verification/bugfix hoàn tất.** Verification-first: không triển khai lại upload/version/re-index/delete, không sửa components/UI/client/backend/contracts/RAG/dependencies/config. Existing F6 và task02/03 browser states giữ nguyên; chưa chuyển F7-03-05/F8.

### 34.1. Audit và gap có bằng chứng

Audit documents-preview/document-upload/document-actions, hooks/controllers/client, FastAPI document router/Pydantic và repository failure semantics xác nhận:

- Existing POST upload/PUT version dùng multipart `file`,201; POST `/re-index` không body tạo version mới; DELETE200/202 có retained raw-file policy. File validation/sync pending không fake progress, receipt không suy ra current detail.
- Existing callbacks: upload receipt→controller.reload; action get preflight + mutation + authoritative get→reconcile selected detail/list; stale snapshot chặn mutation, failed reread giữ receipt + stale warning; delete bỏ row khỏi default list nhưng giữ tombstone detail để cleanup confirm mới. Không cần viết lại các flows.
- **Reproduced bug:** list đã có page đầu, load-more đang chờ; action reconcile abort list cũ và điều chỉnh offset sau delete. State trở lại ready nhưng `listAbort` vẫn giữ request cũ đến khi transport settle, nên loadMore tiếp theo âm thầm return. Test kỳ vọng offsets `[0,2,1]` nhận `[0,2]` → FAIL.
- **Minimal fix:** `DocumentsController.reconcile` abort rồi clear list/detail request slots ngay. Existing signal + identity guards vẫn drop stale results/finally; load-more mới đọc đúng offset trong khi response cũ chưa settle. Regression chuyển PASS, old response không revive deleted row hoặc clear request slot mới. Không đổi retry/API/pagination strategy.

### 34.2. Verification fixtures và coverage

Thêm opt-in `/lifecycle` vào loopback QA mock, helper `qa-document-lifecycle.mjs`: metadata RAM-only, real multipart decoder, exact routes/status/GET rereads, version failure giữ active cũ theo repository, first DELETE202/explicit second200. Synthetic filename `qa-fail.txt` gây500 với persisted FAILED version; default document mutation503 giữ nguyên. Không filesystem raw-file storage, backend/provider import, outbound proxy, parse/embed/index thật hoặc job polling. Body cap2MiB chỉ thuộc mock. Handler mới phục vụ task04 acceptance, không thực thi task05.

`document-lifecycle.test.mjs` dùng actual DocumentsDataView/DocumentDetailPanel props, configured upload/actions callbacks + hook/effect harness + real production clients/controller/local HTTP. Harness mô phỏng parent props mới sau reconciliation; không chứng minh DOM/portal/focus/hydration. Test-only initial failures do giữ props cũ đã được sửa trong harness, không đổi implementation để che test.

| Check | Kết quả thực tế |
| --- | --- |
| New reconciliation regression | FAIL trước fix, PASS sau fix: canceled page slot, adjusted offset, stale response/no deleted-row revival. |
| Existing list/detail/actions | PASS26/26 với new regression, gồm12 list/detail +13 actions. |
| New lifecycle composition | PASS7/7 trong full run: upload callback/list refresh/multipart201; cancel/duplicate/busy close guards; version/re-index authoritative detail/list; failed version active preservation/delete202/confirmed cleanup200/include_deleted; stale preflight/failed reread warning; selection/filter unmount/late response; isolated profile/default503/invalid multipart; upload unmount ignores late201/no refresh/replay. |
| `node --test tests/*.test.mjs` | PASS191/191, gồm existing13 upload +13 actions +12 list/detail và8 new tests. Ngoài sandbox để offline Python fixtures truy cập existing interpreter, không cài lại environment. |
| Configured-API `npm.cmd run build` | PASS7/7 prerender, exit0; mock lifecycle base chỉ process env, restore sau build, không .env edit. Ngoài sandbox để tải Google Fonts. |
| `node node_modules/typescript/bin/tsc --noEmit` | PASS sau build. |
| `npm.cmd run lint` | PASS0 warnings sau bỏ unused binding trong mock helper; không disable rule. |
| `node tests/verify-api-contract.mjs` | PASS45 schemas, offline/network disabled. |
| `git diff --check`, new-file whitespace, archive | PASS; F4-02 archive exact text đã xác minh trước khi remove entry cũ, CURRENT_CHANGE giữ15 entries. |
| Browser bootstrap | FAIL import `Cannot redefine property: process`, trước setup/connection/navigation. Keyboard/Escape/focus/mobile/hydration/mock browser flows NOT RUN/BLOCKED. |
| Backend suites/live ingestion/provider | NOT RUN trong task04; source/schema đối chiếu và offline fixtures không thay live integration. Groq=0, Gemini=0. |

Files changed riêng task04: `frontend/lib/documents/controller.ts` (clear aborted slots), `frontend/tests/{document-reconciliation,document-lifecycle}.test.mjs`, `frontend/scripts/{qa-mock-api,qa-document-lifecycle}.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md, `docs/frontend-browser-qa-blocker.md`, `docs/changelog/phase-02.md`. Giữ dirty work có trước.

Remaining acceptance: Chrome/Edge mock `/lifecycle` checklist trong browser QA doc. Actual confirm/cancel/Escape/focus return/trap/mobile/layout không suy luận PASS từ callbacks/SSR. Mock version/raw retention counters không chứng minh ingestion/cloud/filesystem thật. Sync API không có progress/job polling/snapshot; uncertain mutations cần reread và confirmation mới, không auto-retry. **Dừng tại F7-03-04; chưa triển khai F7-03-05/F8.**

## 35. Evidence F7-03-05 — Functional QA & Regression (2026-10-15)

**IN PROGRESS; gate trước F8 NOT PASSED.** Current capability matrix/technical-debt disposition và exact commands nằm tại [docs/frontend-functional-qa.md](./docs/frontend-functional-qa.md). Không phát triển feature mới hoặc sửa frontend/backend application logic/config/API/schema/RAG trong task này. Giữ task02/03/04/F7-02/Suspense manual acceptance như cũ.

| Check | Actual result |
| --- | --- |
| Full frontend `node --test tests/*.test.mjs` | PASS193/193. New combined local HTTP workspace exercises session CRUD/rename/idempotent delete/3-turn SSE/distinct IDs/history isolation + document upload/version/re-index/delete202/cleanup200. New whitespace mismatch frontend fixture preserves exact content/PARTIAL, warns verification, unlocks/no replay/no canonical navigation. Existing action/keyboard-handler/error/clipboard/citation/deadline/controller/SSR/effect tests retained. Không DOM browser E2E. |
| Guarded backend `verify_frontend_functional_qa.py` | **FAIL:80/81 pass,1 fail**, includes sessions/action repository/concurrency/models/documents/ingestion/chat persistence/stream/SSE/CORS. External TCP blocked, loopback IPC allowed. New parity fixture compares real encoder→real ConversationService→in-memory repository; no real provider/cloud. Local Qdrant payload-index warning là fixture limitation. |
| Offline `verify-api-contract.mjs` | PASS45 schemas, network disabled. |
| `verify-local-integration.mjs` | PASS runtime/source OpenAPI paths+schemas,11 paths; actual two frontend origins × GET sessions/documents200 exact ACAO/Vary, two OPTIONS chat/stream200 with POST/content-type; disallowed localhost3001 preflight400/noACAO. GET/OPTIONS only, không print session/document body. |
| Configured API production build/prerender | PASS7/7, exit0. Process mock lifecycle base restore, no .env edits; partial session route/static documents retained. |
| `verify-production-delivery.mjs` | PASS production `/chat`, `/chat/{fixture ID}`, `/documents`200/main and client JS200; owned ephemeral loopback server stopped/exit verified. Existing developer servers untouched. HTTP không chứng minh hydration/active routing. |
| Standalone TypeScript / ESLint | PASS sau build / PASS0 warnings; không disabled rules. |
| git diff --check / new-file whitespace / log archive | PASS; F4-03 archive exact text trước khi remove entry cũ, CURRENT_CHANGE giữ15 entries. |
| Browser bootstrap | FAIL import `Cannot redefine property: process`, trước setup/connection/navigation; packaged troubleshooting workflow read. Actual keyboard/focus/mobile/zoom/reduced-motion/AT/hydration NOT RUN/BLOCKED. |
| Live providers/ingestion/user mutations | NOT RUN; Groq=0/Gemini=0. Mutation fixtures RAM/temp in-memory only; actual backend probes read-only. |

### 35.1. Reproduced blocking defect

**[BUG-STREAM-001 — terminal/history parity](./docs/bugs/stream-terminal-parity.md):** một delta chỉ chứa space/newline/tab rồi provider error → SSE PARTIAL, persisted FAILED cho cùng message/content/error code. Encoder dùng emitted_delta, persistence dùng content.strip(). Non-whitespace-error và no-delta-error control cases PASS. Frontend cảnh báo và không replay/trim/hide discrepancy; điều đó không làm backend parity PASS.

Regression equality assertion được giữ **FAIL**, không skip/xfail/đổi expected để xanh. Separate follow-up **BUGFIX — Stream terminal/persistence parity NOT STARTED**; task05 đã quy định mismatch phải ghi bugfix riêng, không tự sửa semantics/RAG/API trong QA. Defect chưa được chấp nhận/waive, gate còn chặn.

### 35.2. Technical debt và remaining acceptance

Current QA matrix không còn missing REST/action wiring được xác định ở audit task01; rows browser vẫn PARTIAL/BLOCKED. Matrix mục31 là snapshot lịch sử, current disposition trong QA report:

- Keep previously accepted citation-history fallback; không đoán ordered sources/ordinal hoặc link. Backend persistence expansion cần task riêng.
- Keep explicit deferred URL/new-tab recovery; historical nonterminal snapshot/manual reload resolved trong UI, actual browser acceptance chưa có evidence.
- Keep synchronous ingestion/no public size cap/job polling/cancel API; uncertainty/no fake progress/no replay. Offset pagination/eager history là giới hạn được ghi rõ, không claim snapshot isolation/large-history scalability.
- Auth/scope/model/theme/message editing/rollback/PDF/scaffolding cleanup không required trong MVP scope; không thêm features để làm đẹp matrix.
- Browser/manual và BUG-STREAM-001 là **blockers không waive**. Live cloud/provider/ingestion NOT RUN theo scope, mocks không thay thế live proof. F8 NOT STARTED.

Files changed: `backend/tests/test_stream_terminal_parity.py`, `backend/scripts/verify_frontend_functional_qa.py`, `frontend/tests/functional-regression.test.mjs`, `frontend/scripts/{verify-local-integration,verify-production-delivery}.mjs`, `docs/frontend-functional-qa.md`, `docs/bugs/stream-terminal-parity.md`, `docs/frontend-{accessibility-checklist,browser-qa-blocker}.md`, FRONTEND_PLAN.md, CURRENT_CHANGE.md, `docs/changelog/phase-02.md`. Không sửa application implementation; dirty changes từ trước giữ nguyên. **Dừng F7-03-05, không đánh dấu COMPLETED hoặc chuyển F8.**
