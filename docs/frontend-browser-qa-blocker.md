# F7-02 — Browser QA diagnosis và nghiệm thu Chrome/Edge

Ngày: 2026-10-14. **F7-02 IN PROGRESS**; chưa có bằng chứng manual acceptance. Không sửa UI, Next config, Browser package hoặc runtime security settings. Không gọi Groq/Gemini.

## Chẩn đoán đã thực hiện

| Lớp | Bằng chứng từ môi trường Agent | Kết luận / giới hạn |
| --- | --- | --- |
| Next.js server | Port 3000 LISTEN trên `::`, PID 2696, process `node`; shell Node v24.20.0. | Server đang chạy, không khởi động lại hoặc kill server developer. PID là snapshot tại thời điểm kiểm tra. |
| IPv4/IPv6 HTTP | `curl.exe --noproxy '*'`: `127.0.0.1:3000/chat` 200, `localhost:3000/documents` 200 qua `::1`; `/` 307 → `/chat`; `/chat/not-a-uuid` 200. | Không có lỗi localhost/network ở các probe này. Route invalid-session là trang client xử lý, HTTP200 không chứng minh thông báo lỗi đã render/hydrate đúng. |
| Frontend delivery | `Invoke-WebRequest /chat`: HTTP200, có `main-content`; script `/_next/…` lấy từ HTML trả200, `application/javascript`. | HTML và client asset truy cập được; chưa chứng minh hydration, visual layout hoặc accessibility. |
| Công cụ thực thi | Probe `1+1` trả2; `import('node:os')` thành công, `win32`. | Công cụ thực thi cơ bản vẫn hoạt động. |
| Browser package | Entry `browser/26.602.30954/scripts/browser-client.mjs` tồn tại. Bootstrap theo skill thất bại ở **import**, TypeError `Cannot redefine property: process`, frame đầu dòng33. | Lỗi trước `setupBrowserRuntime`, browser discovery, mở tab và bất kỳ truy cập URL nào; không phải connection timeout tới Next.js. |
| Nguyên nhân tương thích | Entry dòng33 gán `globalThis.process = processShim`, dòng35 cũng gán qua `global`. Kernel của công cụ đặt `process` trong trusted context bằng `defineLockedGlobal` (`writable:false`, `configurable:false`), dòng289. | Xung đột Browser package/runtime được đối chiếu trực tiếp từ source và stack. Không có bằng chứng browser transport/extension hoạt động hay hỏng vì chưa tới bước đó. |
| Troubleshooting | Skill Browser đã đọc, bootstrap chính thức đã thử. `agent.documentation.get('api-troubleshooting')` chưa khả dụng vì `agent` chưa được tạo; đã đọc bản packaged `docs/api-troubleshooting.md` bằng filesystem. | Tài liệu không cung cấp cách khôi phục lỗi locked-global này. Không dùng đường browser-control thay thế hoặc sửa/lách security binding. |

Lệnh đọc socket ban đầu bị `Access denied` trong sandbox; đọc lại bằng escalation đã thành công. Đây là giới hạn quyền của phép đọc socket, độc lập với lỗi import Browser. Không mở firewall hoặc thay bind host để che lỗi công cụ.

Phương án phục hồi thuộc môi trường Codex: khởi động lại ứng dụng/session, cập nhật Browser plugin và execution runtime qua cơ chế quản lý chính thức, rồi thử bootstrap lại. Không bảo đảm restart đơn thuần sẽ sửa một cặp phiên bản không tương thích. Nếu vẫn lỗi, gửi maintainer thông tin phiên bản Browser, lỗi/line33, kernel locked-global và kết quả probe cơ bản; không gửi `.env`, credentials hoặc toàn bộ runtime logs. Chưa thực hiện update/restart ngoài workspace trong task này.

## Chrome/Edge với mock API độc lập

