import type { DocumentInfo } from "@/types/document";
import type { ContractStatusMetric, DepartmentHeadcount } from "@/types/hr";

export interface DepartmentShare extends DepartmentHeadcount {
  sharePercent: number;
  barWidthPercent: number;
}

export interface ContractStatusShare extends ContractStatusMetric {
  sharePercent: number;
}

export interface KnowledgeBaseSummary {
  totalDocuments: number;
  indexedDocuments: number;
  processingDocuments: number;
  failedDocuments: number;
  totalChunks: number;
}

/** Tính tỷ trọng nhân sự và tỉ lệ thanh biểu đồ cho từng phòng ban. */
export function summarizeDepartmentShares(
  departments: readonly DepartmentHeadcount[]
): DepartmentShare[] {
  const total = departments.reduce((sum, item) => sum + item.count, 0);
  const maxCount = Math.max(0, ...departments.map((item) => item.count));

  return departments.map((item) => ({
    ...item,
    sharePercent: total > 0 ? Math.round((item.count / total) * 1000) / 10 : 0,
    barWidthPercent: maxCount > 0 ? Math.round((item.count / maxCount) * 100) : 0,
  }));
}

/** Tính tỷ trọng trạng thái nhân viên / hợp đồng theo tổng số nhân sự. */
export function summarizeContractStatuses(
  statuses: readonly ContractStatusMetric[]
): ContractStatusShare[] {
  const total = statuses.reduce((sum, item) => sum + item.count, 0);
  return statuses.map((item) => ({
    ...item,
    sharePercent: total > 0 ? Math.round((item.count / total) * 1000) / 10 : 0,
  }));
}

/** Tổng hợp thống kê thực tế từ danh sách DocumentInfo trả về bởi GET /documents. */
export function summarizeKnowledgeBaseDocuments(
  documents: readonly DocumentInfo[]
): KnowledgeBaseSummary {
  let indexedDocuments = 0;
  let processingDocuments = 0;
  let failedDocuments = 0;
  let totalChunks = 0;

  for (const doc of documents) {
    if (doc.status === "INDEXED") {
      indexedDocuments += 1;
      totalChunks += doc.chunk_count;
    } else if (doc.status === "PROCESSING" || doc.status === "UPLOADED") {
      processingDocuments += 1;
    } else if (doc.status === "FAILED") {
      failedDocuments += 1;
    }
  }

  return {
    totalDocuments: documents.length,
    indexedDocuments,
    processingDocuments,
    failedDocuments,
    totalChunks,
  };
}
