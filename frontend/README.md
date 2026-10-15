# RAG Workspace frontend

Next.js App Router UI cho FastAPI: `/` chuyển đến `/chat`, `/chat/{session_id}` phục hồi history từ backend, `/documents` quản lý tài liệu. Browser gọi API trực tiếp, không có Next API proxy. Các lệnh dưới đây dùng PowerShell, bắt đầu tại project root.

## Chuẩn bị

- Node.js >=20.9 theo tài liệu Next đi kèm; đã kiểm tra Node24.20.0/npm11.19.0, Next16.4.0/React19.3.0. Dùng lockfile hiện có, không khởi tạo lại project/cài lại shadcn.
- Python3.10.11 + root `.venv` cho backend và contract/unit fixtures; xem [README backend](../README.md#chạy-backend). Python requirements dùng ranges, chưa có lock tái tạo bit-for-bit.
- Chrome/Edge cho demo tương tác. Smoke dùng Playwright full Chromium, không cần Codex in-app Browser.

```powershell
Set-Location frontend
npm.cmd ci
# Không ghi đè cấu hình đang dùng.
if (!(Test-Path .env.local)) { Copy-Item .env.example .env.local }
```

Biến frontend duy nhất: `NEXT_PUBLIC_API_BASE_URL`, đặt trong `frontend/.env.local`. Backend đọc root `.env`; chỉ backend được chứa Groq/Gemini/MongoDB/Qdrant secrets. Biến process ưu tiên hơn file: kiểm tra terminal cũ nếu URL không đổi. Thiếu/blank base hiển thị chưa cấu hình, không tự fallback sang backend/mock.

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

Chạy từ root giữ `DOCUMENTS_DIR=./data/documents` đúng root; nếu đổi CWD, dùng raw path tuyệt đối. Với máy mới, tạo venv Python3.10 phù hợp rồi cài `backend/requirements.txt` theo README root; không xóa/ghi đè venv hiện có. Startup có thể tạo indexes.

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

Hiện giả định Node server cho Next + process FastAPI riêng, chưa cấu hình static export/deployment adapter/proxy/auth/tenant isolation. Backend cần cloud/provider connectivity, Atlas access list phù hợp và raw storage bền vững; local raw không tự chia sẻ giữa replicas. Reverse proxy phải forward SSE không buffering và có timeout phù hợp `STREAM_TIMEOUT_SECONDS` (default120s); chưa nghiệm thu một hosting/proxy cụ thể. Không chạy dev/build đồng thời trên cùng `.next`.

## Checks và giới hạn

```powershell
npm.cmd test
npm.cmd run test:contract
npm.cmd run build:e2e
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run test:e2e
```

Mặc định0 live provider calls. Contract fixtures dùng root `.venv` Windows. Production E2E dùng3100 và per-test mock allowlist; cấu hình QA trước có thể lưu failure trace/screenshot, khác demo smoke không capture. [Demo checklist/kết quả](../docs/frontend-demo-readiness.md), [automated](../docs/frontend-automated-tests.md), [functional QA](../docs/frontend-functional-qa.md), [accessibility](../docs/frontend-accessibility-checklist.md).

History chỉ persist citations, không có ordered metadata để khôi phục chắc chắn ordinal `[n]`: UI dùng fallback, không tạo link giả/PDF viewer. Stream URL có thể cập nhật sau terminal/persistence verification; refresh/unmount không resume/retry generation. DELETE document soft-delete giữ raw/audit;202 là cleanup pending, retry có chủ đích. Chưa có Edit/Regenerate/Delete Message. Human AT/contrast/zoom/touch và9 high advisories còn mở; demo PASS không phải production/security clearance.
