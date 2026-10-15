# CURRENT_CHANGE — Nhật ký thực thi RAG V2

> **Vai trò:** Ghi ngắn gọn những gì Agent **thực sự đã làm** sau mỗi task, kèm file thay đổi, kiểm thử và công việc kế tiếp. Kế hoạch/checklist chính nằm tại [`PROJECT_LOG_V2.md`](./PROJECT_LOG_V2.md). Không tự nhận hoàn thành từ nội dung kế hoạch.

## 1. Trạng thái gần nhất

- **Giai đoạn:** Frontend F0…F6 COMPLETED; F7/F7-03 IN PROGRESS, F7-01 COMPLETED; backend roadmap giữ nguyên.
- **Task đang thực hiện:** `[FRONTEND/F7-03-05]` — Functional QA & Regression IN PROGRESS; gate trước F8 NOT PASSED, 2026-10-15.
- **Task tiếp theo:** Bugfix riêng BUG-STREAM-001 và nghiệm thu browser/mock; chưa được giao sửa backend semantics, F8 NOT STARTED. Các manual acceptance cũ giữ nguyên.
- **Blocker:** Whitespace-only error SSE PARTIAL/history FAILED đã reproduce; Browser import vẫn lỗi `Cannot redefine property: process`. Không waive defect/manual gate. CORS giữ COMPLETED.
- **Lần cập nhật:** Frontend193/193, build/prerender7/7/typecheck/lint/contract45/runtime OpenAPI/CORS/production HTTP PASS; backend80/81 PASS/1 FAIL parity thật. QA report + evidence mục35. Groq/Gemini calls = 0.

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

### [2026-10-15] [FRONTEND/F7-03-05] — Functional QA & Regression

- **Trạng thái:** IN PROGRESS, gate NOT PASSED; backend parity defect và missing manual/browser không waive. Không bắt đầu F8.
- **Đã thực hiện:** New combined local HTTP session CRUD/rename/3-turn history/isolation + document lifecycle fixture; whitespace-only mismatch safe frontend recovery fixture. Guarded selected backend runner (external TCP blocked/loopback IPC only); real runtime/source OpenAPI comparison + actual Origin GET/OPTIONS; owned ephemeral production server HTTP smoke và exit cleanup. Browser bootstrap vẫn FAIL trước setup/connection/navigation. Không sửa frontend/backend application logic/config/schema/RAG/dependencies.
- **Defect:** BUG-STREAM-001 confirmed: real encoder trả PARTIAL cho one whitespace-only delta rồi provider error; real ConversationService lưu FAILED với cùng content/error. No-delta/non-whitespace controls PASS. Equality regression giữ FAIL, không skip/xfail hoặc đổi expected. Frontend warning/unlock/exact whitespace/no replay PASS. Bugfix semantic riêng NOT STARTED theo scope task05; chi tiết `docs/bugs/stream-terminal-parity.md`.
- **Files thay đổi:** `backend/tests/test_stream_terminal_parity.py`, `backend/scripts/verify_frontend_functional_qa.py`, `frontend/tests/functional-regression.test.mjs`, `frontend/scripts/{verify-local-integration,verify-production-delivery}.mjs`, `docs/frontend-functional-qa.md`, `docs/bugs/stream-terminal-parity.md`, `docs/frontend-{accessibility-checklist,browser-qa-blocker}.md`, FRONTEND_PLAN.md, CURRENT_CHANGE.md, `docs/changelog/phase-02.md` (F4-03 archive nguyên vẹn, giữ15 entries).
- **Kiểm thử:** Frontend193/193 PASS; backend runner **FAIL80/81 pass,1 parity fail**. Offline contract45/runtime source paths+schemas11 paths/actual two-origin GET sessions+documents200/preflight chat200/negative preflight400 PASS. Configured production build7/7, standalone typecheck, lint0 warnings PASS; production three routes+client asset200 PASS, owned server stopped, developer servers untouched. Sandbox escalations cho Python/fonts như trước, process env restore. Browser keyboard/focus/mobile/AT/hydration NOT RUN. No live provider/ingestion/user-data mutations; Groq=0/Gemini=0.
- **Debt disposition:** QA report có current capability coverage và từng debt decision. Giữ previously accepted citation fallback, explicit deferred URL/recovery, historical snapshot UX, sync ingestion uncertainty/no fake progress, offset/eager-history constraints; auth/scope/theme/model/message edits/PDF không required MVP. Parity bug và missing actual browser evidence là BLOCKING, chưa được accept/waive.
- **Documentation checks:** git diff --check/new-file whitespace PASS; F4-03 archive exact text đã xác minh trước khi remove entry cũ, CURRENT_CHANGE giữ15 entries.
- **Tiếp theo:** Dừng F7-03-05; separate parity bugfix + manual acceptance cần hoàn tất trước khi chốt gate; F8 NOT STARTED.

