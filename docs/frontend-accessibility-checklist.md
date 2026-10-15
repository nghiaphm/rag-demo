# F7-02 — UX/accessibility checklist (2026-10-14)

Implementation và automated checks đã hoàn tất. **Manual browser acceptance: NOT RUN / BLOCKED** do Browser không kết nối được (`Cannot redefine property: process` trước bootstrap; troubleshooting API chưa khả dụng). Không đánh dấu các phép kiểm tra trực tiếp là PASS từ kết quả unit/SSR hoặc đọc source. F7-02 còn IN PROGRESS cho tới khi nghiệm thu các mục manual.

Đã chẩn đoán lại: Next.js/IPv4/IPv6/client asset truy cập được từ Agent; lỗi nằm ở Browser package/runtime locked-global khi import, trước mọi kết nối browser. Xem [bằng chứng và hướng dẫn Chrome/Edge với mock API](./frontend-browser-qa-blocker.md). Chưa có hàng manual nào được chuyển thành PASS.

## Cách nghiệm thu

Chạy frontend với REST/SSE mock fixtures, không dùng live generation hoặc gọi Groq/Gemini. Chuẩn bị hai session, lịch sử dài, stream nhiều delta có whitespace, lỗi/partial response, bảng/code dài, citation hợp lệ và thiếu metadata, danh sách document loading/empty/error. Kiểm tra desktop, mobile 320/375px, zoom 200%, bàn phím và screen reader. Các mục sau đều **NOT RUN**:

| Tình huống manual | Kết quả cần đạt |
| --- | --- |
| Stream khi đang ở cuối | Vùng hội thoại theo nội dung; composer vẫn dùng được. Delta không bị trim hoặc đọc như từng token. |
| Cuộn lên bằng wheel/touch/PageUp trong stream | Giữ vị trí đang đọc; xuất hiện “Nội dung mới — Về cuối”. Click/Enter nút này về cuối và tiếp tục theo stream. |
| Resize, chuyển session, unmount | Không kéo người đang đọc về cuối; session mới mở ở cuối lịch sử; observer được cleanup, không leak trạng thái. |
| Tab/Shift+Tab và skip link | Thứ tự focus hợp lý, focus nhìn thấy; skip link tới main; vùng lịch sử/code/table có thể cuộn bằng keyboard. |
| Composer | Enter gửi một lần; Shift+Enter xuống dòng; Enter trong IME không gửi; blank không gửi. Khi generate textarea read-only vẫn giữ focus, Stop dùng được bằng keyboard. |
| Copy câu hỏi/câu trả lời/code | Nội dung clipboard chính xác, giữ whitespace/newline. Có thông báo thành công; clipboard bị từ chối/không hỗ trợ báo lỗi và cho copy thủ công. Streaming message không cho copy toàn câu trả lời chưa hoàn tất. |
| Citation drawer trên desktop/mobile | Nguồn đúng assistant, không tràn viewport; close button nhận focus khi mở; Tab ở trong drawer, Escape đóng, focus về đúng trigger. Footer sources trigger cũng trả focus đúng. |
| Mobile sidebar | Trigger có tên, mở/đóng bằng keyboard và Escape; focus trap/return; chọn route đóng sidebar. Không có scroll ngang toàn trang. |
| Upload/protected action dialog trên màn hình thấp | Nội dung cuộn được, action/confirmation còn truy cập được; giữ nguyên guard chống đóng khi mutation đang xử lý. Không gửi mutation live khi QA. |
| Loading/empty/error | Skeleton không được screen reader đọc; loading có nhãn và hết sau terminal; error có thông báo, retry có chủ đích. |
| Markdown | Heading/list/quote/GFM table/code/links rõ ràng; code và bảng dài cuộn trong vùng riêng; citation không biến thành citation button trong code/link. Raw HTML không thực thi. Link báo mở tab mới. |
| Screen reader | Nhãn composer/copy/Stop/regions có nghĩa; trạng thái xử lý được thông báo, không đọc lại toàn transcript sau mỗi delta. |
| Reduced motion, zoom/contrast | Scroll tức thời, spinner/skeleton không animate khi reduced motion; nội dung không bị cắt ở zoom 200%, focus và trạng thái không chỉ dựa vào màu. Kiểm tra contrast thực tế. |

## Bằng chứng tự động / source review

- PASS: 6/6 F7-02 tests (scroll follow/pause/resume/resize/detach, clipboard exact/rejected/unavailable, production Markdown SSR, composer Enter/Shift+Enter/IME/Stop/blank, skeleton aria-hidden/reduced motion).
- PASS: full regression 157/157; build, TypeScript, ESLint, offline 45-schema verifier. Lệnh cụ thể trong FRONTEND_PLAN mục 28.
- Source review: existing skip link, navigation focus rings, Base UI modal semantics; source drawer initial focus vào nút Đóng; transcript không còn aria-live đọc cả nội dung đang stream. Đây không phải bằng chứng focus trap/Escape/screen reader đã chạy trong browser.
- Optional theme switch chưa thêm; không thêm dependency, không xây PDF viewer hoặc link tài liệu giả. Backend/API contract giữ nguyên.
- Lần resolve blocker: mock API harness tests4/4 và full regression161/161 PASS, lint/diff PASS. Đây là HTTP/fixture verification, không thay thế browser/mobile/keyboard/screen-reader nghiệm thu.

## F7-03-05 gate update — 2026-10-15

Tất cả manual rows ở trên **vẫn NOT RUN**; Browser bootstrap lỗi `Cannot redefine property: process` trước setup/connection/URL. Các session menu/rename/delete focus/keyboard, chat URL/history/new-tab/copy/source drawer và document dialogs trên320/375px/zoom200% cũng chưa có actual browser evidence. Chưa có developer Chrome/Edge outcomes, không tự waive các hàng này.

Xem [functional QA report](./frontend-functional-qa.md) cho coverage hiện tại và technical-debt disposition, [mock handoff](./frontend-browser-qa-blocker.md) cho profiles `/many` và `/lifecycle`. Frontend193/193 + backend80/81 (1 parity FAIL) + HTTP/CORS/prerender evidence không thay thế keyboard/focus/reduced-motion/screen-reader acceptance. Gate còn chặn bởi [BUG-STREAM-001](./bugs/stream-terminal-parity.md) và manual coverage; F7-02/F7-03-02…05/Suspense browser acceptance chưa được nâng COMPLETED.