Đã thêm `frontend/scripts/qa-mock-api.mjs`, dùng Node HTTP built-in và TypeScript đã có để đọc document fixtures. Server bind **127.0.0.1:4011**, chỉ có data trong RAM, không import backend, không đọc `.env`, không proxy hoặc gửi outbound requests. Unknown routes trả404. Restart mock reset sessions/history. Default profiles: document upload/update/reindex/delete chỉ tiêu thụ synthetic body rồi trả503 sau delay, không lưu file hoặc mutation. Opt-in `/lifecycle` được bổ sung trong F7-03-04, có document/version metadata mutations trong RAM để QA success/failure; xem extension bên dưới. Body giới hạn2MiB; chỉ dùng file `.txt` vài bytes tự tạo để kiểm tra dialog/busy/error. Đây là mock UX, không mô phỏng toàn bộ FastAPI/business logic hoặc chứng minh cancellation/persistence live.

1. Terminal A, từ root:

   ```powershell
   node frontend/scripts/qa-mock-api.mjs
   ```

2. Developer tự dừng **dev server của project này** bằng Ctrl+C ở terminal đã chạy nó (Agent chưa dừng). Chỉ chạy một Next dev instance trong thư mục frontend để tránh `.next/dev/lock`. Terminal B:

   ```powershell
   Set-Location D:\Project\rag-demo\frontend
   $qaPreviousApiBase = $env:NEXT_PUBLIC_API_BASE_URL
   $env:NEXT_PUBLIC_API_BASE_URL = 'http://127.0.0.1:4011'
   try {
     npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
   } finally {
     if ($null -eq $qaPreviousApiBase) {
       Remove-Item Env:NEXT_PUBLIC_API_BASE_URL -ErrorAction SilentlyContinue
     } else {
       $env:NEXT_PUBLIC_API_BASE_URL = $qaPreviousApiBase
     }
   }
   ```

   Không sửa `.env`/Next config. Nếu port3000 thuộc project khác, chọn port trống và truy cập đúng port; không kill process khác. Dev env này override API URL chỉ trong terminal trên; Ctrl+C chạy phần khôi phục. Không dùng production build cũ vì NEXT_PUBLIC variables có thể đã inline khi build.

3. Mở **Chrome hoặc Edge** tại `http://127.0.0.1:3000/chat`. Trong DevTools Network, xác nhận **mọi API request** đi tới `127.0.0.1:4011`; nếu thấy backend/provider host khác, dừng QA và kiểm tra lại env/server đang mở. Không cần chạy FastAPI. Không click link external fixture `example.test`; chỉ kiểm tra label/new-tab semantics.

4. Hai sidebar sessions: A có24 messages/lịch sử dài, B có2 messages. Mở A để kiểm tra scroll/refresh/missing citation metadata, đổi B để kiểm tra không trộn. New Chat tạo session trong RAM. Gửi `QA success`: stream ~10s, content có heading/list/quote/bảng/code dài, repeat `[1]`, invalid `[99]`, nguồn page0 (hiển thị Trang1). Nguồn được metadata liên kết chỉ trong live assistant tương ứng; refresh chỉ có citations, fallback ordinal phải rõ.

5. Các câu hỏi đặc biệt (vẫn là mock): `[error]` → SSE terminal PARTIAL; `[disconnect]` → đóng stream thiếu terminal; `[no-metadata]` → sources rỗng. Kiểm tra spinner kết thúc, partial text/copy/error UI. Gửi câu thường rồi Stop hoặc đổi session giữa stream để kiểm tra cleanup; không gửi lại tự động.

6. `/documents` có INDEXED/PROCESSING/FAILED và active version riêng. Dùng synthetic file để mở upload/update dialogs; chọn reindex/delete và confirmation chỉ khi Network xác nhận mock host. Mock mutations trả503 có delay để kiểm tra busy guard/error; **không diễn giải kết quả này là live backend mutation hoặc ingestion**. Health routes không được mock trong harness này, trả404; health readiness không thuộc nghiệm thu harness.