### [2026-10-15] [FRONTEND/F7-03-04] — Document Actions Completion

- **Trạng thái:** IN PROGRESS cho browser confirmation/Escape/focus/mobile/hydration; automated acceptance PASS. Không triển khai lại F6 actions hoặc chuyển task05/F8.
- **Đã thực hiện:** Audit actual UI/hooks/controllers/REST và FastAPI/Pydantic/repository contracts. Reproduced load-more slot bug: action reconciliation abort stale page nhưng pointer còn giữ, lần load-more mới bị ignore; regression FAIL `[0,2]` thay vì `[0,2,1]`. Sửa tối thiểu DocumentsController.reconcile clear aborted list/detail slots, existing abort/identity guards giữ nguyên, regression PASS. Không sửa document UI/client/backend/schema/RAG/dependency/config.
- **Verification:** Opt-in loopback `/lifecycle` RAM-only metadata/real multipart/exact201/202/200/500+GET rereads; default document mutations503 giữ nguyên, không raw writes/embed/index/proxy. Composition tests actual wired upload/actions callbacks + hook/effect harness + real clients/local HTTP: upload refresh, busy/cancel/duplicate, version/reindex authoritative list/detail, failed version giữ active cũ, delete202/include_deleted/confirmed cleanup200/raw retention, stale preflight/refresh-failure warning, selection/filter/unmount/late responses. Harness initial stale-props failures được sửa trong test, không dùng làm lý do refactor UI.
- **Files thay đổi:** `frontend/lib/documents/controller.ts`, `frontend/tests/{document-reconciliation,document-lifecycle}.test.mjs`, `frontend/scripts/{qa-mock-api,qa-document-lifecycle}.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md, `docs/frontend-browser-qa-blocker.md`, `docs/changelog/phase-02.md` (F4-02 archive nguyên vẹn, giữ15 entries).
- **Kiểm thử:** Full frontend191/191 PASS, gồm existing13 upload+13 actions+12 list/detail và8 new regressions/compositions. Configured production build/prerender7/7, standalone typecheck, lint0 warnings, offline contract45 schemas PASS. Ngoài sandbox cho Python fixtures/Google Fonts như lượt trước, env process override đã restore. Browser bootstrap FAIL tại import process; manual browser NOT RUN. Backend suites/live ingestion/provider smoke NOT RUN; Groq=0/Gemini=0.
- **Documentation checks:** git diff --check/new-file whitespace PASS; F4-02 archive exact text đã xác minh trước khi remove entry cũ; CURRENT_CHANGE giữ15 entries.
- **Tồn đọng / blocker:** Browser/runtime incompatibility; cần Chrome/Edge `/lifecycle` evidence theo extension task04. Callback/SSR harness không chứng minh portals/focus/Escape/mobile. Mock không chứng minh cloud ingestion/raw filesystem; sync API không có progress polling và mutations uncertain không auto-retry.
- **Tiếp theo:** Dừng F7-03-04; chờ manual acceptance, F7-03-05/F8 NOT STARTED.

### [2026-10-15] [FRONTEND/F7-03-03] — Chat Actions Completion

- **Trạng thái:** IN PROGRESS cho browser acceptance; implementation/automated checks PASS. Không đánh dấu keyboard/focus/mobile/URL browser flows đã nghiệm thu.
- **Đã thực hiện:** Production chat services invalidate existing sidebar owner sau confirmed composer session creation và stream completion/failure, scoped API base/in-memory/unsubscribe; queue/coalesce invalidation khi list mutation/create pending, authoritative reread, không POST replay. Deferred canonical URL chỉ sau verified terminal; banner/link mở/lưu đúng session trong tab mới; recovery sau verification failure/Stop/disconnect, later verified turn vẫn canonicalize. UI-only history provenance giữ PENDING/STREAMING nhưng không fake live spinner/resume; explicit reload, backend409 authority. Stop/copy/citations/SSE giữ nguyên; không Edit/Regenerate/Delete Message hoặc backend/dependency/config changes.
- **Files thay đổi:** `frontend/lib/chat/{controller,recovery,services}.ts`, `frontend/lib/sessions/{controller,history,invalidation}.ts`, `frontend/hooks/use-sessions.ts`, `frontend/components/chat/{chat-preview,chat-message,chat-recovery}.tsx`, `frontend/scripts/qa-mock-api.mjs` (mock stream409), `frontend/tests/{chat-actions,chat-workspace}.test.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md, `docs/frontend-browser-qa-blocker.md`, `docs/changelog/phase-02.md` (archive F4-01 nguyên vẹn, giữ15 entries).
- **Kiểm thử:** New mock/service/SSR-effect integration7/7 PASS; regression183/183 PASS, gồm Stop/unmount/late deltas,3-turn distinct IDs/persistence, citations/copy fixtures; configured production build/prerender7/7, standalone typecheck, lint0 warnings, offline contract45 PASS. Initial sandbox regression180/183/contract FAIL do inaccessible external Python; build FAIL Google Fonts network; escalated reruns PASS, không sửa Python/font/config. Lint phát hiện conditional hook trong test harness, đã sửa đúng call order và rerun lint + workspace1/1 PASS. Browser bootstrap vẫn FAIL import process, manual NOT RUN; live backend/provider smoke NOT RUN, Groq=0/Gemini=0.
- **Documentation checks:** git diff --check và new-file whitespace PASS; archive F4-01 exact text đã xác minh trước khi remove entry cũ; CURRENT_CHANGE giữ15 entries.
- **Tồn đọng / blocker:** Browser package/runtime compatibility; cần Chrome/Edge mock QA theo extension task03. Refresh /chat giữa lượt chưa canonical không tự restore route; mở/lưu link hoặc chọn sidebar. Unknown create receipt cần list reread chủ động. History vẫn thiếu ordered sources, không đoán ordinal hoặc fake terminal. Offset pagination không có snapshot.
- **Tiếp theo:** Dừng tại F7-03-03, chờ manual evidence; F7-03-04/05/F8 NOT STARTED.

