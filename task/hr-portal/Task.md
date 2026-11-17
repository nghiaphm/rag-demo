# HR Portal Demo — Implementation Roadmap & Task Tracking

> **Trạng thái ký hiệu:** `[ ]` Chưa làm · `[/]` Đang thực hiện · `[x]` Hoàn thành · `[!]` Bị chặn

---

## Nguyên tắc kỹ thuật xuyên suốt (Architectural Guardrails)

Mọi thay đổi trong lộ trình xây dựng HR Portal Demo bắt buộc tuân thủ các ràng buộc kiến trúc sau:
1. **Workspace Isolation & Regression Safety**: Giữ nguyên **RAG Workspace** làm sản phẩm mặc định và chính (`/`, `/chat`, `/chat/[sessionId]`, `/documents` nằm trong Route Group `app/(workspace)/`). Tách `HrShell` và `HrChatbotProvider` riêng trong `app/hr/layout.tsx`, không làm ảnh hưởng tới `(workspace)`.
2. **Contract & Offline Test Integrity**: Giữ nguyên 100% 4 file DTO parity (`frontend/types/{api,chat,document,sessions}.ts`) khớp FastAPI OpenAPI; toàn bộ type dành riêng cho HR đặt tại `frontend/types/hr.ts`. Đảm bảo `test:contract`, `typecheck`, `lint`, `npm.cmd test` và `next build` luôn PASS.
3. **Reuse Without Duplication**: `HrChatbotWidget` và `/hr/documents` tái sử dụng trực tiếp `ChatController`, `createChatServices`, `useDocuments`, `useSessions`, `UploadController`, `ChatMessage`, `ChatComposer`, `CitationContent`, `DocumentPreview` — không nhân bản HTTP/SSE/RAG client logic.
4. **Honest Data & Isolation Boundaries**:
   - Thống kê nhân sự dùng từ `fixtures/hr-analytics.ts` và gắn nhãn rõ là **Dữ liệu mô phỏng HR (Demo)**.
   - Phân loại *Chính sách / Quy định / Quy trình* suy luận thuần phía client (`lib/hr/document-categories.ts`), không sửa schema Backend hay giả lập đã lưu xuống MongoDB.
   - Minh bạch rằng tài liệu upload tại `/hr/documents` đi vào RAG Knowledge Base dùng chung với `/documents` (trừ khi tách `.env` collection riêng khi chạy demo).

---

## Phase H1 – Routing Isolation, HR Shell & Domain Foundation
**Mục tiêu**: Tách `(workspace)` Route Group giữ nguyên URL cũ, dựng khung điều hướng `/hr/*`, `HrChatbotProvider` đúng ranh giới UI/ngữ cảnh và lớp pure TS logic/fixtures cho HR.

### H1.1 Route Group Separation & HR Navigation Shell
- [x] Tinh gọn `frontend/app/layout.tsx` (chỉ giữ `<html>`, `<body>`, Geist fonts, metadata, skip-link); giữ `frontend/app/page.tsx` redirect `/` $\rightarrow$ `/chat`.
- [x] Tạo `frontend/app/(workspace)/layout.tsx` bọc `<AppShell>` và di chuyển `chat/`, `documents/` vào `(workspace)/` giữ nguyên hoàn toàn URL công khai (`/chat`, `/chat/[sessionId]`, `/documents`); thêm link chuyển nhanh sang `/hr` trong `AppShell` mà không làm vỡ test hiện có.
- [x] Tạo `frontend/types/hr.ts` (`HrPageContext`, `HrUserProfile`, `HrDocumentCategory`, `DepartmentHeadcount`, `ContractStatusMetric`, `HrKpiCard`, `HrGuideSection`, `HrPromptTemplate`).
- [x] Tạo `HrChatbotProvider` + `useHrChatbot` (`frontend/components/hr/layout/hr-chatbot-provider.tsx`) chỉ quản lý UI/navigation state (`isOpen`, `activeSessionId`, `pageContext`, `draftPrompt`), không chứa `ChatController`, `fetch` hay SSE parser.
- [x] Tạo `HrShell` (`frontend/components/hr/layout/hr-shell.tsx`) và `HrHeaderUser` (`frontend/components/hr/layout/hr-header-user.tsx`) gồm sidebar điều hướng (`/hr`, `/hr/documents`, `/hr/guide`), highlight trang đang truy cập, header với thông tin người dùng Demo, nút quay về RAG Workspace và điểm mount `HrChatbotWidget`; gắn vào `frontend/app/hr/layout.tsx`.