7. Để kiểm tra empty/list error/skeleton, lần lượt đổi giá trị env trong bước2 và **restart dev server**:

   | Mock base URL | Scenario |
   | --- | --- |
   | `http://127.0.0.1:4011` | Normal; REST delay600ms, SSE250ms/delta |
   | `http://127.0.0.1:4011/slow` | REST delay2400ms cho skeleton/focus pending |
   | `http://127.0.0.1:4011/empty` | Session/document lists rỗng |
   | `http://127.0.0.1:4011/error` | REST503, không loop/spinner vô hạn |

   Test network failure bằng cách Ctrl+C **mock server** rồi click refresh/retry chủ động; restart mock để phục hồi. Không đổi API sang backend thật. Endpoint chưa mock sẽ404, không fallback.

8. Chạy **tất cả** hàng trong [accessibility checklist](./frontend-accessibility-checklist.md): desktop, Device Toolbar 320/375px và màn hình thấp, zoom200%, Tab/Shift+Tab/Enter/Escape/PageUp, clipboard allow/deny (DevTools Permissions hoặc Site settings), reduced motion (DevTools Rendering), NVDA hoặc Narrator cho screen reader. Mobile emulation không thay thế touch trên thiết bị thật; ghi rõ mức coverage. Check contrast bằng browser accessibility inspector/contrast tool, không suy luận từ màu source.

9. Sau QA: Ctrl+C frontend để restore env; Ctrl+C mock để reset data. Khởi động lại frontend bình thường bằng cấu hình trước task nếu cần.

## Evidence cần lưu trước khi COMPLETED

### F7-03-05 — Integrated gate (2026-10-15)

Browser bootstrap chính thức vẫn lỗi import `Cannot redefine property: process`, trước setup/connection/navigation. Actual backend source/runtime OpenAPI/CORS và production HTML/client asset delivery PASS; đây không phải UI/browser acceptance. Không có manual outcomes mới để chuyển checklist thành PASS.

[Functional QA report](./frontend-functional-qa.md) ghi coverage và debt disposition. Ngoài browser blocker, [BUG-STREAM-001](./bugs/stream-terminal-parity.md) đã tái hiện: whitespace-only error SSE PARTIAL/history FAILED. Backend selected runner80/81 PASS/1 FAIL; frontend193/193 giữ safe warning/no replay. Bugfix backend phải được giao riêng theo scope task05; không skip regression hoặc waive gate. Chạy toàn bộ extensions task02/03/04 dưới đây và accessibility checklist khi Browser/runtime tương thích hoặc developer kiểm thử Chrome/Edge. F8 chưa bắt đầu.

### F7-03-02 — Session Actions manual extension (NOT RUN)

Retry ngày2026-10-14: bootstrap chính thức vẫn lỗi import `Cannot redefine property: process`, kể cả sau reset phiên công cụ; basic execution/builtin import hoạt động. Agent GET `/chat` và `/documents` trên port3000 đều200. Targeted Session Actions/sidebar/mock tests PASS15/15. Không tới được bước browser connection hoặc navigation, nên các bước keyboard/focus/mobile dưới đây **vẫn NOT RUN**. Không sửa UI/runtime/plugin hoặc dừng server developer trong lượt retry này. Cần Browser/runtime tương thích hoặc developer chạy Chrome/Edge và ghi kết quả thực tế theo template; không suy luận PASS từ HTTP/tests.

Mock đã hỗ trợ PATCH/DELETE sessions, tombstone410/idempotent receipt và DELETE409 khi mock stream còn hoạt động. Document mutations vẫn trả503/no persistence. Dùng quy trình terminal/env restore ở trên với base URL `http://127.0.0.1:4011/many` để seed60 sessions, không backend/provider calls.

