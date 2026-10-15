// In-memory read invalidation only; the API remains the session list authority.
// No cached sessions, cross-tab storage, polling, or generation replay.
const listeners = new Map<string, Set<() => void>>();
const scope = (baseUrl: string) => baseUrl.replace(/\/+$/, "");

export function subscribeSessionList(baseUrl: string, listener: () => void) {
  const key = scope(baseUrl);
  const group = listeners.get(key) ?? new Set<() => void>();
  group.add(listener);
  listeners.set(key, group);
  return () => {
    group.delete(listener);
    if (!group.size) listeners.delete(key);
  };
}

export function invalidateSessionList(baseUrl: string) {
  for (const listener of listeners.get(scope(baseUrl)) ?? []) listener();
}
