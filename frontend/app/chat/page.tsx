import { ChatPreview } from "@/components/chat/chat-preview";

export default function ChatPage() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || null;
  return <ChatPreview apiBaseUrl={apiBaseUrl} />;
}