### H1.2 HR Fixtures & Pure Domain Logic (`lib/hr/`)
- [ ] Tạo `frontend/fixtures/hr-analytics.ts` (KPI nhân sự cơ bản, phân bổ nhân viên theo phòng ban, trạng thái nhân viên/hợp đồng) và `frontend/fixtures/hr-guide.ts` (hướng dẫn hệ thống & câu hỏi mẫu).
- [ ] Tạo `frontend/lib/hr/analytics.ts` (tổng hợp KPI & tỷ lệ biểu đồ từ fixtures; tách riêng hàm tóm tắt trạng thái kho tài liệu thực từ `DocumentInfo[]`).
- [ ] Tạo `frontend/lib/hr/document-categories.ts` (phân loại xác định *Chính sách / Quy định / Quy trình / Khác* từ `file_name` + hàm lọc/tìm kiếm thuần TypeScript).

**Definition of Done (Phase H1)**:
- [ ] Toàn bộ kiểm thử RAG Workspace (`test:contract`, `typecheck`, `lint`, `npm.cmd test`) PASS 100%, không đổi URL và hành vi của `(workspace)`.

---

## Phase H2 – HR Dashboard & Analytics (`/hr`)
**Mục tiêu**: Xây dựng trang Dashboard HR với thẻ thống kê nhân sự, biểu đồ phòng ban, biểu đồ trạng thái nhân viên/hợp đồng và thẻ tổng quan kho tri thức thực.

### H2.1 Dashboard Components & Route
- [ ] Xây dựng `frontend/components/hr/dashboard/hr-kpi-cards.tsx` (thẻ thống kê nhân sự tổng quan + chỉ số HR cơ bản, gắn nhãn `Dữ liệu mô phỏng HR`).
- [ ] Xây dựng `frontend/components/hr/dashboard/department-chart.tsx` (biểu đồ số lượng nhân viên theo phòng ban bằng SVG/Tailwind thuần, hỗ trợ accessibility & SSR).
- [ ] Xây dựng `frontend/components/hr/dashboard/employee-status-chart.tsx` (biểu đồ trạng thái nhân viên / hợp đồng).
- [ ] Xây dựng `frontend/components/hr/dashboard/hr-dashboard-view.tsx` và route `frontend/app/hr/page.tsx` (tích hợp tóm tắt số tài liệu thực từ `useDocuments` và nút mở nhanh Chatbot).

**Definition of Done (Phase H2)**:
- [ ] `/hr` render sạch cả SSR và browser, tách bạch rõ dữ liệu mô phỏng HR với số liệu tài liệu thực từ Backend.

---

## Phase H3 – HR Document Center (`/hr/documents`)
**Mục tiêu**: Hiển thị danh sách tài liệu nhân sự, phân loại Chính sách / Quy định / Quy trình, xem nội dung và upload tài liệu mới vào RAG Knowledge Base.

### H3.1 Category Filtering, Preview & RAG Upload
- [ ] Xây dựng `frontend/components/hr/documents/hr-upload-dialog.tsx` bọc `DocumentUpload` của lõi RAG kèm thông báo minh bạch về kho tri thức dùng chung với `/documents`.
- [ ] Xây dựng `frontend/components/hr/documents/hr-documents-view.tsx` tái sử dụng `useDocuments`, `DocumentStatusBadge`, `DocumentPreview` (`getDocumentPreview`) và bổ sung tab lọc *Chính sách / Quy định / Quy trình* (hiển thị rõ là phân loại từ tên file), ô tìm kiếm nhanh và nút **"Hỏi Chatbot về tài liệu này"**.
- [ ] Tạo route `frontend/app/hr/documents/page.tsx`.

