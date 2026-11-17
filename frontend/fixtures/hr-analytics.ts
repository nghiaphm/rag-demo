import type { HrAnalyticsSnapshot } from "@/types/hr";

/**
 * Dữ liệu nhân sự mô phỏng cho HR Portal Demo.
 * Backend hiện chưa cung cấp HRIS API; toàn bộ số liệu này là fixture tĩnh.
 */
export const HR_ANALYTICS_FIXTURE: HrAnalyticsSnapshot = {
  asOfLabel: "Dữ liệu mô phỏng HR · Quý 4/2026",
  totalEmployees: 184,
  kpis: [
    {
      id: "total-headcount",
      label: "Tổng nhân sự",
      value: "184",
      deltaLabel: "+6.4% so với quý trước",
      trend: "up",
      helperText: "Bao gồm toàn thời gian, thử việc và cộng tác viên",
    },
    {
      id: "new-hires",
      label: "Nhân sự mới (tháng)",
      value: "12",
      deltaLabel: "Đạt 92% kế hoạch tuyển dụng",
      trend: "up",
      helperText: "Tập trung ở Kỹ thuật & Vận hành",
    },
    {
      id: "turnover-rate",
      label: "Tỉ lệ nghỉ việc",
      value: "2.1%",
      deltaLabel: "-0.4% so với cùng kỳ",
      trend: "down",
      helperText: "Mức ổn định dưới ngưỡng mục tiêu 3.0%",
    },
    {
      id: "avg-tenure",
      label: "Thâm niên trung bình",
      value: "3.4 năm",
      deltaLabel: "Tỉ lệ gắn bó > 2 năm: 68%",
      trend: "neutral",
      helperText: "Tính trên hợp đồng lao động chính thức",
    },
  ],
  departments: [
    { id: "eng", department: "Kỹ thuật & Sản phẩm", count: 68, openRoles: 5 },
    { id: "ops", department: "Vận hành & CSKH", count: 38, openRoles: 2 },
    { id: "sales", department: "Kinh doanh", count: 32, openRoles: 3 },
    { id: "hr", department: "Nhân sự & Hành chính", count: 16, openRoles: 1 },
    { id: "fin", department: "Tài chính & Kế toán", count: 16, openRoles: 0 },
    { id: "mkt", department: "Marketing & Tăng trưởng", count: 14, openRoles: 2 },
  ],
  contractStatuses: [
    { id: "indefinite", label: "HĐ không xác định thời hạn", count: 132, tone: "primary" },
    { id: "fixed-term", label: "HĐ xác định thời hạn", count: 31, tone: "info" },
    { id: "probation", label: "Đang thử việc", count: 14, tone: "warning" },
    { id: "intern", label: "Thực tập / Cộng tác viên", count: 7, tone: "muted" },
  ],
};
