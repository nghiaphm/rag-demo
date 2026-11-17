# HR Portal Demo — Implementation Change Log

Tài liệu này lưu lại toàn bộ lịch sử thay đổi, quyết định thiết kế, danh sách file thêm mới/chỉnh sửa và kết quả kiểm thử qua từng Phase khi xây dựng HR Portal Demo trên nền RAG Workspace.

---

## Baseline (Pre-Phase H1) — Trạng thái trước khi bắt đầu
- **Thời điểm**: 2026-11-16 (Nhánh `master` commit `e4bcfc5`, tạo nhánh làm việc `feat/hr-portal-demo`)
- **Kiến trúc hiện hữu**:
  - **RAG Workspace Frontend** (Next.js `16.4.0` App Router, React `19.3.0`, Tailwind CSS v4, Base UI): `/`, `/chat`, `/chat/[sessionId]`, `/documents`.
  - Lõi nghiệp vụ & giao tiếp tách khỏi React UI: `lib/chat/` (`ChatController`), `lib/documents/` (`DocumentsController`, `UploadController`, `text-preview`), `lib/sessions/`, `lib/sse/`, `lib/api/`, `hooks/`.
  - Kiểm thử đối xứng DTO tự động qua `frontend/tests/verify-api-contract.mjs` và Mock Server `frontend/scripts/qa-mock-api.mjs`.
  - Backend đã hoàn thành Phase 1–4 + Phase 5.1 (Async Ingestion) + Phase 5.2 (Document Scope Selector), chưa có trường `category` cho HR và chưa có HRIS / aggregate analytics endpoints.
- **Trạng thái kiểm thử Baseline** (tại `master` `e4bcfc5`):
  - Backend: `tests/architecture` **9/9 PASS**, `tests/unit` **287/287 PASS**, `tests/integration` **154/154 PASS**.
  - Frontend: `test:contract` **PASS** (`55 REST/SSE/health schemas`), `typecheck` **PASS**, `lint` **PASS**, `npm.cmd test` **214/214 PASS**.

---

## Phase H1 – Routing Isolation, HR Shell & Domain Foundation
> **Trạng thái**: Hoàn thành  
> **Phạm vi**: `Route Groups` · `HrShell` · `HrChatbotProvider` · `HR Domain Logic`

### Thay đổi đã thực hiện
- **H1.1 Route Group Separation & HR Navigation Shell**:
  - Tinh gọn `frontend/app/layout.tsx` chỉ giữ `<html>`, `<body>`, Geist fonts, metadata và skip-link; giữ `frontend/app/page.tsx` redirect `/` $\rightarrow$ `/chat`.
  - Tạo `frontend/app/(workspace)/layout.tsx` bọc `<AppShell>` và di chuyển `chat/`, `documents/` vào `(workspace)/` bảo toàn nguyên vẹn URL `/chat`, `/chat/[sessionId]`, `/documents`; bổ sung link chuyển sang `HR Demo Portal` (`/hr`) trong `SidebarFooter` của `frontend/components/layout/app-shell.tsx`.
  - Tạo `frontend/types/hr.ts` tách biệt hoàn toàn với 4 file OpenAPI DTO (`api`, `chat`, `document`, `sessions`).
  - Tạo `HrChatbotProvider` + `useHrChatbot` (`frontend/components/hr/layout/hr-chatbot-provider.tsx`) chỉ quản lý state UI/ngữ cảnh (`isOpen`, `activeSessionId`, `pageContext`, `draftPrompt`).
  - Tạo `HrHeaderUser` (`frontend/components/hr/layout/hr-header-user.tsx`) và `HrShell` (`frontend/components/hr/layout/hr-shell.tsx`) với sidebar điều hướng `/hr`, `/hr/documents`, `/hr/guide` highlight active route (`aria-current="page"`), thông tin người dùng Demo, nút quay về RAG Workspace (`/chat`) và launcher Trợ lý HR.
- **H1.2 HR Fixtures & Pure Domain Logic (`lib/hr/`)**:
  - Tạo `frontend/fixtures/hr-analytics.ts` (184 nhân sự mô phỏng qua 6 phòng ban và 4 trạng thái hợp đồng + 4 KPI cards) và `frontend/fixtures/hr-guide.ts` (4 phần hướng dẫn + 6 câu hỏi mẫu).
  - Tạo `frontend/lib/hr/analytics.ts` (`summarizeDepartmentShares`, `summarizeContractStatuses`, `summarizeKnowledgeBaseDocuments`) và `frontend/lib/hr/document-categories.ts` (`classifyHrDocument`, `countDocumentsByCategory`, `filterHrDocuments`).