### [2026-10-14] [FRONTEND/F7-03-02] — Session Actions

- **Browser acceptance retry:** Bootstrap chính thức trước/sau reset phiên công cụ đều FAIL tại import (`Cannot redefine property: process`), trước kết nối URL; basic execution/builtin import PASS. Agent HTTP `/chat` IPv4 và `/documents` localhost đều200. Rerun action/sidebar/mock tests PASS15/15; keyboard/focus/mobile NOT RUN. Lượt tiếp tục chỉ cập nhật FRONTEND_PLAN.md, CURRENT_CHANGE.md và `docs/frontend-browser-qa-blocker.md`; build/typecheck/lint/backend/contract không chạy lại, evidence bên dưới thuộc lượt implementation. Không sửa UI/config/server hoặc gọi providers; giữ IN PROGRESS, chờ browser recovery/manual evidence.
- **Trạng thái:** IN PROGRESS cho manual keyboard/focus/mobile; implementation/automated verification hoàn tất. Chưa tự đánh dấu accessibility AC PASS hoặc chuyển task.
- **Đã thực hiện:** Tái dùng PATCH title/DELETE clients đã có đầu lượt; nối useSessions/SessionsController vào menu+rename/delete confirmation. Title Unicode/nonempty/max200, busy/confirmation guards, successful receipt-only route replace current session→/chat, giữ route khi xóa session khác; current-path ref tránh callback route cũ. Safe409/404/410/422/429/503/network feedback/no replay, refreshed authoritative list, load-more offset50/dedupe/stale cancellation, refresh control. Existing Base UI/shadcn, static Suspense fallback giữ nguyên. No backend business/schema/SSE/RAG/dependency changes.
- **Files thay đổi:** `frontend/lib/sessions/controller.ts`, `frontend/hooks/use-sessions.ts`, `frontend/components/layout/{session-navigation,session-actions}.tsx`, `frontend/tests/{session-actions,session-navigation-ui,qa-mock-api}.test.mjs`, `frontend/scripts/qa-mock-api.mjs`, `backend/tests/test_session_actions.py`, `docs/frontend-browser-qa-blocker.md`, FRONTEND_PLAN.md, CURRENT_CHANGE.md, `docs/changelog/phase-02.md` (archive F3-03 nguyên vẹn, giữ15 entries). `frontend/lib/api/sessions.ts` reused/preserved, không ghi đè các functions sẵn có.
- **Kiểm thử:** Full frontend176/176 PASS, gồm7 action tests+2 assembled-sidebar SSR/callback tests; mock harness6/6 với real REST/SSE clients,60 sessions/PATCH/idempotent DELETE/410/409-stream/CORS PATCH. Backend repository/API/session/concurrency11/11 PASS, active-lock/atomic-race/repeat tombstone cleanup/rename-during-generation/HTTP409. Configured-API production build7/7/prerender, standalone typecheck, lint0 warnings, contract45 schemas và diff/new-file whitespace PASS. Browser bootstrap retry FAIL import process; keyboard/focus/mobile browser QA NOT RUN. No live session DELETE/PATCH or generation; Groq=0, Gemini=0.
- **Tồn đọng / blocker:** Manual extension trong browser QA doc dùng RAM-only mock /many (60 sessions), document mutations vẫn503; chưa có actual focus trap/return/arrows/Escape evidence. Composer-created session synchronization/historical spinner/URL timing vẫn thuộc F7-03-03, chưa triển khai. Matrix mục31 là audit snapshot; current session actions evidence ở mục32.
- **Tiếp theo:** Dừng ở F7-03-02, chờ manual evidence; không tự triển khai F7-03-03 hoặc F8.

