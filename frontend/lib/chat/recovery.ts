import type { ChatState, ChatViewMessage } from "@/lib/chat/controller";

export function isHistoricalNonterminal(message: ChatViewMessage) {
  return message.origin === "history" && (message.status === "PENDING" || message.status === "STREAMING");
}

/** Do not remount the keyed workspace while streaming or persistence is uncertain. */
export function canonicalChatPath(initialSessionId: string | null, state: ChatState) {
  return !initialSessionId && state.sessionId && !state.isGenerating && state.historyVerified && !state.persistenceError
    ? `/chat/${encodeURIComponent(state.sessionId)}` : null;
}