### Files thêm mới / chỉnh sửa
- **Thêm mới**: `frontend/app/(workspace)/layout.tsx`, `frontend/app/hr/layout.tsx`, `frontend/types/hr.ts`, `frontend/components/hr/layout/hr-chatbot-provider.tsx`, `frontend/components/hr/layout/hr-header-user.tsx`, `frontend/components/hr/layout/hr-shell.tsx`, `frontend/fixtures/hr-analytics.ts`, `frontend/fixtures/hr-guide.ts`, `frontend/lib/hr/analytics.ts`, `frontend/lib/hr/document-categories.ts`, `frontend/tests/hr-shell.test.mjs`.
- **Chỉnh sửa / Di chuyển**: `frontend/app/layout.tsx`, `frontend/components/layout/app-shell.tsx`, `frontend/app/(workspace)/chat`, `frontend/app/(workspace)/documents`.

### Kết quả kiểm thử
- Xem chi tiết kiểm thử tổng hợp tại Phase H5.

---

## Phase H2 – HR Dashboard & Analytics
> **Trạng thái**: Hoàn thành  
> **Phạm vi**: `KPI Cards` · `Department Chart` · `Contract Status Chart` · `Live Docs Summary`

### Thay đổi đã thực hiện
- Tạo `hr-kpi-cards.tsx`, `department-chart.tsx` (biểu đồ thanh SVG/Tailwind accessible), `employee-status-chart.tsx` (SVG donut chart bất biến bằng `reduce`), `hr-dashboard-view.tsx` và route `frontend/app/hr/page.tsx`.
- Tích hợp `LiveKnowledgeBaseCard` đọc số liệu tài liệu thực (`GET /documents` qua `useDocuments`) tách biệt rõ với số liệu nhân sự mô phỏng Demo.

### Files thêm mới / chỉnh sửa
- **Thêm mới**: `frontend/components/hr/dashboard/hr-kpi-cards.tsx`, `frontend/components/hr/dashboard/department-chart.tsx`, `frontend/components/hr/dashboard/employee-status-chart.tsx`, `frontend/components/hr/dashboard/hr-dashboard-view.tsx`, `frontend/app/hr/page.tsx`.

### Kết quả kiểm thử
- Kiểm thử bằng `hr-domain.test.mjs` và `hr-ui.test.mjs` PASS (chi tiết ở Phase H5).

---

## Phase H3 – HR Document Center
> **Trạng thái**: Hoàn thành  
> **Phạm vi**: `Category Classifier` · `Document Preview` · `RAG Knowledge Upload`

### Thay đổi đã thực hiện
- Tạo `hr-upload-dialog.tsx` bọc `DocumentUpload` kèm thông báo minh bạch dùng chung kho tri thức với `/documents`.
- Tạo `hr-documents-view.tsx` và route `frontend/app/hr/documents/page.tsx`: tái sử dụng `useDocuments` (hỗ trợ cả polling async 202 và phân trang `loadMore`), `DocumentStatusBadge`, `DocumentPreview`; bổ sung tab phân loại client-side (*Chính sách / Quy định / Quy trình / Tài liệu chung*), ô tìm kiếm và nút **"Hỏi Chatbot về tài liệu này"**.

### Files thêm mới / chỉnh sửa
- **Thêm mới**: `frontend/components/hr/documents/hr-upload-dialog.tsx`, `frontend/components/hr/documents/hr-documents-view.tsx`, `frontend/app/hr/documents/page.tsx`.

### Kết quả kiểm thử
- Kiểm thử bằng `hr-domain.test.mjs` và `hr-ui.test.mjs` PASS (chi tiết ở Phase H5).

---

## Phase H4 – Global HR Chatbot Widget & User Guide
> **Trạng thái**: Hoàn thành  
> **Phạm vi**: `Floating/Drawer Widget` · `Multi-turn RAG` · `Citations` · `Interactive Guide`

### Thay đổi đã thực hiện
- Thêm prop tùy chọn `showAttachments?: boolean` (mặc định `true`) ở `frontend/components/chat/chat-composer.tsx` giữ nguyên 100% hành vi Workspace.
- Tạo `frontend/components/hr/chatbot/hr-chatbot-widget.tsx` và gắn vào `HrShell`: tái sử dụng `ChatController`, `createChatServices`, `ChatMessage`, `ChatComposer`, `ChatScrollController`, `CitationContent` và `DocumentPreviewSheet`; đồng bộ `activeSessionId` giữ hội thoại liên tục trên toàn bộ `/hr/*`, hỗ trợ `draftPrompt`, nút **"Phiên mới"** và link **"Mở toàn trang (/chat/[id])"**.
- Tạo `frontend/components/hr/guide/hr-guide-view.tsx` và route `frontend/app/hr/guide/page.tsx` gồm 4 mục hướng dẫn + 6 câu hỏi mẫu bấm mở nhanh Chatbot.

