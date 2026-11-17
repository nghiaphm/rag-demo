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
> **Trạng thái**: Đang thực hiện (Hoàn thành H1.1 Route Group Separation & HR Navigation Shell)  
> **Phạm vi**: `Route Groups` · `HrShell` · `HrChatbotProvider` · `HR Domain Logic`

### Thay đổi đã thực hiện
- **H1.1 Route Group Separation & HR Navigation Shell**:
  - Tinh gọn `frontend/app/layout.tsx` chỉ giữ `<html>`, `<body>`, Geist fonts, metadata và skip-link; giữ `frontend/app/page.tsx` redirect `/` $\rightarrow$ `/chat`.
  - Tạo `frontend/app/(workspace)/layout.tsx` bọc `<AppShell>` và di chuyển `chat/`, `documents/` vào `(workspace)/` bảo toàn nguyên vẹn URL `/chat`, `/chat/[sessionId]`, `/documents`; bổ sung link chuyển sang `HR Demo Portal` (`/hr`) trong `SidebarFooter` của `frontend/components/layout/app-shell.tsx`.
  - Tạo `frontend/types/hr.ts` tách biệt hoàn toàn với 4 file OpenAPI DTO (`api`, `chat`, `document`, `sessions`).
  - Tạo `HrChatbotProvider` + `useHrChatbot` (`frontend/components/hr/layout/hr-chatbot-provider.tsx`) chỉ quản lý state UI/ngữ cảnh (`isOpen`, `activeSessionId`, `pageContext`, `draftPrompt`).
  - Tạo `HrHeaderUser` (`frontend/components/hr/layout/hr-header-user.tsx`) và `HrShell` (`frontend/components/hr/layout/hr-shell.tsx`) với sidebar điều hướng `/hr`, `/hr/documents`, `/hr/guide` highlight active route (`aria-current="page"`), thông tin người dùng Demo, nút quay về RAG Workspace (`/chat`) và launcher placeholder cho Trợ lý HR; gắn vào `frontend/app/hr/layout.tsx` + placeholder `frontend/app/hr/page.tsx`.
  - Viết unit/SSR test tại `frontend/tests/hr-shell.test.mjs`.

### Files thêm mới / chỉnh sửa
- **Thêm mới (H1.1)**: `frontend/app/(workspace)/layout.tsx`, `frontend/app/hr/layout.tsx`, `frontend/app/hr/page.tsx`, `frontend/types/hr.ts`, `frontend/components/hr/layout/hr-chatbot-provider.tsx`, `frontend/components/hr/layout/hr-header-user.tsx`, `frontend/components/hr/layout/hr-shell.tsx`, `frontend/tests/hr-shell.test.mjs`.
- **Chỉnh sửa / Di chuyển (H1.1)**: `frontend/app/layout.tsx`, `frontend/components/layout/app-shell.tsx`, di chuyển `frontend/app/chat` $\rightarrow$ `frontend/app/(workspace)/chat`, `frontend/app/documents` $\rightarrow$ `frontend/app/(workspace)/documents`.

### Kết quả kiểm thử
- `npm.cmd run test:contract`: **PASS** (`55 REST/SSE/health schemas`)
- `npm.cmd run typecheck`: **PASS**
- `npm.cmd run lint`: **PASS**
- `npm.cmd test`: **218/218 PASS** (gồm `hr-shell.test.mjs`)
- `npx.cmd next build --webpack`: **PASS** (đã kiểm tra prerender đủ 8/8 pages gồm `/`, `/chat`, `/chat/[sessionId]`, `/documents`, `/hr`; lưu ý Turbopack trên Windows + Node 24 gặp lỗi spawn worker CSS riêng môi trường).

---

## Phase H2 – HR Dashboard & Analytics
> **Trạng thái**: Chưa bắt đầu  
> **Phạm vi**: `KPI Cards` · `Department Chart` · `Contract Status Chart` · `Live Docs Summary`

### Thay đổi đã thực hiện
- *(Chưa có cập nhật)*

### Files thêm mới / chỉnh sửa
- *(Chưa có cập nhật)*

### Kết quả kiểm thử
- *(Chưa có cập nhật)*

---

## Phase H3 – HR Document Center
> **Trạng thái**: Chưa bắt đầu  
> **Phạm vi**: `Category Classifier` · `Document Preview` · `RAG Knowledge Upload`

### Thay đổi đã thực hiện
- *(Chưa có cập nhật)*

### Files thêm mới / chỉnh sửa
- *(Chưa có cập nhật)*

### Kết quả kiểm thử
- *(Chưa có cập nhật)*

---

## Phase H4 – Global HR Chatbot Widget & User Guide
> **Trạng thái**: Chưa bắt đầu  
> **Phạm vi**: `Floating/Drawer Widget` · `Multi-turn RAG` · `Citations` · `Interactive Guide`

### Thay đổi đã thực hiện
- *(Chưa có cập nhật)*

### Files thêm mới / chỉnh sửa
- *(Chưa có cập nhật)*

### Kết quả kiểm thử
- *(Chưa có cập nhật)*

---

## Phase H5 – Verification, Documentation & Delivery
> **Trạng thái**: Chưa bắt đầu  
> **Phạm vi**: `HR Unit & SSR Tests` · `Contract Check` · `Next.js Build` · `Docs`

### Thay đổi đã thực hiện
- *(Chưa có cập nhật)*

### Files thêm mới / chỉnh sửa
- *(Chưa có cập nhật)*

### Kết quả kiểm thử
- *(Chưa có cập nhật)*
