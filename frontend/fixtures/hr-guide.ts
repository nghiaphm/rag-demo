import type { HrGuideSection, HrPromptTemplate } from "@/types/hr";

export const HR_GUIDE_SECTIONS: readonly HrGuideSection[] = [
  {
    id: "overview",
    title: "1. Tổng quan hệ thống HR Portal & RAG",
    summary:
      "HR Portal kết nối trực tiếp với hệ thống RAG Backend hiện có để tra cứu chính sách, quy định và quy trình nhân sự kèm trích dẫn nguồn xác thực.",
    steps: [
      "Dashboard (/hr) hiển thị thống kê nhân sự mô phỏng kết hợp trạng thái kho tài liệu thực từ RAG Backend.",
      "Kho tài liệu nhân sự (/hr/documents) hiển thị toàn bộ tài liệu đã tải lên, hỗ trợ xem nội dung và nạp thêm tài liệu mới vào kho tri thức.",
      "RAG Workspace (/chat) vẫn là không gian làm việc đầy đủ để trò chuyện nhiều lượt, cấu hình phạm vi tài liệu và xem lịch sử phiên.",
    ],
  },
  {
    id: "documents",
    title: "2. Tìm kiếm, phân loại & xem tài liệu (/hr/documents)",
    summary:
      "Tài liệu được phân nhóm hiển thị ở phía giao diện dựa theo tên file để tra cứu nhanh giữa Chính sách, Quy định và Quy trình.",
    steps: [
      "Chọn tab phân loại (Tất cả / Chính sách / Quy định / Quy trình) hoặc gõ từ khóa tên tài liệu vào ô tìm kiếm.",
      "Nhấn vào một tài liệu để xem trạng thái index (INDEXED / PROCESSING / FAILED), số lượng chunks và nội dung chi tiết (TXT, MD, XLSX).",
      "Dùng nút 'Thêm tài liệu HR' để tải file mới (.pdf, .txt, .md, .xlsx) vào RAG Knowledge Base dùng chung.",
    ],
  },
  {
    id: "chatbot",
    title: "3. Sử dụng Trợ lý HR Chatbot & trích dẫn [n]",
    summary:
      "Nút Trợ lý HR luôn sẵn sàng ở thanh Header và góc dưới bên phải trên mọi trang của HR Portal.",
    steps: [
      "Mở Trợ lý HR từ bất kỳ trang nào (/hr, /hr/documents, /hr/guide) và đặt câu hỏi bằng tiếng Việt tự nhiên.",
      "Cuộc hội thoại được giữ liên tục khi bạn chuyển qua lại giữa các trang trong HR Portal.",
      "Nhấp vào các thẻ trích dẫn [1], [2]... trong câu trả lời để mở drawer kiểm tra tài liệu nguồn và số trang tương ứng.",
      "Nhấn 'Mở toàn trang' trên khung chat nếu muốn chuyển sang giao diện RAG Workspace đầy đủ tại /chat/[sessionId].",
    ],
  },
  {
    id: "scope-notes",
    title: "4. Lưu ý về phạm vi tri thức & dữ liệu Demo",
    summary:
      "Hiểu đúng nguồn dữ liệu giúp minh bạch khi trình diễn và kiểm thử.",
    steps: [
      "Các chỉ số nhân sự (184 nhân viên, cơ cấu phòng ban, hợp đồng) là dữ liệu mẫu tĩnh vì Backend hiện chưa có HRIS API.",
      "Tài liệu tải lên từ /hr/documents chia sẻ chung kho tri thức RAG với /documents.",
      "Bộ lọc Chính sách / Quy định / Quy trình chỉ dùng để hiển thị danh sách trên giao diện, không phải cơ chế phân quyền truy cập.",
    ],
  },
];

export const HR_PROMPT_TEMPLATES: readonly HrPromptTemplate[] = [
  {
    id: "leave-policy",
    title: "Chính sách nghỉ phép năm",
    prompt: "Chính sách nghỉ phép năm và điều kiện cộng dồn phép của công ty được quy định như thế nào?",
    category: "POLICY",
  },
  {
    id: "onboarding-flow",
    title: "Quy trình Onboarding nhân viên mới",
    prompt: "Tóm tắt quy trình onboarding trong tuần đầu tiên cho nhân viên mới.",
    category: "PROCEDURE",
  },
  {
    id: "probation-eval",
    title: "Đánh giá kết thúc thử việc",
    prompt: "Quy định về thời gian thử việc, tiêu chí đánh giá và quyền lợi sau khi lên chính thức là gì?",
    category: "REGULATION",
  },
  {
    id: "overtime-allowance",
    title: "Chính sách làm thêm giờ (OT)",
    prompt: "Điều kiện duyệt làm thêm giờ và mức phụ cấp / nghỉ bù được tính như thế nào?",
    category: "POLICY",
  },
  {
    id: "security-rules",
    title: "Nội quy bảo mật thông tin",
    prompt: "Các quy định chính về bảo mật thông tin nội bộ và dữ liệu khách hàng mà nhân viên phải tuân thủ?",
    category: "REGULATION",
  },
  {
    id: "offboarding-flow",
    title: "Quy trình bàn giao nghỉ việc",
    prompt: "Nhân viên cần thực hiện các bước bàn giao nào trước khi nghỉ việc theo quy trình hiện hành?",
    category: "PROCEDURE",
  },
];