### Files thêm mới / chỉnh sửa
- **Thêm mới**: `frontend/components/hr/chatbot/hr-chatbot-widget.tsx`, `frontend/components/hr/guide/hr-guide-view.tsx`, `frontend/app/hr/guide/page.tsx`.
- **Chỉnh sửa**: `frontend/components/chat/chat-composer.tsx`, `frontend/components/hr/layout/hr-shell.tsx`.

### Kết quả kiểm thử
- Kiểm thử bằng `hr-ui.test.mjs` PASS (chi tiết ở Phase H5).

---

## Phase H5 – Verification, Documentation & Delivery
> **Trạng thái**: Hoàn thành  
> **Phạm vi**: `HR Unit & SSR Tests` · `Contract Check` · `Next.js Build` · `Docs`

### Thay đổi đã thực hiện
- Bổ sung `frontend/tests/hr-domain.test.mjs` và `frontend/tests/hr-ui.test.mjs`.
- Cập nhật `frontend/README.md` bổ sung tài liệu surface `/hr/*` (giữ RAG Workspace là chính).

### Files thêm mới / chỉnh sửa
- **Thêm mới**: `frontend/tests/hr-domain.test.mjs`, `frontend/tests/hr-ui.test.mjs`.
- **Chỉnh sửa**: `frontend/README.md`, `task/hr-portal/Task.md`, `task/hr-portal/change-log.md`.

### Kết quả kiểm thử
- Frontend `npm.cmd run test:contract`: **PASS** (`55 REST/SSE/health schemas`)
- Frontend `npm.cmd run typecheck`: **PASS**
- Frontend `npm.cmd run lint`: **PASS**
- Frontend `npm.cmd test`: **225/225 PASS**
- Frontend `npx.cmd next build --webpack`: **PASS** (10/10 static/PPR routes: `/`, `/_not-found`, `/chat`, `/chat/[sessionId]`, `/documents`, `/hr`, `/hr/documents`, `/hr/guide`)
- Backend `tests/architecture`: **9/9 PASS**, `tests/unit`: **287/287 PASS**, `tests/integration`: **154/154 PASS**

---

## Phase H6 – HR UI Visual & Typography Polish (`frontend-design` + `taste-skill`)
> **Trạng thái**: Hoàn thành  
> **Phạm vi**: `HR Theme Tokens` · `Typography Pairing` · `Layout Rhythm` · `Chart Palette`

### Thay đổi đã thực hiện
- Tạo `frontend/app/hr/hr-theme.css` định nghĩa hệ màu riêng cho `/hr/*` (mineral paper `#F6F8F7`, deep spruce primary `#0F5C4D`, palette chart đa sắc `#0F5C4D` / `#2B7A94` / `#C78626` / `#70877F` — không dùng violet/lavender và không ảnh hưởng tới RAG Workspace).
- Tích hợp font Google có hỗ trợ đầy đủ tiếng Việt (`Plus_Jakarta_Sans` cho heading + `Be_Vietnam_Pro` cho body) vào `frontend/app/hr/layout.tsx` và gán `.hr-theme` lên cả `HrLayout` lẫn Portal `<SheetContent>` của `HrChatbotWidget`.
- Tái cấu trúc bố cục theo từng màn hình thay cho card lồng lặp lại:
  - `/hr` Dashboard: dải metric 4 cột chia đường kẻ (`divide-x`) kèm `tabular-nums`, lưới 12 cột bất đối xứng (`7/5`) cho biểu đồ phòng ban và SVG Donut hợp đồng, dải trạng thái kho tri thức RAG thực.
  - `/hr/documents`: reader workbench 2 cột với indicator viền trái cho tài liệu đang chọn và khoảng đọc thoải mái.
  - `/hr/guide`: tinh gọn tiêu đề danh từ tự nhiên (`hr-guide.ts`), bố cục 2 cột dễ đọc và prompt cards có micro-interaction hover tinh tế.

### Files thêm mới / chỉnh sửa
- **Thêm mới**: `frontend/app/hr/hr-theme.css`.
- **Chỉnh sửa**: `frontend/app/hr/layout.tsx`, `frontend/fixtures/hr-guide.ts`, `frontend/components/hr/layout/hr-header-user.tsx`, `frontend/components/hr/layout/hr-shell.tsx`, `frontend/components/hr/dashboard/hr-kpi-cards.tsx`, `frontend/components/hr/dashboard/department-chart.tsx`, `frontend/components/hr/dashboard/employee-status-chart.tsx`, `frontend/components/hr/dashboard/hr-dashboard-view.tsx`, `frontend/components/hr/documents/hr-documents-view.tsx`, `frontend/components/hr/guide/hr-guide-view.tsx`, `frontend/components/hr/chatbot/hr-chatbot-widget.tsx`.

### Kết quả kiểm thử
- Frontend: `test:contract` **PASS**, `typecheck` **PASS**, `lint` **PASS**, `npm.cmd test` **225/225 PASS**, `npx.cmd next build --webpack` **PASS** (`10/10` routes).
