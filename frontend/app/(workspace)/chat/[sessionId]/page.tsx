import { Suspense } from "react";

import { SessionChat } from "@/components/chat/session-chat";

interface ChatPageProps {
  params: Promise<{ sessionId: string }>;
}

async function SessionChatContent({ params }: ChatPageProps) {
  const { sessionId } = await params;
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || null;
  return <SessionChat apiBaseUrl={apiBaseUrl} sessionId={sessionId} />;
}

export default function ChatPage({ params }: ChatPageProps) {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Đang mở phiên trò chuyện…</p>}>
      <SessionChatContent params={params} />
    </Suspense>
  );
}
