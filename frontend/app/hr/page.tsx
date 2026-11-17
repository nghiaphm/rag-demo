import Link from "next/link";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function HrOverviewPage() {
  return (
    <section aria-labelledby="hr-overview-placeholder" className="mx-auto w-full max-w-5xl space-y-4">
      <Card>
        <CardHeader>
          <CardTitle id="hr-overview-placeholder">HR Portal Demo — Đã sẵn sàng khung điều hướng</CardTitle>
          <CardDescription>
            Route Group (workspace) và HrShell đã được tách độc lập khỏi RAG Workspace.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          <p>
            Các module Dashboard &amp; Analytics (Phase H2), HR Document Center (Phase H3), Global HR Chatbot &amp; User Guide (Phase H4) sẽ được tích hợp tuần tự vào khung này.{" "}
            <Link href="/chat" className="underline text-foreground">
              Quay về RAG Workspace (/chat)
            </Link>
            .
          </p>
        </CardContent>
      </Card>
    </section>
  );
}