### [2026-10-14] [FRONTEND/F7-03-01] — API Capability Audit & Functional Gap Analysis

- **Trạng thái:** COMPLETED theo deliverables audit; F7-03-02…05 NOT STARTED, F7-02/bugfix browser acceptance giữ IN PROGRESS, F8 NOT STARTED.
- **Findings:** Backend PATCH/DELETE session đã có và OpenAPI xác nhận; thiếu frontend functions/menu/dialog/mutation navigation. Sidebar chỉ lấy50 session; composer tạo session bằng controller khác, không invalidate sidebar, URL replace sau terminal. History giữ PENDING/STREAMING nhưng bubble vẽ live spinner dù controller không generate. Chat SSE/Stop/persistence/copy/live citation đã nối; history thiếu ordered sources nên không restore ordinal. Document list/upload/version/re-index/delete/confirm/stale reconciliation đã nối, không cần làm lại F6.
- **Deliverables / files:** Functional Capability Matrix dựa source/tests, contract limits, backlog F7-03-02…05 đủ scope/files/dependencies/AC/tests/out-of-scope và debt/gates trong FRONTEND_PLAN mục31; cập nhật CURRENT_CHANGE.md, `docs/changelog/phase-02.md` (archive F3-02 nguyên vẹn; giữ15 entries). PROJECT_LOG_V2 chỉ đọc, không sửa implementation/API/schema/SSE/RAG/dependency/config.
- **Kiểm thử/checks:** GET /openapi.json localhost8000 PASS inventory16 operations/11 paths; frontend regression165/165 PASS; backend9 selected suites73/73 PASS với external network blocked, loopback IPC allowed; offline contract45 schemas PASS; source-hash/doc-only và git diff/new-file whitespace PASS. Local Qdrant test warning payload-index unsupported là fixture limit, không evidence cloud. Build/typecheck/lint/browser/live generation/mutations NOT RUN trong audit; evidence prior tasks giữ nguyên. Groq=0, Gemini=0.
- **Tồn đọng / blocker:** Browser/manual QA chưa có evidence; session delete active-guard/idempotence repo tests chưa thấy coverage trực tiếp, cần thêm trong F7-03-02/05. Accepted/proposed MVP debt được ghi rõ: citation-history ordinal gap, sync ingestion/no progress job API, deferred URL timing; chưa tự quyết đổi contract.
- **Tiếp theo:** Dừng sau F7-03-01; không tự triển khai F7-03-02 hoặc F8. Không cần phê duyệt kiến trúc mới để nối existing session APIs.

