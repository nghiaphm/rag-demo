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
| F4 — Sessions/History | NOT STARTED | |
| F5 — Sources/Citations | NOT STARTED | |
| F6 — Documents | NOT STARTED | |
| F7 — UX/Resilience | NOT STARTED | |
| F8 — Testing/E2E | NOT STARTED | |

**Task đang thực hiện:** Không có. **Task vừa hoàn thành:** F3-03 — Cancel/recovery. **Task tiếp theo:** F4-01 — NOT STARTED, chờ giao việc riêng. **Blocker:** Không có blocker implementation F3-03; fake cancel/disconnect/error, build/typecheck/lint/contract/diff PASS. Browser live SSE cần `NEXT_PUBLIC_API_BASE_URL` và CORS phù hợp, chưa chạy; không gọi backend/provider. Evidence mới ở mục 18.

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

- [ ] **F4-01 — Session list/New Chat:** REST client hooks + sidebar; không yêu cầu người dùng tự nhập UUID; thiếu/invalid session xử lý rõ. AC: new/open session bằng mock API.
- [ ] **F4-02 — History/pagination:** load messages theo backend schema và thứ tự ổn định; URL phản ánh current session; refresh phục hồi từ backend, không dùng localStorage như system of record. AC: hai session không bị trộn, pagination đúng nếu có.
- [ ] **F4-03 — Multi-turn integration:** reuse session_id; đổi session giữa stream không leak deltas; request IDs distinct; validate lại backend persisted messages. AC: 3-turn scripted E2E mock; live smoke khi được phép.

### F5 — Sources & Citations

- [ ] **F5-01 — Source mapper:** mapping `[1]` → source position trong metadata của **đúng assistant message** (không phải `chunk_index`); lưu `document_id`, `version_id`, `chunk_id`, `file_name`, `page`; xác minh backend page convention 0/1-based. AC: test sparse/repeated/out-of-range citations; không tạo link giả.
- [ ] **F5-02 — Citation UI:** clickable citations/source drawer, grouped file/page, state fallback khi metadata thiếu; Markdown text không làm mất citation. AC: click citation đúng nguồn; refresh/history vẫn hiển thị nếu backend persist sources.

### F6 — Document Management

- [ ] **F6-01 — List/detail/status:** fetch/pagination/filter theo routes có thật; hiển thị document status và `active_version_id` riêng biệt. AC: loading/empty/error đúng.
- [ ] **F6-02 — Upload/progress:** file type/size validation khớp backend, `multipart/form-data` đúng schema; phản hồi UPLOADED/PROCESSING/INDEXED/FAILED thực tế, không giả lập thành công. AC: mocked success/failure, một live file test khi được phép.
- [ ] **F6-03 — Versions/reindex/delete:** update/version flows đúng backend contract, confirmations, idempotent delete semantics, preserve active version khi version mới thất bại; không tuyên bố raw files đã xóa nếu soft-delete. AC: tests cho protected actions và stale state.

### F7 — UX & Resilience

- [ ] **F7-01 — Error/health UX:** lỗi 422, 404, 409 nếu contract có, 429, 503 MongoDB/Qdrant/Groq, network, post-header SSE `error`; safe messages, retry có chủ đích, không request loop. AC: fixture tests và no infinite spinner.
- [ ] **F7-02 — UI polish/accessibility:** auto-scroll tôn trọng người đang đọc, copy, responsive drawer, focus/keyboard, skeleton, markdown/code rendering, optional theme; không scope creep PDF viewer nếu backend không hỗ trợ. AC: manual UX/accessibility checklist.

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
|---|---|
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
|---|---|
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
|---|---|
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
|---|---|
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
|---|---|
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
|---|---|
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
|---|---|
| `node --test tests/chat-controller.test.mjs` | PASS 8/8: success/terminal, duplicate guard, Stop partial/no retry, dispose during session creation, fake disconnect partial/unlock/no retry, terminal preservation, failure recovery và session contract. |
| `node --test tests/chat-controller.test.mjs tests/chat-stream-client.test.mjs tests/sse-parser.test.mjs tests/api-client.test.mjs` | PASS 58/58 combined regression; không external calls. |
| `node tests/verify-api-contract.mjs` | PASS 45 REST/SSE/health schemas; network disabled. |
| `npm.cmd exec tsc -- --noEmit` | PASS, exit 0. |
| `npm.cmd run lint` | PASS, exit 0. |
| `npm.cmd run build` | PASS, exit 0; `/chat` static và `/chat/[sessionId]` partial prerender. |
| Live browser SSE/cancel/CORS/backend/provider smoke | NOT RUN; cần public API base/CORS runtime. Groq=0, Gemini=0. |
| `git diff --check` và new-file whitespace check | PASS. |

Files changed cho F3-03: `frontend/lib/chat/controller.ts`, `frontend/components/chat/{chat-composer,chat-preview}.tsx`, `frontend/tests/chat-controller.test.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md và archive `docs/changelog/phase-02.md`. **Blocker F3-03 implementation:** không có. **F4-01 NOT STARTED; dừng sau F3-03.**
