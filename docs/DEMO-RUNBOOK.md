# Demo Runbook: RAG Workspace & HR Demo Portal

Tài liệu này hướng dẫn quy trình chạy thử và trình diễn (demo) hệ thống theo 2 chế độ:

1. **Chế độ 1: Provider-Free Mock Mode** (không cần API key Groq/Gemini, không cần MongoDB/Qdrant).
2. **Chế độ 2: Local / Docker Full-Stack Demo** (đầy đủ FastAPI, ARQ Worker, Next.js Standalone, dữ liệu giả lập nạp an toàn vào collection riêng `rag_documents_demo`).

---

## 1. Chế độ 1: Provider-Free Mock Mode (Offline 100%)

Dùng khi trình diễn nhanh giao diện Chat, Quản lý tài liệu, Document Scope Selector và HR Portal mà không phát sinh chi phí hay phụ thuộc mạng.

### Chạy thủ công để tương tác trên trình duyệt
Từ thư mục `frontend/`:

```powershell
# Terminal A: khởi động in-memory Mock API server trên 127.0.0.1:4011
Set-Location frontend
node scripts/qa-mock-api.mjs

# Terminal B: khởi động Next.js dev server nối vào mock /lifecycle
Set-Location frontend
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:4011/lifecycle"
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

Mở `http://127.0.0.1:3000/chat` hoặc `http://127.0.0.1:3000/hr` để trình diễn. Toàn bộ dữ liệu nằm trong RAM của mock server và reset khi dừng tiến trình.

### Chạy kịch bản Demo Smoke tự động
```powershell
Set-Location frontend
node scripts/demo-smoke.mjs
```

Script tự khởi động `qa-mock-api.mjs` và `next dev`, kiểm tra luồng tạo phiên `/chat`, 1 lượt SSE, reload giữ lịch sử, `/documents`, và `/hr` + `HrChatbotWidget`, sau đó tắt sạch tiến trình và kiểm tra các cổng `3000`, `4011` đã được giải phóng.

---

## 2. Chế độ 2: Local / Docker Full-Stack Demo (Dữ liệu Giả Lập Cô Lập)

### Bước 1: Chuẩn bị biến môi trường
Tại thư mục gốc `rag-demo/`:

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
if (!(Test-Path frontend\.env.local)) { Copy-Item frontend\.env.example frontend\.env.local }
```

Điền tối thiểu `GROQ_API_KEY`, `EMBEDDING_API_KEY` (Google AI Studio), và:
- Nếu dùng Cloud (MongoDB Atlas & Qdrant Cloud): điền `MONGODB_URI`, `MONGODB_DB_NAME`, `QDRANT_URL` (`https://...`), `QDRANT_API_KEY`.
- Nếu dùng Docker profile `local-infra` (Mongo 7 + Qdrant local trên máy): đặt `QDRANT_ALLOW_INSECURE_HTTP=true`, `QDRANT_URL=http://qdrant:6333`, `MONGODB_URI=mongodb://mongo:27017`.

### Bước 2: Kiểm tra trước (Dry-run) và Nạp dữ liệu Demo an toàn
Script `backend/scripts/seed_demo_workspace.py` mặc định chạy ở chế độ `--dry-run` (không ghi dữ liệu), chỉ dùng tài liệu kỹ thuật công khai và dữ liệu nhân sự giả lập (không có PII thật).

```powershell
# 1. Dry-run (mặc định): kiểm tra 7 file mẫu, checksum SHA-256 và an toàn XLSX (0 side-effects)
.\.venv\Scripts\python.exe backend/scripts/seed_demo_workspace.py

# 2. Thực thi nạp dữ liệu demo vào collection/DB/thư mục cô lập riêng
#    Mặc định: rag_documents_demo / rag_demo_workspace / ./data/documents_demo
#    Script sẽ chặn nếu truyền QDRANT_COLLECTION=rag_documents mà thiếu --allow-primary-collection
.\.venv\Scripts\python.exe backend/scripts/seed_demo_workspace.py --apply --qdrant-collection rag_documents_demo --mongodb-db-name rag_demo_workspace
```

> Lưu ý: Để Backend đọc đúng bộ dữ liệu demo vừa nạp, đặt `QDRANT_COLLECTION=rag_documents_demo`, `MONGODB_DB_NAME=rag_demo_workspace`, `DOCUMENTS_DIR=./data/documents_demo` trong `.env`. Nếu muốn trình diễn Agentic + Excel SQL (`run_sql`), bật thêm `TOOL_USE_ENABLED=true`, `AGENTIC_MODE_ENABLED=true`, `EXCEL_PARQUET_INGESTION_ENABLED=true`, `EXCEL_SQL_ENABLED=true`.