### [2026-10-14] [BUGFIX/SESSION-SUSPENSE] — Local boundary cho ConfiguredSessions

- **Trạng thái:** IN PROGRESS chỉ ở browser smoke; code/automated verification hoàn tất. F7-02 manual acceptance giữ IN PROGRESS, CORS giữ COMPLETED, chưa chuyển F8.
- **Audit / đã thực hiện:** ConfiguredSessions gọi usePathname ngoài boundary; AppShell có boundaries riêng cho AppNavigation/RouteLabel nhưng không bao phủ sibling SessionNavigation. Tái hiện production prerender FAIL với NEXT_PUBLIC_API_BASE_URL cấu hình. Bọc riêng ConfiguredSessions trong SessionNavigation bằng Suspense + static labelled fallback; không đổi hook fetching/router/URL/API/Next config hoặc blocking rendering. Đọc local Next16 usePathname/cacheComponents guidance.
- **Files thay đổi:** `frontend/components/layout/session-navigation.tsx`, `frontend/tests/session-navigation.test.mjs`, FRONTEND_PLAN.md, CURRENT_CHANGE.md, `docs/changelog/phase-02.md` (archive F3-01 nguyên vẹn, giữ15 entries). Không sửa AppShell/layout hoặc components khác.
- **Kiểm thử:** Targeted navigation4/4 PASS (real React Suspense fallback với suspended pathname, hai active-session paths, documents/unmatched không false active, unconfigured không đọc URL/hook); full regression165/165 PASS; configured-API production build/prerender PASS7/7, dynamic chat vẫn partial prerender và documents static; standalone typecheck, ESLint0 warnings và diff/new-file whitespace PASS. HTTP GET existing-session/docs trên dev3000 + production3012 PASS200/main/noCLIENT_HOOK_DYNAMIC. Initial HTTP probe lỗi PowerShell array expression tạo URL sai404, sửa probe và rerun PASS, không sửa UI theo lỗi probe. Browser bootstrap vẫn FAIL import process; browser interaction NOT RUN. Groq=0, Gemini=0.
- **Tồn đọng / blocker:** Cần browser smoke refresh/history/sidebar active/session switching và documents khi Browser tương thích hoặc developer nghiệm thu. HTTP/SSR fixtures không chứng minh hydration/interaction. Production server tạm3012 đã dọn đúng PID do Agent tạo; dev/backend giữ hoạt động, env override build đã restore, không sửa .env.
- **Tiếp theo:** Nghiệm thu browser bugfix/F7-02, dừng; không triển khai F8.

### [2026-10-14] [INTEGRATION/CORS] — Next.js → FastAPI development CORS