- Sidebar “Tải thêm phiên” phải truy cập được sessions51–60; refresh không duplicate; first-page/empty/error/loading recovery đúng.
- Mở menu bằng Tab/Enter/Space, dùng arrows và Escape; trigger có tên session. Rename focus vào input; blank/201+ characters bị chặn, cancel không PATCH, valid title cập nhật từ response/reload; emoji code-point limit đúng.
- Delete dialog ban đầu focus Hủy. Cancel/Escape khi idle không DELETE; confirmed delete của current session → /chat và không old history/deltas. Delete session khác giữ route hiện tại. Focus quay trigger còn tồn tại, hoặc New Chat/main nếu row đã xóa.
- Trong mock stream, confirm DELETE phải nhận409 và không navigate/remove/retry tự động; PATCH title được phép bởi contract. Stop generating rồi kiểm tra lại chủ động trước khi xác nhận mới. Không dùng live backend để thử thao tác này.
- Stop mock server để thử network uncertainty, kiểm tra không tuyên bố thành công; restore mock và refresh trước thao tác mới. Browser Back/route change giữa pending mutation không bị callback cũ kéo về session cũ.
- Kiểm tra mobile320/375px, long titles, keyboard focus/confirmation trap/return/Escape và screen reader. Tất cả các mục trên vẫn NOT RUN cho đến khi developer hoặc Browser có evidence; SSR/controller tests không thay thế manual UX.

### F7-03-03 — Chat Actions manual extension (2026-10-15, NOT RUN)

Bootstrap Browser vẫn FAIL tại import `Cannot redefine property: process`, trước setup/connection/navigation. Dùng Chrome/Edge với mock và env restore ở trên; không backend/provider calls. Chưa có manual PASS từ các SSR/effect/HTTP tests.

- Mở `/chat`, gửi một câu hỏi: một POST `/sessions`, session xuất hiện sidebar ngay sau confirmed creation/list reread; refresh lỗi có retry chủ động. Khi stream chạy URL vẫn `/chat`; thử bấm gửi trùng không tạo lượt/session thứ hai.
- Banner cho biết URL được chuyển sau terminal + verified history và refresh `/chat` trước lúc đó không khôi phục phiên. Mở/lưu link phiên trong tab mới không dừng stream ở tab cũ. Khi hoàn tất URL chuyển đúng session; refresh tải đúng history.
- Trong tab history mở giữa stream: thấy STREAMING/PENDING nếu backend trả về, nội dung đã lưu, không spinner live/Stop giả. “Tải lại lịch sử” là full GET/navigation chủ động, không polling/resume. Gửi câu hỏi chủ động khi mock stream khác đang active nhận409 một lần, spinner kết thúc; không thay status message cũ hoặc tự retry.
- Đợi tab đầu kết thúc rồi tải lại history: trạng thái đọc mới từ backend. Gửi thêm hai lượt, giữ session ID và request IDs riêng; không trộn với session khác khi chuyển route.
- `[disconnect]`, `[error]`, Stop và network failure: giữ partial text/ID/recovery link, không chuyển URL tự động khi chưa verified; không tự gửi lại. Mở lại lịch sử để xác minh chủ động. Reload history có thể thiếu ordered sources: persisted citations còn hiển thị, ordinal thiếu metadata vẫn fallback.
- Kiểm tra copy exact whitespace/denied, source drawer đúng assistant, Tab/Enter/focus, mobile320/375px và zoom200% cho banner/link/history. Không Edit/Regenerate/Delete Message. Ghi browser/version/viewport và actual outcomes theo template dưới.

### F7-03-04 — Document Actions manual extension (2026-10-15, NOT RUN)

Browser bootstrap tiếp tục FAIL tại import `Cannot redefine property: process`, trước navigation. Callback/effect/HTTP tests không chứng minh Escape/focus trap/mobile/hydration PASS.

Dùng quy trình terminal/mock/env restore ở trên, đổi API base thành **`http://127.0.0.1:4011/lifecycle`** rồi restart dev instance của project. Chỉ dùng synthetic TXT vài bytes. Profile này opt-in, giữ document/version metadata trong RAM; không lưu raw file, không gọi backend/embedding/provider, không parse/index thật. Default và `/many` document mutations vẫn503 như trước. Restart mock reset mọi lifecycle metadata. Body cap2MiB là giới hạn harness, không phải giới hạn backend/frontend được công bố.

