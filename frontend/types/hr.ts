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
  title?: string;
  purpose?: string;
  selectedDocumentId?: string;
  selectedDocumentName?: string;
  selectedCategory?: HrDocumentCategory;
  searchQuery?: string;
  liveFeatures?: readonly string[];
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

export type HrTourTargetId =
  | "hr-kpi-strip"
  | "hr-analytics-charts"
  | "hr-live-kb"
  | "hr-docs-filters"
  | "hr-docs-workbench"
  | "hr-chatbot-drawer";

export type HrTourPlacement = "top" | "bottom" | "left" | "right" | "center";

export type HrTourCompletionState = "completed" | "dismissed";

export type HrTourScope = "all" | "dashboard" | "documents" | "copilot";

export interface HrTourStep {
  id: string;
  scope: Exclude<HrTourScope, "all">;
  route?: HrPageRoute;
  targetId: HrTourTargetId;
  placement: HrTourPlacement;
  eyebrow: string;
  title: string;
  description: string;
  actionHint?: string;
  opensChatbot?: boolean;
  suggestedPrompt?: string;
}
