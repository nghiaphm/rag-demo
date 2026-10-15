# F8-03 — Demo readiness (2026-10-15)

**COMPLETED cho scope runbook + reproducible local demo.** Không phải full release/security/accessibility clearance. F7-02/F7-03-05 vẫn IN PROGRESS; không chấp nhận debt thay người dùng. Không có screenshot/video được yêu cầu hoặc tạo trong task này.

## Entry points và cấu hình

- [Frontend README](../frontend/README.md): setup, mock/real dev, production build/start, CORS header probes, runtime/deployment assumptions, troubleshooting và test commands.
- [Frontend env example](../frontend/.env.example): duy nhất public API base, không secrets; `.gitignore` chỉ mở đúng `.env.example`, `.env.local` vẫn ignored. Root `.env.example` dành backend giữ nguyên.
- [Demo smoke](../frontend/scripts/demo-smoke.mjs): khởi động Next dev mới và RAM-only mock hiện có, giới hạn browser request origins, kiểm tra UI và teardown. Không import backend/provider hoặc dùng live namespace.
- [F8-02 live evidence](./frontend-controlled-live-e2e.md):3-turn/health/citation/document/cleanup đã nghiệm thu ở task trước, không chạy lại trong F8-03. Budget Gemini của approval cũ đã hết.

Audit dựa source hiện tại: `frontend/package.json`, `app/{layout,chat/page,chat/[sessionId]/page,documents/page}.tsx`, `next.config.ts`, API clients/controllers, mock/lifecycle server; FastAPI `main.py`, `config.py`, documents router/loader. Đọc tài liệu Next đi kèm `node_modules/next/dist/docs` về env/build/deploy. Không thêm proxy/env loader/library, không sửa UI, RAG, API/SSE/schema hoặc dependency.

## Kết quả thực chạy

Windows/PowerShell, Node24.20.0/npm11.19.0, existing dependencies và Python3.10.11 environment:

| Check | Kết quả F8-03 |
| --- | --- |
| `node scripts/demo-smoke.mjs` | **PASS7/7, hai lần chạy liên tiếp sau sửa teardown harness**, mỗi lần fresh owned `next dev`3000 + mock4011, browser Chromium headless,0 live calls. |
| Dev smoke coverage | `/chat`200; `/`→`/chat`; hydrated New Chat→UUID route;1 SSE POST đúng session; assistant Markdown + terminal unlock; reload khôi phục đúng1 assistant/question không replay; Documents/upload dialog/Escape;375px no page horizontal overflow; no uncaught page errors/unexpected HTTP origin. |
| Teardown | **PASS** cả hai lần: own browser/dev/mock closed, bind probes xác nhận3000/4011 free. Mock RAM reset khi đóng. Không chạm backend/user server. |
| `npm.cmd test` | **PASS198/198**, skipped0. Initial sandbox run FAIL vì không đọc được external Python mà `.venv` tham chiếu; rerun được cấp quyền truy cập existing interpreter PASS, không sửa environment/test assertions. |
| `npm.cmd run build` | **PASS7/7 prerender**, process-only `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000` theo example. Normal build, không phải mock `build:e2e`. Không start backend hoặc gọi provider. |
| `npm.cmd run typecheck`, `npm.cmd run lint` | **PASS / PASS0 warnings**. |
| `npm.cmd run test:contract` | **PASS45 schemas**, offline/network disabled, dùng existing interpreter. |
| `node scripts/verify-production-delivery.mjs` | **PASS** `/chat`, `/chat/{fixture UUID}`, `/documents` HTTP200/main content + client JS200; owned ephemeral server stopped. HTTP-only, không phải real API/browser live acceptance. |
| `node --check scripts/demo-smoke.mjs` | **PASS**. |
| Example/ignore/local links/whitespace/log archive | **PASS**, `.env.example` trackable, `.env.local` ignored; local relative doc targets exist; current log15 entries và archive nguyên vẹn; `git diff --check` + new-file whitespace PASS. |
| `npm ci`, Chromium install | **NOT RUN** lại: hướng dẫn setup, smoke dùng dependencies/browser đã cài. Không claim clean-room reinstall hoặc cross-platform verification. |
| Full44 mock E2E, broad backend suite, npm audit | **NOT RERUN**; kết quả task trước là evidence lịch sử, không tính là lần chạy F8-03. |
| Live FastAPI/cloud/CORS/provider, human manual QA | **NOT RUN** trong task này;0 Groq/Gemini calls,0 live mutations. CORS commands được đối chiếu middleware hiện có, không giả vờ đã chạy trên backend thật lần này. |

Lần thử smoke đầu có đủ7 UI checks nhưng exit1 vì harness báo teardown failed; không tính lượt này PASS. Điều chỉnh harness chờ child exit, có fallback terminate đúng owned PID, kiểm tra teardown/browser và probe port trước khi in tổng PASS; hai lượt sau exit0. Không có evidence lỗi application nên không sửa UI. Không xóa `.next`/node_modules/env/user data; “fresh startup” là process mới với environment override xác định, không phải xóa mọi cache. Normal build hiện tại nhắm localhost8000; muốn chạy mock production E2E phải `build:e2e` lại.

## Checklist demo có thể lặp lại

Các dòng dưới là runbook cho người trình diễn. **PASS trước đó** chỉ được dùng khi có report dẫn kèm, không phải human manual acceptance mới trong task này.

