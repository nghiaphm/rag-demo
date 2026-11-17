import { HrDashboardView } from "@/components/hr/dashboard/hr-dashboard-view";

export default function HrOverviewPage() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || null;
  return <HrDashboardView apiBaseUrl={apiBaseUrl} />;
}
