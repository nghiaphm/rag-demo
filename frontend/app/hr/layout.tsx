import { HrChatbotProvider } from "@/components/hr/layout/hr-chatbot-provider";
import { HrShell } from "@/components/hr/layout/hr-shell";

export default function HrLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || null;
  return (
    <HrChatbotProvider>
      <HrShell apiBaseUrl={apiBaseUrl}>{children}</HrShell>
    </HrChatbotProvider>
  );
}