| Bước | Thao tác / kết quả mong đợi | Evidence hiện có |
| --- | --- | --- |
| 1. Chọn mode | Dùng mock4011/lifecycle để trình diễn không phí provider. Dừng cổng xung đột, không cho Next tự đổi3001. Live phải có namespace riêng và budget mới được duyệt. | Dev smoke PASS; live task trước theo F8-02. |
| 2. Startup | Theo README, `/`→Chat; sidebar/composer hydrated, không Suspense/runtime error. Backend thật thì health200 + dependencies200; health không chứng minh provider. | Fresh dev browser và production HTTP PASS. Live health NOT RERUN. |
| 3. Session + turns | New Chat, gửi2–3 câu; session UUID không cần nhập, sidebar/URL đúng, messages không trộn. | F8-03 một mock turn; [functional QA](./frontend-functional-qa.md) và F8-02 có3-turn evidence. |
| 4. Refresh/citations | Refresh giữ đúng session/history; citation live đúng assistant/file/page; lịch sử thiếu ordered metadata có fallback rõ. PDF page0 hiển thị Trang1. | F8-03 history PASS; [chat acceptance](./chat-actions-browser-acceptance.md), F8-02 citations PASS. |
| 5. Stop/recovery/error | Gửi mock thường rồi Stop; partial text giữ lại, spinner kết thúc, không retry tự động. Mock `[error]`/`[disconnect]` kiểm tra error/recovery. | Prior functional/chat automated evidence; NOT RERUN riêng trong dev smoke. |
| 6. Session actions | Menu keyboard, rename, cancel delete, confirm current-session delete→Chat;409 khi remote stream không replay. | [Session acceptance](./session-actions-browser-acceptance.md), NOT RERUN đầy đủ F8-03. |
| 7. Documents | Trong mock lifecycle upload synthetic TXT, xem status và active version riêng; new version/re-index/confirm delete.202 là pending; retry cleanup có chủ đích, raw retention text đúng. | [Document acceptance](./document-actions-browser-acceptance.md). F8-03 route/dialog Escape PASS; không repeat live ingestion. |
| 8. Mobile/keyboard |375px sidebar/dialog/citation, Tab/Shift+Tab/Escape/focus return; người trình diễn tự kiểm zoom200%/AT/contrast/touch theo checklist. | Scoped browser suites trước đó; F8-03 chỉ documents375px overflow/Escape. Human checks vẫn NOT RUN. |
| 9. Cleanup | Ctrl+C cả dev/mock, mở terminal mới khi chuyển base. Mock restart mất RAM. Live soft-delete không đồng nghĩa raw đã xóa; chỉ cleanup exact-owned test namespace theo approved runbook. | F8-03 owned dev/mock ports free; F8-02 independent cloud/raw cleanup PASS. |

Nếu smoke thiếu Chromium: chạy install `--no-shell` theo README (tránh optional Headless Shell tải vào C: khi thiếu dung lượng). Nếu cổng bận hoặc `.next/dev/lock` thuộc phiên khác, dừng đúng phiên mình quản lý; không kill hàng loạt Node hoặc xóa cache khi dev/build còn chạy. Nếu API base sai: kiểm tra `.env.local`/process override, restart dev hoặc rebuild production. Nếu403/preflight/CORS: xác minh exact origin và ACAO bằng probes; không sửa UI/disable browser security.

## Giới hạn và release gate còn mở

- F7 human screen-reader/contrast/desktop zoom200%/real touch chưa chạy/waive.9 high npm advisories từ lần audit trước chưa resolve/accept; không chạy audit fix hoặc suy ra advisories vẫn có số lượng mới từ một audit chưa chạy.
- Không có authentication/authorization/tenant boundary hoàn chỉnh; demo local/scoped, chưa chứng nhận public multi-user deployment. Chưa kiểm proxy buffering/timeout, HTTPS/CORS deployment matrix, multi-replica raw storage hay fresh-machine install.
- History API persist citations nhưng thiếu ordered source positions; fallback hiển thị sources, không chắc `[n]` mapping sau refresh. Không PDF viewer/raw download endpoint giả.
- Refresh/navigation không resume stream; PENDING/STREAMING history là snapshot, không live loading. Deferred URL/recovery không bảo đảm request có thể replay an toàn, nên retry chủ động.
- Backend support `.pdf,.md,.markdown,.txt,.xlsx`, chưa có maximum byte limit được định nghĩa; không bịa size limit. Demo dùng TXT rất nhỏ. Status document và active version là hai trạng thái khác nhau; version mới fail giữ version active cũ.
- Document DELETE soft-delete/raw retention; session DELETE tombstone + related messages hard-delete theo contract. Cleanup cloud cần ownership guard, không xóa namespace mặc định. Không có Edit/Regenerate/Delete Message.
- Concurrent multi-session incident vẫn **NOT REPRODUCED**, không tuyên bố FIXED từ smoke tuần tự. BUG-STREAM-001 đã FIXED ở task trước, không sửa lại tại đây.

F8-01/02/03 scoped tasks hoàn tất; full demo/release gate **chưa** tự chuyển PASS khi F7 manual/security debt còn mở. Dừng sau F8-03, không deploy/publish hoặc chạy thêm live provider.
