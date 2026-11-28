# Mục lục Tài liệu Dự án (`docs/`)

Tài liệu kỹ thuật và vận hành của RAG Workspace được chia theo các nhóm sau:

## 1. Hướng dẫn Demo và Đánh giá
- [DEMO-RUNBOOK](DEMO-RUNBOOK.md): Hướng dẫn chạy Demo theo cả 2 chế độ (Provider-Free Mock Mode và Local/Docker Stack), nạp dữ liệu an toàn qua `backend/scripts/seed_demo_workspace.py` (`--dry-run` mặc định, tách collection `rag_documents_demo`) và cấu hình SSE sau Reverse Proxy.
- Ghi chú đánh giá: Thư mục `backend/evaluation/` dùng **RAGAS-inspired custom metrics** (`deterministic_heuristic` tách riêng với `CustomLlmJudge`, không mạo nhận thư viện `ragas` PyPI chính thức). Báo cáo live (`docs/evaluation/FINAL-EVALUATION-REPORT.md`) chỉ được xuất khi người vận hành phê duyệt chạy `benchmark_matrix.py --live --approve-live --qdrant-collection rag_documents_eval`.

## 2. Kiến trúc và Tái cấu trúc (`docs/refactoring/`)
- [REF-00: Baseline Audit](refactoring/REF-00-BASELINE-AUDIT.md): Kết quả kiểm toán trước tái cấu trúc.
- [REF-01: Module Mapping](refactoring/REF-01-MODULE-MAPPING.md): Bảng ánh xạ module backend, test, scripts và evaluation.
- [REF-02: Architecture Decisions Record (ADR)](refactoring/REF-02-ARCHITECTURE-DECISIONS.md): 6 quyết định kiến trúc (Modular Monolith, Ports/Adapters, Zero-shim).
- [REF-03: Migration Log](refactoring/REF-03-MIGRATION-LOG.md): Nhật ký di chuyển mã nguồn.
- [REF-04: Architecture Verification](refactoring/REF-04-ARCHITECTURE-VERIFICATION.md): Báo cáo kiểm chứng kiến trúc và kiểm thử hồi quy tại thời điểm cắt nhánh.

## 3. Báo cáo Nghiệm thu và Kiểm toán (`docs/acceptance/` & `docs/audits/`)
- [R2-06A: Offline Acceptance Report](acceptance/R2-06-ACCEPTANCE-REPORT.md): Báo cáo hồi quy offline cho Tool Use MVP.
- [R2-06B: Controlled Live Smoke Report](acceptance/R2-06B-LIVE-SMOKE-REPORT.md): Báo cáo live smoke có kiểm soát với Groq Cloud và MongoDB Atlas.
- `docs/audits/`: Báo cáo phân tích phụ thuộc (`BACKEND-DEPENDENCY-ANALYSIS.md`, `BACKEND-MODULE-BOUNDARIES.md`), kiểm kê mã nguồn (`CODEBASE-INVENTORY.md`), kiểm toán RAG/Conversation/Frontend và đối chiếu tài liệu (`README-GAP-REPORT-0D.md`).

## 4. Lịch sử, Sửa lỗi và Runbooks Frontend
- `docs/archive/`: Nhật ký thiết kế giai đoạn V1 (`PROJECT_LOG_V1.md`).
- `docs/changelog/` & `docs/bugs/`: Ghi chép thay đổi các phase đầu và báo cáo xử lý lỗi (`stream-terminal-parity.md`).
- Runbooks kiểm thử trình duyệt: `chat-actions-browser-acceptance.md`, `document-actions-browser-acceptance.md`, `session-actions-browser-acceptance.md`, `frontend-accessibility-checklist.md`, `frontend-automated-tests.md`, `frontend-demo-readiness.md`, `frontend-functional-qa.md`.
- Tiến độ chuẩn bị triển khai hiện tại (Phase 0 đến Phase 5): [Task.md](../task/rag-workspace-readiness/Task.md) và [change-log.md](../task/rag-workspace-readiness/change-log.md).
