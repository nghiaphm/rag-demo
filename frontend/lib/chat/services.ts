import { createChatStreamClient } from "@/lib/api/chat";
import { createApiClient } from "@/lib/api/client";
import { createSession, listSessionMessages } from "@/lib/api/sessions";
import type { ChatControllerServices } from "@/lib/chat/controller";
import { historyMessageToViewMessage, loadMessageHistory } from "@/lib/sessions/history";
import { invalidateSessionList } from "@/lib/sessions/invalidation";

/** Shared composer wiring; confirmed creation invalidates the existing list owner. */
export function createChatServices(baseUrl: string): ChatControllerServices {
  const api = createApiClient({ baseUrl });
  const streamClient = createChatStreamClient({ baseUrl });
  return {
    createSession: async (signal) => {
      const session = await createSession(api, {}, signal);
      if (!signal.aborted) invalidateSessionList(baseUrl);
      return session;
    },
    stream: async (payload, options) => {
      try {
        return await streamClient.stream(payload, options);
      } finally {
        // Refresh titles/order after a completed or failed request, never replay it.
        if (!options?.signal?.aborted) invalidateSessionList(baseUrl);
      }
    },
    loadHistory: async (id, signal) => (await loadMessageHistory(id, {
      list: (sessionId, query, pageSignal) => listSessionMessages(api, sessionId, query, pageSignal),
    }, signal)).map(historyMessageToViewMessage),
  };
}