- DevTools Network phải chỉ tới loopback4011/lifecycle. GET list/detail có fixture INDEXED/PROCESSING/FAILED. Kiểm tra status và active version riêng; PROCESSING không cho tạo version/re-index, không có active version thì re-index bị khóa.
- Upload `qa-upload.txt`: pending không có phần trăm hoặc thành công giả; duplicate submit không tạo thêm POST. Sau201, receipt/status/activated đúng mock response và list tự tải lại. File rỗng/unsupported bị chặn trước request. Dialog close/Escape/backdrop bị chặn trong pending; Stop waiting không tuyên bố server đã hủy ingestion.
- Chọn một document INDEXED, mở “Phiên bản mới”, cancel không PUT. Confirm với `qa-version.txt`: một multipart PUT có field file/boundary do browser tạo, version_count tăng và active ID đổi theo GET detail. Re-index gọi đúng POST `/re-index` không body; tạo version mới dùng filename của active version, không mutate version cũ.
- Version `qa-fail.txt`: mock500, version mới FAILED được đọc lại, active cũ/status document INDEXED giữ nguyên. UI không tự retry hoặc tuyên bố activation. Upload mới tên `qa-fail.txt` tạo document FAILED/không active trong RAM; cần refresh chủ động sau error. Đổi filename khác để chạy success scenario.
- Delete cancel không DELETE; confirm đầu nhận202, row bị loại khi include_deleted=false, detail tombstone/cleanup warning và raw retention vẫn rõ. “Thử cleanup lại” cần proposal/confirmation mới, lần sau200/cleanup_pending=false. Include_deleted đưa tombstone vào list; không có tuyên bố raw files đã bị xóa.
- Mở confirmation ở tab A, mutate cùng fixture từ tab B rồi confirm A: preflight phát hiện stale và cập nhật detail, không gửi mutation theo snapshot cũ. Xem lại và mở confirmation mới nếu muốn thao tác.
- Thử đổi selection/filter hoặc rời route khi pending, rồi quay lại/refresh: không late overwrite selection, không retry tự động. Dừng mock để thử uncertain/network/refresh errors; xem cảnh báo và refresh chủ động. Mutation đã được server nhận vẫn có thể hoàn tất dù client dừng chờ.
- Kiểm tra Tab/Shift+Tab/Enter/Escape, cancel/close/return focus, modal busy, viewport320/375px/màn hình thấp/zoom200%, filename dài và screen reader. Các hàng này vẫn NOT RUN đến khi có actual observations. Không dùng Chrome/Edge để thử các thao tác này trên backend thật.

Mỗi hàng checklist cần `PASS/FAIL`, browser/version, viewport/zoom/input/AT, scenario và actual outcome; screenshot/video hoặc focus/clipboard/screen-reader observations khi phù hợp. Record code whitespace bằng clipboard paste vào text editor (không gửi nội dung ra ngoài). Hàng chưa chạy tiếp tục `NOT RUN`; lỗi phải được tái hiện trước khi sửa UI.

```text
Tester / date:
Chrome/Edge version; OS; screen reader/version:
Commit/worktree tested; mock base URL:
Checklist row; viewport/zoom; input mode:
Steps + actual result:
PASS / FAIL / NOT RUN:
Evidence path / observation:
```

Automated verification trong lần chẩn đoán: mock harness4/4 và regression161/161 PASS; production REST/SSE clients validate fixture payloads, persisted exact content, CORS, empty/error/disconnect/no-metadata và fail-closed routes. Các tests này **không phải** browser manual acceptance. Build/typecheck/contract PASS157-test baseline là evidence lần triển khai trước; không tự nhận đã rerun build trong lần diagnosis.
