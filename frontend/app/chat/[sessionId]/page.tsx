import { Suspense } from "react";

import { SessionChat } from "@/components/chat/session-chat";

async function SessionChatContent({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = await params;
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || null;
  return <SessionChat apiBaseUrl={apiBaseUrl} sessionId={sessionId} />;
}

export default function ChatPage({ params }: PageProps<"/chat/[sessionId]">) {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Đang mở phiên trò chuyện…</p>}>
      <SessionChatContent params={params} />
    </Suspense>
  );
}
