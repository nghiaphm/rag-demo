import { test as base, expect } from "@playwright/test"
import { createQaMockServer } from "../scripts/qa-mock-api.mjs"

type Qa = { profile: string; requests: { method: string; path: string; body: string | null }[]; blocked: string[]; lagHistoryReads: number }

export const test = base.extend<{ qa: Qa; streamDelayMs: number; apiDelayMs: number }>({
  streamDelayMs: [50, { option: true }],
  apiDelayMs: [25, { option: true }],
  qa: [async ({ context, streamDelayMs, apiDelayMs }, provide) => {
    const server = createQaMockServer({ delayMs: apiDelayMs, deltaMs: streamDelayMs })
    await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve))
    const address = server.address()
    if (!address || typeof address === "string") throw new Error("Mock did not bind loopback")
    const qa: Qa = { profile: "/lifecycle", requests: [], blocked: [], lagHistoryReads: 0 }
    const runtimeErrors: string[] = []
    context.on("page", page => page.on("pageerror", error => runtimeErrors.push(error.message)))
    await context.route("**/*", async route => {
      const request = route.request(), url = new URL(request.url())
      if (url.origin === "http://127.0.0.1:3100") { await route.continue(); return }
      if (url.origin === "http://127.0.0.1:4011" && url.pathname.startsWith("/lifecycle/")) {
        qa.requests.push({ method: request.method(), path: url.pathname, body: request.postData() })
        url.port = String(address.port)
        url.pathname = qa.profile + url.pathname.slice("/lifecycle".length)
        if (request.method() === "GET" && url.pathname.endsWith("/messages") && qa.lagHistoryReads > 0) {
          qa.lagHistoryReads--
          const response = await route.fetch({ url: url.toString() })
          const history = await response.json()
          const last = history.items.at(-1)
          await route.fulfill({ response, json: { ...history, items: history.items.map((item: { message_id: string }) =>
            item.message_id === last.message_id ? { ...item, status: "STREAMING", completed_at: null } : item) } })
          return
        }
        await route.continue({ url: url.toString() }); return
      }
      qa.blocked.push(url.origin + url.pathname)
      await route.abort("blockedbyclient")
    })
    try { await provide(qa) } finally {
      server.closeAllConnections()
      await new Promise<void>(resolve => server.close(() => resolve()))
      expect(qa.blocked, "No request to a backend/provider/unexpected origin is allowed").toEqual([])
      expect(runtimeErrors, "No uncaught browser exceptions").toEqual([])
    }
  }, { auto: true }],
})
export { expect }