**Definition of Done (Phase H3)**:
- [ ] Xem danh sách, lọc theo 3 nhóm HR, xem thông tin/nội dung tài liệu (TXT/MD/XLSX) và upload tài liệu vào RAG Knowledge Base hoạt động đầy đủ (kể cả async polling).

---

## Phase H4 – Global HR Chatbot Widget & User Guide (`/hr/guide`)
**Mục tiêu**: Cung cấp HR Chatbot mở được từ mọi trang `/hr/*` hỗ trợ hội thoại nhiều lượt kèm trích dẫn nguồn, cùng trang User Guide tương tác.

### H4.1 Global HR Chatbot Widget
- [ ] Bổ sung prop tùy chọn `showAttachments?: boolean` (mặc định `true`) ở `frontend/components/chat/chat-composer.tsx` nếu cần giao diện drawer gọn nhẹ mà vẫn giữ nguyên hành vi Workspace.
- [ ] Xây dựng `frontend/components/hr/chatbot/hr-chatbot-widget.tsx` gắn trong `HrShell`:
  - Nút mở nhanh ở góc màn hình & Header trên mọi trang `/hr/*`.
  - Khởi tạo `ChatController` (`createChatServices`), đồng bộ `activeSessionId` với `HrChatbotProvider` nhưng không gọi `router.replace`, giữ nguyên hội thoại khi chuyển giữa `/hr`, `/hr/documents`, `/hr/guide`.
  - Hỗ trợ `draftPrompt`, hội thoại nhiều lượt, nút **"Phiên mới"**, link **"Mở toàn trang (/chat/[id])"**, render Markdown + `CitationContent` + mở `DocumentPreviewSheet`.

### H4.2 User Guide Page (`/hr/guide`)
- [ ] Xây dựng `frontend/components/hr/guide/hr-guide-view.tsx` và route `frontend/app/hr/guide/page.tsx` gồm 4 mục: *Hướng dẫn hệ thống*, *Các chức năng*, *Hướng dẫn sử dụng Chatbot & trích dẫn `[n]`*, *Tìm kiếm & xem tài liệu*, kèm các câu hỏi mẫu bấm mở nhanh Chatbot.

**Definition of Done (Phase H4)**:
- [ ] Mở HR Chatbot từ mọi trang `/hr/*`, hỏi đáp chính sách nhiều lượt với RAG Backend, xem nguồn tham khảo và dùng User Guide hoạt động trơn tru.

---

## Phase H5 – Verification, Documentation & Delivery
**Mục tiêu**: Bổ sung bộ test cho HR Portal, xác nhận build production sạch và cập nhật tài liệu dự án.

### H5.1 Tests, Quality Gates & Documentation
- [ ] Viết `frontend/tests/hr-domain.test.mjs` kiểm thử `lib/hr/analytics.ts` và `lib/hr/document-categories.ts`.
- [ ] Viết `frontend/tests/hr-ui.test.mjs` kiểm thử SSR `renderToStaticMarkup` cho `HrShell` (highlight active route, header user info), `HrDashboardView`, `HrDocumentsView`, `HrGuideView`, `HrChatbotWidget` và `HrChatbotProvider`.
- [ ] Chạy đầy đủ kiểm thử: `npm.cmd run test:contract`, `npm.cmd run typecheck`, `npm.cmd run lint`, `npm.cmd test`, `npm.cmd run build` và Backend `tests/architecture`, `tests/unit`, `tests/integration`.
- [ ] Cập nhật `frontend/README.md` (bổ sung mô tả surface `/hr/*` trong khi giữ RAG Workspace làm sản phẩm chính) và hoàn thiện `task/hr-portal/change-log.md`.

**Definition of Done (Phase H5)**:
- [ ] Toàn bộ CI Frontend + Backend + `next build` PASS 100%, sẵn sàng chia commit theo phạm vi và mở PR vào `master`.
