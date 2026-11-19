import { Be_Vietnam_Pro, Plus_Jakarta_Sans } from "next/font/google";

import { HrChatbotProvider } from "@/components/hr/layout/hr-chatbot-provider";
import { HrShell } from "@/components/hr/layout/hr-shell";
import { HrTourProvider } from "@/components/hr/tour/hr-tour-provider";

import "./hr-theme.css";

const plusJakarta = Plus_Jakarta_Sans({
  variable: "--font-hr-display",
  subsets: ["latin", "vietnamese"],
  weight: ["500", "600", "700"],
});

const beVietnam = Be_Vietnam_Pro({
  variable: "--font-hr-body",
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600"],
});

export default function HrLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || null;
  return (
    <div
      className={`${plusJakarta.variable} ${beVietnam.variable} hr-theme min-h-svh bg-background font-sans text-foreground antialiased`}
    >
      <HrChatbotProvider>
        <HrTourProvider>
          <HrShell apiBaseUrl={apiBaseUrl}>{children}</HrShell>
        </HrTourProvider>
      </HrChatbotProvider>
    </div>
  );
}
