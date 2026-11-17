import { HrDocumentsView } from "@/components/hr/documents/hr-documents-view";

export default function HrDocumentsPage() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || null;
  return <HrDocumentsView apiBaseUrl={apiBaseUrl} />;
}
