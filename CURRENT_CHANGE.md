# CURRENT_CHANGE — Nhật ký thực thi RAG V2

> **Vai trò:** Ghi ngắn gọn những gì Agent **thực sự đã làm** sau mỗi task, kèm file thay đổi, kiểm thử và công việc kế tiếp. Kế hoạch/checklist chính nằm tại [`PROJECT_LOG_V2.md`](./PROJECT_LOG_V2.md). Không tự nhận hoàn thành từ nội dung kế hoạch.

## 1. Trạng thái gần nhất

- **Giai đoạn:** Giai đoạn 1 — IN PROGRESS; audit baseline hoàn thành, chưa triển khai V2
- **Task vừa hoàn thành:** `P1-01 / M-01` — Audit repository và các phụ thuộc PostgreSQL/pgvector
- **Task tiếp theo:** `P1-02 / M-02` — Kết nối MongoDB Atlas và Qdrant Cloud (**chưa bắt đầu**)
- **Blocker:** `.venv` bị hỏng do thiếu Python gốc; Docker daemon không chạy; `.env` chưa có cấu hình MongoDB. Qdrant credentials có mặt nhưng chưa được source sử dụng và chưa kiểm tra kết nối
- **Lần cập nhật:** Hoàn thành audit tĩnh và ghi nhận baseline; không thay đổi source code, không kết nối hay thay đổi dữ liệu cloud

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

### [2026-10-11 13:41 UTC+07:00] P1-01 / M-01 — Audit baseline
- **Trạng thái:** COMPLETED
- **Đã thực hiện:** Đối chiếu README với toàn bộ backend, routes, upload/index/list/delete, retrieval/chain, scripts, evaluation, dependencies, config và Compose. Xác nhận runtime V1 coupling trực tiếp với PostgreSQL/pgvector; chưa có MongoDB/Qdrant adapter. Ghi nhận loader thực tế hỗ trợ thêm XLSX và các rủi ro baseline: upload ghi đè file trước khi index, re-index xóa vector cũ trước khi add, delete không xóa file, chưa có test suite.
- **Files thay đổi:** `PROJECT_LOG_V2.md`, `CURRENT_CHANGE.md` (chỉ cập nhật trạng thái/nhật ký; không sửa source code).
- **Kiểm thử:** `docker compose config --quiet` — PASS; cấu hình Compose hợp lệ. Kiểm tra `.env` không in giá trị — PASS; Qdrant URL/key hiện diện, URL HTTPS, MongoDB URI/database chưa có. Python AST, `/health`, `try_step.py` và retrieval/eval hiện tại — NOT RUN; interpreter gốc của `.venv` không còn tồn tại. `docker compose ps` — NOT RUN; Docker daemon không chạy. Hai artifact eval ngày 2026-09-24 là baseline lịch sử: mỗi run 9/9 case không lỗi, retrieval hit/recall 1.0; đây không phải kết quả chạy lại.
- **Tồn đọng / quyết định:** `langchain-postgres`, `pgvector`, `psycopg`, `DATABASE_URL`, `app/db.py`, vectorstore/retriever/pipeline, API documents/chat, scripts, eval và Compose đều cần được thay thế hoặc tách khỏi PostgreSQL trong các task migration sau. `.env.example` và Settings chưa khai báo MongoDB/Qdrant; Qdrant credentials trong `.env` hiện bị `extra="ignore"`. Chưa xác minh kết nối cloud, collection/dimension hay dữ liệu.
- **Tiếp theo:** `P1-02 / M-02` — chỉ bắt đầu khi được giao; sửa môi trường Python trước khi chạy smoke test.

## 4. Lưu trữ nhật ký cũ (archive)

Chưa có. Khi archive, dùng ví dụ `docs/changelog/phase-01.md` và ghi đường dẫn thật tại đây.
