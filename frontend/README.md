# RAG Workspace frontend

Next.js App Router UI cho FastAPI: `/` chuyển đến `/chat`, `/chat/{session_id}` phục hồi history từ backend, `/documents` quản lý tài liệu. Browser gọi API trực tiếp, không có Next API proxy. Các lệnh dưới đây dùng PowerShell, bắt đầu tại project root.

## Chuẩn bị

- Node.js >=20.9 theo tài liệu Next đi kèm; Node24.20.0/npm11.19.0 là môi trường kiểm tra lịch sử (HISTORICAL_EVIDENCE), không phải kiểm tra mới. Manifest hiện khai báo Next16.4.0/React19.3.0; dùng lockfile hiện có, không khởi tạo lại project/cài lại shadcn.
- Python3.10.11 là môi trường lịch sử; backend và một số Node fixtures/contract check cần root `.venv` Windows đang hoạt động. Xem [README backend](../README.md#chạy-backend). Python requirements dùng ranges, chưa có lock tái tạo bit-for-bit. PATH/launcher lỗi không tự chứng minh interpreter đã bị xóa; không repair/ghi đè venv đang dùng theo các lệnh setup này.
- Chrome/Edge cho demo tương tác. Smoke dùng Playwright full Chromium, không cần Codex in-app Browser.

```powershell
Set-Location frontend
npm.cmd ci
# Không ghi đè cấu hình đang dùng.
if (!(Test-Path .env.local)) { Copy-Item .env.example .env.local }
```

Biến frontend duy nhất: `NEXT_PUBLIC_API_BASE_URL`, đặt trong `frontend/.env.local`. Backend đọc root `.env`; chỉ backend được chứa Groq/Gemini/MongoDB/Qdrant secrets. Biến process ưu tiên hơn file: kiểm tra terminal cũ nếu URL không đổi. Thiếu/blank base hiển thị chưa cấu hình, không tự fallback sang backend/mock.

## Kiến trúc frontend

| Thành phần | Vai trò / nguồn |
| --- | --- |
| App Router | [app/page.tsx](app/page.tsx) redirect `/` → `/chat`; `/chat` mở workspace mới, [app/chat/[sessionId]/page.tsx](app/chat/[sessionId]/page.tsx) restore session; [app/documents/page.tsx](app/documents/page.tsx) quản lý documents |
| Workspace và history | [chat-preview.tsx](components/chat/chat-preview.tsx), [session-chat.tsx](components/chat/session-chat.tsx); controller [lib/chat/controller.ts](lib/chat/controller.ts) và [lib/sessions/history.ts](lib/sessions/history.ts) quản lý send/abort/restore/reconciliation |
| API và stream | [lib/api/](lib/api/) gọi FastAPI trực tiếp; [types/](types/) chứa DTOs, [SSE parser](lib/sse/parser.ts) xử lý framing và [stream client](lib/api/chat.ts) validate event/terminal; không có Next API proxy |
| Hooks và tài liệu | [hooks/](hooks/) nối state với React, upload/attachments; [document-preview.tsx](components/chat/document-preview.tsx) đọc local TXT hoặc remote immutable version; [citation-content.tsx](components/chat/citation-content.tsx) render Markdown/source drawer |

Backend RAG, MongoDB/Qdrant và storage contracts thuộc [README root](../README.md#kiến-trúc-hiện-tại).
Đây là Functional Single-user RAG MVP ở mức implementation; không chứng nhận runtime reliability,
semantic quality hoặc production readiness. Authentication/RBAC và multi-tenancy được defer.

## Demo mock — không gọi provider

Terminal A trong `frontend/`:

```powershell
node scripts/qa-mock-api.mjs
```

Terminal B trong `frontend/`:

```powershell
$env:NEXT_PUBLIC_API_BASE_URL = 'http://127.0.0.1:4011/lifecycle'
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

Mở `http://127.0.0.1:3000`. Mock bind loopback4011, dữ liệu chỉ ở RAM; restart mock reset mọi thay đổi. Prefix `/lifecycle` bật upload/version/re-index/delete fixtures, không lưu raw file/embedding thật. New Chat, streaming Markdown/citation, refresh history và session actions dùng mock. Health routes chưa mock: trả404 trong chế độ này, không phải bằng chứng backend hỏng.

Smoke tự động **tự mở và đóng** mock4011 + dev3000. Dừng hai terminal trên trước; script từ chối cổng bận. Chỉ override env process con, không sửa `.env.local`:

```powershell
node node_modules/playwright/cli.js install chromium --no-shell
node scripts/demo-smoke.mjs
```

Smoke kiểm tra startup, redirect, hydrated New Chat, một stream đúng session, refresh không replay, Documents/dialog Escape,375px, browser errors/origin allowlist và giải phóng cổng. Không chụp ảnh/quay video. Next dùng Google Fonts nên compile/build có thể cần network; đây không phải provider call. `npm ci`/browser install chỉ là setup, không cần lặp lại mỗi demo.

## Chạy với FastAPI thật

Đóng mock/dev, mở terminal mới để bỏ mock override. Chuẩn bị root `.env` từ root `.env.example` nếu chưa có, secrets ngoài git. Cần MongoDB Atlas, Qdrant Cloud và local raw storage; dùng namespace demo riêng đã được phép cho mutation.

Terminal A tại project root, dùng existing interpreter:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Lệnh trên chạy từ project root để resolve module/paths rõ ràng. Raw `DOCUMENTS_DIR` tương đối được production factory anchor vào `PROJECT_ROOT`, không phụ thuộc CWD. Setup backend/configuration theo [README root](../README.md#chạy-backend) và [Cấu hình](../README.md#cấu-hình); không xóa/ghi đè venv hiện có. Startup có thể tạo MongoDB indexes.

Terminal B tại project root:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/health/dependencies
Set-Location frontend
$env:NEXT_PUBLIC_API_BASE_URL = 'http://127.0.0.1:8000'
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

`/health` kiểm tra process/config; dependencies chỉ chứng minh MongoDB/Qdrant, **không** Groq/Gemini readiness. Chat/query rewriting gọi Groq; query/upload/version/re-index có thể gọi Gemini. F8-02 đã hết4 Gemini requests được duyệt: **không rerun live flow theo approval cũ**. Hướng dẫn không cấp thêm budget. [Live runbook/evidence](../docs/frontend-controlled-live-e2e.md).

## CORS

FastAPI hiện allow đúng `http://localhost:3000` và `http://127.0.0.1:3000`; credentials=false, GET/POST/PUT/PATCH/DELETE, request header Content-Type. OPTIONS do middleware xử lý. Hostname/cổng/scheme khác là origin khác;3001/3100/HTTPS/deployment origin chưa được allow. Không dùng `no-cors` che lỗi.

Backend thật đang chạy, kiểm tra read-only/preflight, không gửi question:

```powershell
curl.exe -i -H "Origin: http://localhost:3000" http://127.0.0.1:8000/sessions
curl.exe -i -H "Origin: http://localhost:3000" http://127.0.0.1:8000/documents
curl.exe -i -X OPTIONS http://127.0.0.1:8000/chat/stream -H "Origin: http://localhost:3000" -H "Access-Control-Request-Method: POST" -H "Access-Control-Request-Headers: content-type"
```

GET thành công cần ACAO khớp Origin; preflight cần200 + ACAO + allowed POST/Content-Type. HTTP200 thiếu ACAO vẫn bị browser chặn. Lặp với Origin127.0.0.1:3000 khi dùng hostname này. Không ghi health PASS khi503/unavailable. Mock có CORS loopback riêng, không chứng minh CORS FastAPI.

## Chat và session

- New Chat mở workspace chưa có session; lần submit hợp lệ tạo session rồi gửi question qua SSE.
  Controller chặn overlapping local submit. `start` gắn durable session/message/request IDs;
  metadata mang ordered sources, delta được nối nguyên nội dung, terminal cập nhật status/usage.
- Sau terminal, client đọc history để so ID/request/role/content/status và các trường persistence;
  mismatch/load lỗi hiển thị cảnh báo, giữ nội dung hiện tại, không tự gửi lại generation.
  URL session có thể được cập nhật sau lượt chat/xử lý draft, không được coi đổi URL là xác nhận commit.
- Mở `/chat/[sessionId]` hoặc refresh load paginated history; state loading/error/empty tách biệt.
  Session components/controllers dùng keyed instances và abort để hạn chế late callbacks.
  Pagination không phải snapshot server, nên concurrent updates vẫn có thể gây restore warning.
- Stop hoặc switch/unmount abort local request/wait. Điều đó không chứng minh server đã hủy hay chưa
  commit; có thể cần reload để kiểm tra durable outcome. Nếu chỉ nhận whitespace rồi abort trước
  terminal, local PARTIAL có thể đổi thành FAILED khi restore theo backend meaningful-content rule.
- Session actions hỗ trợ rename/delete; delete trong generation có thể bị HTTP409. Hard crash có thể
  để stale guard; chưa có automatic lease recovery. Không có auto-resume/replay/retry generation.
- Session mặc định ALL_ACTIVE; internal SELECTED_DOCUMENTS không đồng nghĩa có public scope setter
  hay UI editor (NOT_IMPLEMENTED).

Nguồn: [ChatController](lib/chat/controller.ts), [history controller](lib/sessions/history.ts).
Server sequencing/status/error contracts ở [APIs root](../README.md#apis) và
[SSE lifecycle](../README.md#post-chatstream).

## Documents, attachments và preview

`/documents` hỗ trợ upload, version update, re-index, delete. Ingestion nhận PDF/TXT/MD/Markdown/XLSX;
update/re-index tạo immutable version mới. Delete unpublish trước vector cleanup, giữ raw/audit;
HTTP202 là cleanup pending và có thể retry có chủ đích. Xem [server lifecycle](../README.md#document-ingestion-và-immutable-versions).

Trong composer, chọn file bắt đầu upload/index. Draft chỉ ready để gửi khi upload result INDEXED
và `activated=true`; pending/error không được coi đã attach thành công. Gửi IDs `document_id` +
`version_id` trong persistent session, tối đa 20 references không trùng pair. Backend kiểm tra
ownership/nondeleted document và INDEXED referenced version, rồi persist filename phía server.
History phục hồi reference đó để mở đúng version, không tự đổi sang active version mới.

Attachment **không tự giới hạn retrieval scope**: version cũ được attach/preview khác với current
active version dùng cho retrieval theo session. Remove draft attachment chỉ bỏ draft và abort local
wait; không delete stored document và không bảo đảm server upload đã bị hủy. Delete document là
thao tác riêng; document deleted/raw unavailable có thể làm preview reference cũ không dùng được.

| Preview | Hành vi hiện tại |
| --- | --- |
| Local TXT | Đọc tối đa 256 KiB cho preview; file gốc upload không bị cắt |
| Remote TXT/MD/Markdown | GET đúng document/version, `kind=text`; giới hạn 256 KiB, hỗ trợ UTF-8/UTF-16 BOM |
| Remote XLSX | Chờ upload/index xong; `kind=excel` với sheets/columns/rows giới hạn; công thức hiển thị literal |
| PDF | Ingest/attach được, content preview/PDF viewer chưa triển khai |

Preview sheet resize theo bounds/viewport; width preference chỉ lưu trong tab bằng sessionStorage
với memory fallback nếu storage bị chặn, không persist vào MongoDB hoặc bảo đảm giữa browser sessions.
Đây là attachment preview, không phải citation-to-content opening.
Nguồn: [attachment hook](hooks/use-chat-attachments.ts), [preview](components/chat/document-preview.tsx),
[resize panel](components/chat/document-preview-sheet.tsx). Request/response và endpoint đầy đủ ở
[Attachments và version preview](../README.md#attachments-và-version-preview).

## Citations và sources

Live `[n]` chỉ resolve theo ordered source metadata của đúng assistant message, không theo
`chunk_index` hoặc array citations đã lưu. Mapper kiểm tra ordinal/UUID/page eligibility;
invalid/out-of-range/missing metadata không tạo fake source link. Đây là identity validation,
không bảo đảm answer được source hỗ trợ về nghĩa.

Refresh/history trả saved citation identities nhưng không có complete ordered sources; UI dùng
fallback source cards không tự đánh số lại `[1]` theo thứ tự citations. Raw marker mapping có thể
nhận `[n]` trong code/link trong khi Markdown button transformer bỏ qua các vùng đó; số cards
không phải phép đo semantic support hoặc số citation buttons.

Source drawer nhóm tài liệu/trang và hiển thị document/version/chunk IDs; hiện **chưa mở nội dung
tài liệu hoặc citation-to-content link**. Attachment preview ở trên là luồng riêng; không có PDF
viewer hay bảo đảm exact ordinal restoration sau refresh. Xem
[source mapper](lib/chat/source-mapper.ts), [citation panel](lib/chat/citation-panel.ts),
[citation renderer](components/chat/citation-content.tsx) và [server identity contract](../README.md#attachments-và-version-preview).

## Production/runtime assumptions

Trong `frontend/`, dùng URL browser thực sự truy cập được; ví dụ này chỉ dành demo local:

```powershell
$env:NEXT_PUBLIC_API_BASE_URL = 'http://127.0.0.1:8000'
npm.cmd run build
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run start -- --hostname 127.0.0.1 --port 3000
```

Đặt public API URL **trước build**; `NEXT_PUBLIC_*` bị đóng vào artifact, đổi env lúc start không sửa bundle. Sau `build:e2e`, build thường lại với base đúng trước demo thật (E2E artifact trỏ mock4011). Khi deploy cần public HTTPS API URL và exact frontend origin ở FastAPI qua thay đổi deployment được duyệt; remote browser không dùng loopback của server, HTTPS UI gọi HTTP API có thể bị mixed-content block.

Hiện giả định Node server cho Next + process FastAPI riêng, chưa cấu hình static export/deployment adapter/proxy/auth/tenant isolation. Backend cần cloud/provider connectivity, Atlas access list phù hợp và raw storage bền vững; local raw không tự chia sẻ giữa replicas. Reverse proxy phải forward SSE không buffering và có timeout phù hợp. `STREAM_TIMEOUT_SECONDS` (default120s) giới hạn provider iteration, không bao phủ preparation/close/persistence toàn request; chưa nghiệm thu một hosting/proxy cụ thể. Không chạy dev/build đồng thời trên cùng `.next`.

## Checks và giới hạn

### Test tooling

Chạy từ `frontend/` sau setup; đây là hướng dẫn, không phải kết quả vừa chạy:

```powershell
npm.cmd test
npm.cmd run test:contract
npm.cmd run build:e2e
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run test:e2e
```

Các Node fixtures/mocks và mock E2E trên dùng0 live provider calls theo cấu hình tooling; không áp
dụng cho live backend/evaluation commands. Một số Node tests gọi Python; contract export dùng root
`.venv/Scripts/python.exe` Windows, chặn network và không chạy FastAPI lifespan. Vì vậy npm test
không phải toàn bộ JavaScript thuần hoặc bằng chứng backend cloud hiện hoạt động.

`build:e2e` ghi `.next` trỏ mock4011; Playwright dùng3100, loopback mocks và per-test allowlist,
có thể ghi `.playwright-tmp`, test results/report/failure trace/screenshot. Typecheck incremental
cũng có thể ghi cache; các lệnh không phải tất cả read-only. Demo smoke riêng không capture ảnh/video.
[Demo checklist/kết quả](../docs/frontend-demo-readiness.md), [automated](../docs/frontend-automated-tests.md),
[functional QA](../docs/frontend-functional-qa.md), [accessibility](../docs/frontend-accessibility-checklist.md).

### Giới hạn và evidence lịch sử

Chat/Stop/history limits ở [Chat và session](#chat-và-session); preview và citations có giới hạn riêng
ở [workflow documents](#documents-attachments-và-preview) và [source drawer](#citations-và-sources).
Chưa có Edit/Regenerate/Delete Message. Manual AT/contrast/zoom/touch và9 high advisories là trạng thái
ghi nhận trong QA lịch sử, không phải scan/test mới; xem runbooks ở trên. Các kết quả demo/test là
HISTORICAL_EVIDENCE, không phải current PASS hoặc production/security clearance. Không công bố
observations 0C-A thành official baseline. [Assessment](../RAG-CODEBASE-ASSESSMENT-0C.md) giữ phân loại
finding gốc; runtime reliability/semantic quality chưa được chứng nhận. Backend evaluation và giới hạn
benchmark ở [README root](../README.md#evaluation).
