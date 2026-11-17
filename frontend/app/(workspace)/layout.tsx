import { AppShell } from "@/components/layout/app-shell";

export default function WorkspaceLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || null;
  return <AppShell apiBaseUrl={apiBaseUrl}>{children}</AppShell>;
}