### Bước 3: Khởi động Stack qua Docker Compose (hoặc chạy trực tiếp)
```powershell
# Cách A: Chạy với MongoDB Atlas & Qdrant Cloud (+ Redis cho ARQ/RateLimit)
docker compose up --build

# Cách B: Chạy hoàn toàn cục bộ với Redis, Qdrant và Mongo trong Docker
docker compose --profile local-infra up --build
```

Sau khi các container ở trạng thái healthy:
- Frontend: `http://127.0.0.1:3000` (`/chat`, `/documents`, `/hr`, `/hr/documents`, `/hr/guide`)
- Backend API & Swagger: `http://127.0.0.1:8000/docs`
- Healthcheck: `http://127.0.0.1:8000/health/dependencies`
- Prometheus metrics: `http://127.0.0.1:8000/metrics`

---

## 3. Kịch bản Trình diễn Gợi ý

1. **Quản lý tài liệu & Preview (`/documents`)**:
   - Kiểm tra danh sách 7 tài liệu demo (`hr_employees_mock.xlsx`, `hr-leave-policy.md`, `security-incident-sop.txt`, `enterprise_it_knowledge_base.xlsx`, `qdrant.md`, `chunking.md`, `llm-embedding.md`).
   - Mở preview nội dung file TXT/MD và bảng XLSX (giữ nguyên giá trị literal của công thức).
2. **Scope Selector & Hỏi đáp RAG có trích dẫn (`/chat`)**:
   - Tạo phiên mới, thử giới hạn phạm vi bằng `Chọn tài liệu` (`SELECTED_DOCUMENTS` vs `ALL_ACTIVE`).
   - Đặt câu hỏi về quy chế nghỉ phép (`"Nhân viên chính thức đủ 12 tháng có bao nhiêu ngày phép năm và hạn dùng phép chuyển là ngày nào?"`) -> kiểm tra SSE streaming theo từng delta và drawer trích dẫn `[1]`.
   - Thử câu hỏi ngoài phạm vi (`"Giá vàng SJC hôm nay là bao nhiêu?"`) -> xác nhận hệ thống từ chối trả lời thay vì bịa thông tin.
3. **Agentic Mode & DuckDB `run_sql` trên Excel (`/chat`)**:
   - Hỏi câu thống kê trên `hr_employees_mock.xlsx`: `"Tổng quỹ lương cơ bản hàng tháng của phòng Kỹ thuật & Sản phẩm là bao nhiêu triệu đồng?"` (đáp án đúng trên bảng `nhansu` là `90` triệu; toàn công ty là `234` triệu).
4. **HR Demo Portal (`/hr`)**:
   - Xem KPI & biểu đồ nhân sự giả lập (`HR_ANALYTICS_FIXTURE`) kèm khối **Kho tri thức RAG (Dữ liệu thực từ API)**.
   - Chuyển sang `/hr/documents` để lọc theo danh mục hiển thị, sau đó mở **Trợ lý HR** (`HrChatbotWidget`), hỏi đa lượt xuyên từ `/hr/documents` sang `/hr/guide` và đối chiếu để thấy phiên HR tách biệt với `/chat`.
5. **Observability (`/metrics`, Logs & Langfuse)**:
   - Mở `http://127.0.0.1:8000/metrics` để kiểm tra `rag_http_requests_total`, `rag_chat_turns_total`, `rag_chat_ttft_seconds`, `rag_stage_duration_seconds`, `rag_llm_tokens_total`.
   - Kiểm tra stdout backend log JSON 1 dòng kèm `request_id` (tất cả secret/URI bị che). Nếu bật `LANGFUSE_ENABLED=true`, kiểm tra trace trên Langfuse với payload mặc định đã lược bỏ nội dung nhạy cảm (`LANGFUSE_TRACE_CONTENT_ENABLED=false`).

---

## 4. Lưu ý Reverse Proxy cho SSE

Nếu đặt Nginx, Caddy hoặc load balancer phía trước FastAPI Backend, cần tắt buffering cho endpoint `/chat/stream` để token streaming được đẩy ngay về trình duyệt (FastAPI đã tự gắn header `X-Accel-Buffering: no`, nhưng ở phía Nginx vẫn nên cấu hình tường minh `proxy_buffering off;` cho location `/chat/stream`).