- **Trạng thái:** COMPLETED sau request Origin và OPTIONS preflight trên backend thực. F7-02 vẫn IN PROGRESS; không chuyển F8.
- **Audit / đã thực hiện:** FastAPI entry chưa có CORSMiddleware; GET200 thiếu ACAO và preflight405 được tái hiện. Thêm middleware với exact origins localhost:3000/127.0.0.1:3000, GET/POST/PUT/PATCH/DELETE, Content-Type, credentials=false. Server port8000 đã phản ánh source mới; Agent không kill/restart thủ công, không đổi frontend/env/schema/RAG.
- **Files thay đổi:** `backend/app/main.py`, `backend/tests/test_cors.py`, FRONTEND_PLAN.md, CURRENT_CHANGE.md, `docs/changelog/phase-02.md` (archive F2-03 nguyên vẹn; giữ15 entries).
- **Kiểm thử:** Actual port8000: hai origins × GET sessions/documents200 có ACAO khớp/Vary Origin; hai OPTIONS chat/stream200 có POST/Content-Type; preflight localhost:3001 trả400/noACAO và GET external-origin200/noACAO. CORS tests6/6 + sessions/documents/chat-stream regression tổng26/26 PASS, external network blocked (chỉ cho loopback IPC của Windows); contract verifier45 schemas/network disabled PASS; git diff/new-file whitespace PASS. Initial test runs FAIL do helper enterContext không có trên Python3.10 và guard chặn asyncio self-pipe, đã sửa helper/runner và rerun PASS. Browser interaction/valid chat POST/live generation NOT RUN; Groq=0, Gemini=0.
- **Tồn đọng / blocker:** Không blocker CORS; allowlist chỉ gồm hai development origins được nêu. HTTP/header acceptance không thay thế UI/browser accessibility acceptance; Browser tool incompatibility giữ nguyên.
- **Tiếp theo:** Nghiệm thu manual F7-02 theo task riêng; dừng, không tự động triển khai F8.

### [2026-10-14] [FRONTEND/F7-02-QA] — Resolve Browser QA Blocker

- **Trạng thái:** Diagnosis/handoff hoàn tất; F7-02 giữ IN PROGRESS vì manual AC chưa có evidence. Không chuyển F8-01.
- **Đã thực hiện:** Đọc plan/checklist/Browser skill, probe listener3000/node process, localhost IPv4/IPv6/root redirect/client asset. Basic execution/builtin import hoạt động; Browser bootstrap fail tại import line33. Đối chiếu package gán `globalThis.process` với kernel locked-global writable/configurable=false; xác nhận tool incompatibility trước mọi browser connection. Không sửa UI/server/config/vendor/runtime hoặc kill dev server.
- **Files thay đổi:** `frontend/scripts/qa-mock-api.mjs`, `frontend/tests/qa-mock-api.test.mjs`, `docs/frontend-browser-qa-blocker.md`, `docs/frontend-accessibility-checklist.md`, FRONTEND_PLAN.md, CURRENT_CHANGE.md, `docs/changelog/phase-02.md` (archive F2-02 nguyên vẹn, giữ15 entries).
- **Kiểm thử:** Listener3000/node snapshot PASS; `/chat` IPv4 HTTP200, `/documents` IPv6 HTTP200, root307→chat, invalid-session routeHTTP200 và client scriptHTTP200 PASS (delivery only); execution/basic import PASS; Browser import FAIL TypeError process. Mock REST/SSE production-validation/CORS/error/disconnect/persistence fixtures4/4 và full regression161/161 PASS; lint0 warnings/diff/new-file whitespace PASS. Build/typecheck/contract NOT RUN lại, evidence PASS từ lần implementation giữ nguyên. Manual browser/mobile/keyboard/screen-reader NOT RUN; Groq=0, Gemini=0.
- **Tồn đọng / blocker:** Cần Browser plugin/runtime tương thích hoặc developer nghiệm thu Chrome/Edge theo từng hàng checklist. Local mock bind127.0.0.1:4011, RAM-only, không outbound/backend/provider; mutations trả503, không lưu file. Handoff có commands/env restore/scenarios/evidence template; không suy luận manual PASS từ HTTP hoặc tests.
- **Tiếp theo:** Thu thập đủ manual evidence F7-02; dừng, không triển khai F8-01.

### [2026-10-14] [FRONTEND/F7-02] — UI polish/accessibility

