# Project Documentation Index (`docs/`)

Tài liệu dự án RAG Workspace được phân loại theo các thư mục chuyên đề bên dưới:

---

## 1. Kiến Trúc & Tái Cấu Trúc (`docs/refactoring/`)
Tập hợp các tài liệu và quyết định kiến trúc cho đợt **Backend Structural Refactoring (Target Architecture)**:
- [REF-00: Baseline Audit](refactoring/REF-00-BASELINE-AUDIT.md): Kết quả audit baseline và trạng thái test suite trước khi refactor.
- [REF-01: Module Mapping](refactoring/REF-01-MODULE-MAPPING.md): Bảng đối chiếu nguồn -> đích của toàn bộ modules backend, tests, scripts và evaluation.
- [REF-02: Architecture Decisions Record (ADR)](refactoring/REF-02-ARCHITECTURE-DECISIONS.md): 6 quyết định kiến trúc cốt lõi (Modular Monolith, Ports/Adapters, 4 splits, Zero-shim policy).
- [REF-03: Migration Log](refactoring/REF-03-MIGRATION-LOG.md): Nhật ký chi tiết các lệnh thực thi, commit và xử lý lỗi phát sinh.
- [REF-04: Architecture Verification](refactoring/REF-04-ARCHITECTURE-VERIFICATION.md): Báo cáo nghiệm thu kiểm chứng kiến trúc mới và 393 tests PASS.

---

## 2. Báo Cáo Nghiệm Thu & Kiểm Thử (`docs/acceptance/`)
Báo cáo kiểm thử hồi quy và nghiệm thu thực tế:
- [R2-06A: Offline Acceptance Report](acceptance/R2-06-ACCEPTANCE-REPORT.md): Nghiệm thu hồi quy offline 384 tests cho Tool Use MVP.
- [R2-06B: Controlled Live Smoke Report](acceptance/R2-06B-LIVE-SMOKE-REPORT.md): Nghiệm thu live smoke có kiểm soát với Groq Cloud và MongoDB Atlas.

---

## 3. Báo Cáo Kiểm Toán Hệ Thống (`docs/audits/`)
Các báo cáo audit hiện trạng mã nguồn qua các giai đoạn:
- [BACKEND-DEPENDENCY-ANALYSIS (R0-B)](audits/BACKEND-DEPENDENCY-ANALYSIS.md): Phân tích đồ thị import, fan-out, fan-in và phụ thuộc nội bộ.
- [BACKEND-MODULE-BOUNDARIES (R0-C)](audits/BACKEND-MODULE-BOUNDARIES.md): Phân tích ranh giới trách nhiệm module backend.
- [CODEBASE-INVENTORY](audits/CODEBASE-INVENTORY.md): Kiểm kê danh mục toàn bộ file và module trong dự án.
- [RAG-CORE-AUDIT-0B01](audits/RAG-CORE-AUDIT-0B01.md): Báo cáo audit backend RAG core logic.
- [RAG-CONVERSATION-AUDIT-0B02](audits/RAG-CONVERSATION-AUDIT-0B02.md): Báo cáo audit module hội thoại và persistence.
- [RAG-FRONTEND-EVALUATION-AUDIT-0B03](audits/RAG-FRONTEND-EVALUATION-AUDIT-0B03.md): Báo cáo audit frontend evaluation.
- [RAG-CODEBASE-ASSESSMENT-0C](audits/RAG-CODEBASE-ASSESSMENT-0C.md): Đánh giá tổng thể mã nguồn.
- [README-GAP-REPORT-0D](audits/README-GAP-REPORT-0D.md): Đối chiếu độ lệch giữa README và hiện trạng mã nguồn.

---

## 4. Tài Liệu Lưu Trữ (`docs/archive/`)
- [PROJECT_LOG_V1](archive/PROJECT_LOG_V1.md): Kế hoạch và nhật ký ban đầu của dự án RAG Demo (Giai đoạn V1).

---

## 5. Nhật Ký Thay Đổi & Bug Fixes (`docs/changelog/` & `docs/bugs/`)
- `docs/changelog/`: Lưu vết chi tiết thay đổi theo từng phase (`phase-01.md`, `phase-02.md`, `phase-03-04.md`).
- `docs/bugs/`: Báo cáo phân tích và giải pháp cho các bug quan trọng (`stream-terminal-parity.md`).

---

## 6. Frontend Runbooks & Browser Acceptance
Các hướng dẫn chạy thử, checklist tiếp cận và kiểm thử trình duyệt:
- `chat-actions-browser-acceptance.md`: Nghiệm thu hành vi chat trên trình duyệt Chromium.
- `document-actions-browser-acceptance.md`: Nghiệm thu quản lý tài liệu trên trình duyệt.
- `session-actions-browser-acceptance.md`: Nghiệm thu hành vi phiên hội thoại.
- `frontend-accessibility-checklist.md`: Checklist hỗ trợ tiếp cận (a11y).
- `frontend-automated-tests.md`: Hướng dẫn kiểm thử tự động Playwright và Node.
- `frontend-demo-readiness.md`: Báo cáo mức độ sẵn sàng cho demo.
- `frontend-functional-qa.md`: Runbook QA chức năng giao diện người dùng.
