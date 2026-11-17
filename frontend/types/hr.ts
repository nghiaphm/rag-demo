/** HR Portal demo UI & domain types (strictly separate from Backend OpenAPI DTO files). */

export type HrPageRoute = "/hr" | "/hr/documents" | "/hr/guide";

export type HrDocumentCategory = "POLICY" | "REGULATION" | "PROCEDURE" | "OTHER";

export interface HrDocumentCategoryMeta {
  id: HrDocumentCategory;
  label: string;
  description: string;
}

export interface HrUserProfile {
  name: string;
  roleTitle: string;
  department: string;
  email: string;
  avatarInitials: string;
  isDemoProfile: true;
}

export interface HrPageContext {
  route: HrPageRoute;
  title: string;
  selectedDocumentId?: string;
  selectedDocumentName?: string;
  selectedCategory?: HrDocumentCategory;
}

export interface HrKpiCard {
  id: string;
  label: string;
  value: string;
  deltaLabel: string;
  trend: "up" | "down" | "neutral";
  helperText: string;
}

export interface DepartmentHeadcount {
  id: string;
  department: string;
  count: number;
  openRoles: number;
}

export interface ContractStatusMetric {
  id: string;
  label: string;
  count: number;
  tone: "primary" | "info" | "warning" | "muted";
}

export interface HrAnalyticsSnapshot {
  asOfLabel: string;
  totalEmployees: number;
  kpis: readonly HrKpiCard[];
  departments: readonly DepartmentHeadcount[];
  contractStatuses: readonly ContractStatusMetric[];
}

export interface HrPromptTemplate {
  id: string;
  title: string;
  prompt: string;
  category: HrDocumentCategory;
}

export interface HrGuideSection {
  id: string;
  title: string;
  summary: string;
  steps: readonly string[];
}
