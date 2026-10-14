import { DocumentsPreview } from "@/components/documents/documents-preview";

export default function DocumentsPage() {
  return <DocumentsPreview apiBaseUrl={process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || null} />;
}
