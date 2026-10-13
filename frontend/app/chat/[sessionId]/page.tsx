import { Suspense } from "react";

import { ChatPreview } from "@/components/chat/chat-preview";

async function SessionChat({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = await params;
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || null;
  return <ChatPreview apiBaseUrl={apiBaseUrl} initialSessionId={sessionId} />;
}

export default function ChatPage({ params }: PageProps<"/chat/[sessionId]">) {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Đang mở phiên trò chuyện…</p>}>
      <SessionChat params={params} />
    </Suspense>
  );
}