- **Trạng thái:** IN PROGRESS; implementation hoàn tất, chờ manual UX/accessibility acceptance. F7-01 giữ COMPLETED.
- **Đã thực hiện:** Vùng chat bounded/dvh, reader-aware scroll follow/pause/jump và ResizeObserver cleanup; copy message/code giữ whitespace với error feedback; composer read-only giữ focus và chặn submit khi generate; Markdown heading/table/code/link accessibility; source drawer initial focus/width/break-words; document/dialog mobile overflow, loading skeleton và reduced-motion spinner/skeleton. Không thêm dependency/theme switch/PDF viewer/backend change hoặc live generation.
- **Files thay đổi:** `frontend/lib/chat/{scroll,clipboard}.ts`, `frontend/components/chat/{copy-button,code-block,chat-preview,chat-message,chat-composer,citation-content,session-chat}.tsx`, `frontend/components/layout/loading-skeleton.tsx`, `frontend/components/documents/{documents-preview,document-upload,document-actions}.tsx`, `frontend/app/globals.css`, `frontend/tests/ui-polish.test.mjs`, `docs/frontend-accessibility-checklist.md`, FRONTEND_PLAN.md, CURRENT_CHANGE.md, `docs/changelog/phase-02.md` (archive F2-01 nguyên vẹn; giữ 15 entries). Giữ các thay đổi F7-01 có sẵn.
- **Kiểm thử:** `node --test tests/ui-polish.test.mjs` PASS 6/6; full regression PASS 157/157; build/typecheck/lint PASS; offline contract PASS 45 schemas; `git diff --check`/new-file whitespace PASS. Browser manual NOT RUN/BLOCKED, bootstrap failure trước khi mở trang. Không suy luận manual PASS từ unit/SSR/source review; Groq=0, Gemini=0.
- **Tồn đọng / blocker:** Checklist manual ghi expected outcomes và tất cả tương tác chưa chạy; cần kiểm tra mobile, focus trap/return, Escape, clipboard thực, scroll/touch và screen reader khi Browser hoạt động. Chưa đánh dấu COMPLETED.
- **Tiếp theo:** Hoàn tất manual acceptance F7-02; dừng, không tự động triển khai F8-01.

### [2026-10-14] [FRONTEND/F7-01] — Error/health UX

- **Trạng thái:** COMPLETED; F7 IN PROGRESS, F7-02 chưa bắt đầu.
- **Đã thực hiện:** Safe HTTP-status/network/protocol copy dùng cho chat/session/history/document/mutation errors; SSE terminal message được sanitize, giữ code/status/usage/partial text và không replay request. Chat pending user được chốt khi không nhận start; 180s client deadline/abort guard + reader cancellation và terminal-history warning bảo đảm không infinite spinner. Header health check manual GET health/dependencies, typed503 opt-in vẫn giữ503 degraded, reconstruct safe dependency reports, không auto polling/mount request; Groq chưa có health API nên không đoán readiness. Full route reload history trước resend. Không backend/config/dependency/provider changes.
- **Files thay đổi:** `frontend/lib/api/{error-ux,health,client,chat}.ts`, `frontend/lib/health/controller.ts`, chat/session/document controllers, `frontend/components/layout/{app-shell,service-health}.tsx`, chat/session/document UI, `frontend/tests/{error-health,chat-controller,sessions}.test.mjs`, `FRONTEND_PLAN.md`, `CURRENT_CHANGE.md`, `docs/changelog/phase-02.md`; danh sách đầy đủ FRONTEND_PLAN mục27.
- **Kiểm thử:** targeted error/health PASS 12/12; full regression PASS 151/151; build/typecheck/lint (0 warnings)/contract45/diff/new-file whitespace PASS. Fixtures gồm REST422/404/409/429/503/network,503 MongoDB degraded với Qdrant ready, unknown Groq health, post200 SSE error sanitization, duplicate/no-loop và hung stream/session/history/reader deadlines. Browser/live cloud/provider smoke NOT RUN. Groq=0, Gemini=0.
- **Tồn đọng / blocker:** Không blocker implementation. Client deadlines không đảm bảo backend request rollback; phải đọc persisted state trước resend. Health endpoint không check Groq và không xác định mọi provider503; UI giữ unknown, không probe provider hoặc giả sẵn sàng. Browser health/retry/CORS QA chưa chạy.
- **Tiếp theo:** `F7-02` NOT STARTED; dừng, không tự động triển khai.

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










## 4. Lưu trữ nhật ký cũ (archive)

- [Phase 1 + các entry M-03…M-06/P2-01 đã archive](./docs/changelog/phase-01.md)
- [Phase 2 — các entry P2 đã archive](./docs/changelog/phase-02.md)
- [Phase 3–4 — P3-04/P4-01…P4-04 cũ đã archive](./docs/changelog/phase-03-04.md)
