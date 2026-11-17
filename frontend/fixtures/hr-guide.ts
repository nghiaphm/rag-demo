import type { HrGuideSection, HrPromptTemplate } from "@/types/hr";

export const HR_GUIDE_SECTIONS: readonly HrGuideSection[] = [
  {
    id: "overview",
    title: "Tổng quan cổng thông tin nhân sự",
    summary:
      "HR Portal kết nối trực tiếp với RAG Backend hiện tại để tra cứu chính sách, quy định và quy trình kèm trích dẫn nguồn xác thực.",
    steps: [
      "Bảng tổng quan nhân sự (/hr) hiển thị thống kê nhân sự mô phỏng kết hợp trạng thái kho tài liệu thực từ RAG Backend.",
      "Kho tài liệu nhân sự (/hr/documents) liệt kê toàn bộ tài liệu đang có, hỗ trợ đọc nội dung và tải file mới vào kho tri thức.",
      "RAG Workspace (/chat) giữ vai trò không gian hỏi đáp chính với lịch sử phiên đầy đủ và tùy chỉnh phạm vi tài liệu.",
    ],
  },
  {
    id: "documents",
    title: "Tìm kiếm, phân nhóm và đọc tài liệu",
    summary:
      "Danh sách tài liệu được phân nhóm ngay trên giao diện theo tên file để dễ lọc giữa Chính sách, Quy định và Quy trình.",
    steps: [
      "Chọn tab phân loại (Tất cả, Chính sách, Quy định, Quy trình) hoặc nhập từ khóa tên file vào ô tìm kiếm.",
      "Nhấn vào từng tài liệu để kiểm tra trạng thái xử lý, số lượng chunks và đọc trước nội dung (TXT, MD, XLSX).",
      "Chọn Tải tài liệu lên (.pdf, .txt, .md, .xlsx) để nạp tài liệu mới trực tiếp vào RAG Knowledge Base.",
    ],
  },
  {
    id: "chatbot",
    title: "Hỏi đáp với Trợ lý HR và kiểm chứng trích dẫn",
    summary:
      "Nút Trợ lý HR luôn hiện diện ở thanh tiêu đề và góc dưới bên phải trên mọi trang của HR Portal.",
    steps: [
      "Mở Trợ lý HR từ bất kỳ trang nào và đặt câu hỏi bằng tiếng Việt tự nhiên.",
      "Nội dung hội thoại được giữ liên tục khi bạn chuyển qua lại giữa các trang trong HR Portal.",
      "Nhấp vào thẻ trích dẫn [1], [2] trong câu trả lời để mở bảng đối chiếu tài liệu nguồn và số trang.",
      "Chọn Mở toàn trang để chuyển cuộc hội thoại đang dở sang RAG Workspace tại /chat.",
    ],
  },
  {
    id: "scope-notes",
    title: "Phạm vi tri thức và dữ liệu minh họa",
    summary:
      "Các ranh giới dữ liệu được tách bạch rõ ràng giữa phần mô phỏng HR và dữ liệu thực từ hệ thống RAG.",
    steps: [
      "Các chỉ số nhân sự (184 nhân viên, phòng ban, hợp đồng) là dữ liệu mẫu tĩnh vì Backend hiện chưa có HRIS API.",
      "Tài liệu tải lên từ /hr/documents nằm chung kho tri thức RAG với /documents.",
      "Bộ lọc Chính sách, Quy định và Quy trình chỉ phục vụ hiển thị trên giao diện, không phải cơ chế phân quyền truy cập.",
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
