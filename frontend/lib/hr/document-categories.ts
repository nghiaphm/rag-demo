import type { DocumentInfo } from "@/types/document";
import type { HrDocumentCategory, HrDocumentCategoryMeta } from "@/types/hr";

export const HR_DOCUMENT_CATEGORIES: readonly HrDocumentCategoryMeta[] = [
  {
    id: "POLICY",
    label: "Chính sách",
    description: "Phúc lợi, lương thưởng, nghỉ phép, bảo hiểm và chế độ đãi ngộ.",
  },
  {
    id: "REGULATION",
    label: "Quy định",
    description: "Nội quy lao động, bảo mật thông tin, kỷ luật và quy tắc ứng xử.",
  },
  {
    id: "PROCEDURE",
    label: "Quy trình",
    description: "Onboarding, đánh giá, nghỉ việc, duyệt chi và hướng dẫn thực thi (SOP).",
  },
  {
    id: "OTHER",
    label: "Tài liệu chung",
    description: "Các tài liệu chưa gắn từ khóa phân loại Chính sách / Quy định / Quy trình.",
  },
] as const;

const CATEGORY_LABELS: Record<HrDocumentCategory, string> = {
  POLICY: "Chính sách",
  REGULATION: "Quy định",
  PROCEDURE: "Quy trình",
  OTHER: "Tài liệu chung",
};

function normalizeForMatching(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[đĐ]/g, "d")
    .toLowerCase();
}

const CATEGORY_RULES: readonly { category: HrDocumentCategory; keywords: readonly string[] }[] = [
  {
    category: "POLICY",
    keywords: ["policy", "chinh-sach", "chinh sach", "chinh_sach", "phuc-loi", "phuc loi", "nghi-phep", "nghi phep", "benefit", "luong", "thuong", "allowance", "leave"],
  },
  {
    category: "REGULATION",
    keywords: ["regulation", "quy-dinh", "quy dinh", "quy_dinh", "noi-quy", "noi quy", "noi_quy", "rule", "ky-luat", "bao-mat", "security", "conduct", "compliance"],
  },
  {
    category: "PROCEDURE",
    keywords: ["procedure", "quy-trinh", "quy trinh", "quy_trinh", "sop", "onboarding", "offboarding", "workflow", "huong-dan", "huong dan", "process", "handbook"],
  },
];

/**
 * Suy luận phân loại hiển thị phía client từ tên tài liệu.
 * Backend hiện chưa lưu trường category cho DocumentRecord.
 */
export function classifyHrDocument(fileName: string): HrDocumentCategory {
  const normalized = normalizeForMatching(fileName);
  for (const rule of CATEGORY_RULES) {
    if (rule.keywords.some((keyword) => normalized.includes(keyword))) {
      return rule.category;
    }
  }
  return "OTHER";
}

export function getHrCategoryLabel(category: HrDocumentCategory): string {
  return CATEGORY_LABELS[category];
}

export function countDocumentsByCategory(
  documents: readonly DocumentInfo[]
): Record<HrDocumentCategory | "ALL", number> {
  const counts: Record<HrDocumentCategory | "ALL", number> = {
    ALL: documents.length,
    POLICY: 0,
    REGULATION: 0,
    PROCEDURE: 0,
    OTHER: 0,
  };
  for (const doc of documents) {
    counts[classifyHrDocument(doc.file_name)] += 1;
  }
  return counts;
}

export function filterHrDocuments(
  documents: readonly DocumentInfo[],
  options: { category?: HrDocumentCategory | "ALL"; query?: string }
): DocumentInfo[] {
  const category = options.category ?? "ALL";
  const normalizedQuery = normalizeForMatching((options.query ?? "").trim());

  return documents.filter((doc) => {
    if (category !== "ALL" && classifyHrDocument(doc.file_name) !== category) {
      return false;
    }
    if (normalizedQuery && !normalizeForMatching(doc.file_name).includes(normalizedQuery)) {
      return false;
    }
    return true;
  });
}
