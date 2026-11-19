import { HR_PROMPT_TEMPLATES } from "@/fixtures/hr-guide";
import type { HrTourScope, HrTourStep } from "@/types/hr";

export const HR_PRODUCT_TOUR_STEPS: readonly HrTourStep[] = [
  {
    id: "kpi-overview",
    scope: "dashboard",
    route: "/hr",
    targetId: "hr-kpi-strip",
    placement: "bottom",
    eyebrow: "Tổng quan nhân sự",
    title: "Theo dõi nhanh các chỉ số nhân sự trọng tâm",
    description:
      "Dải chỉ số hiển thị quy mô 184 nhân sự, tỷ lệ giữ chân và nhu cầu tuyển dụng đang mở dưới dạng dữ liệu minh họa HR để bạn kiểm tra nhanh ngữ cảnh cổng nhân sự.",
    actionHint: "Dữ liệu nhân sự ở khối này là fixture tĩnh phục vụ demo giao diện.",
  },
  {
    id: "workforce-charts",
    scope: "dashboard",
    route: "/hr",
    targetId: "hr-analytics-charts",
    placement: "top",
    eyebrow: "Phân tích cơ cấu",
    title: "Phân bổ theo phòng ban và loại hợp đồng",
    description:
      "Cặp biểu đồ giúp HR Manager nhìn nhanh mật độ nhân sự theo từng khối chuyên môn cũng như tỷ trọng hợp đồng chính thức, thử việc và thực tập.",
  },
  {
    id: "live-rag-kb",
    scope: "dashboard",
    route: "/hr",
    targetId: "hr-live-kb",
    placement: "top",
    eyebrow: "Kết nối dữ liệu thật",
    title: "Kho tri thức RAG đồng bộ trực tiếp từ API",
    description:
      "Khác với số liệu nhân sự minh họa phía trên, khối này đọc trực tiếp từ GET /documents để theo dõi số tài liệu đã INDEXED, đang xử lý và tổng vector chunks.",
  },
  {
    id: "document-filters",
    scope: "documents",
    route: "/hr/documents",
    targetId: "hr-docs-filters",
    placement: "bottom",
    eyebrow: "Kho tài liệu HR",
    title: "Phân nhóm chính sách và tìm kiếm tức thời",
    description:
      "Tài liệu được gắn nhãn tự động theo tên file thành Chính sách, Quy định và Quy trình để tra cứu nhanh. Nhãn này chỉ phục vụ hiển thị UI, dùng chung kho với /documents.",
  },
  {
    id: "document-workbench",
    scope: "documents",
    route: "/hr/documents",
    targetId: "hr-docs-workbench",
    placement: "top",
    eyebrow: "Đọc & Nạp tài liệu",
    title: "Xem trước nội dung và tải file mới vào RAG",
    description:
      "Nhấp vào bất kỳ tài liệu nào ở cột trái để kiểm tra trạng thái, số chunks và đọc trước nội dung (TXT, MD, XLSX) hoặc bấm Tải tài liệu lên để nạp thêm chính sách mới.",
  },
  {
    id: "chatbot-assistant",
    scope: "copilot",
    targetId: "hr-chatbot-drawer",
    placement: "left",
    eyebrow: "Trợ lý HR theo ngữ cảnh",
    title: "Hỏi đáp chính sách & thao tác trang kèm trích dẫn [n]",
    description:
      "Khung Trợ lý HR nhận biết trang bạn đang mở để hướng dẫn thao tác trực tiếp, đồng thời kết nối RAG Backend qua SSE streaming và hiển thị trích dẫn nguồn [1], [2].",
    actionHint: "Nhấn nút bên dưới để điền sẵn câu hỏi mẫu vào khung chat mà không gọi RAG tự động.",
    opensChatbot: true,
    suggestedPrompt: HR_PROMPT_TEMPLATES[0].prompt,
  },
];

export function getHrTourSteps(scope: HrTourScope = "all"): readonly HrTourStep[] {
  if (scope === "all") return HR_PRODUCT_TOUR_STEPS;
  return HR_PRODUCT_TOUR_STEPS.filter((step) => step.scope === scope);
}
