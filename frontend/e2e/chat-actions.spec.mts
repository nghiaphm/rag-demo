import { test, expect } from "./fixtures.mjs"

const a = "aaaaaaaa-1111-4111-8111-111111111111"
const b = "bbbbbbbb-1111-4111-8111-111111111111"
const question = (page: import("@playwright/test").Page) => page.getByRole("textbox", { name: "Câu hỏi", exact: true })
const assistant = (page: import("@playwright/test").Page) => page.getByRole("article", { name: "Câu trả lời của trợ lý", exact: true })
const streamPosts = (qa: { requests: { method: string; path: string; body: string | null }[] }) => qa.requests.filter(r => r.method === "POST" && r.path.endsWith("/chat/stream"))
const recoveryName = "Mở lịch sử trong tab mới (có thể lưu liên kết phiên)"

test.describe("deferred first-turn URL", () => {
  test.use({ streamDelayMs: 200 })
  test("composer reconciles sidebar before terminal; new tab is a snapshot, intentional submit gets409, terminal canonicalizes", async ({ page, qa }) => {
    await page.goto("/chat")
    await question(page).fill("composer sidebar live fixture")
    await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).press("Enter")
    const recovery = page.getByRole("link", { name: recoveryName, exact: true })
    await expect(recovery).toBeVisible()
    const href = (await recovery.getAttribute("href"))!
    const id = href.split("/").at(-1)!
    await expect(page.locator(`a[href='${href}']`).filter({ hasText: "QA new chat" })).toBeVisible()
    await expect(page).toHaveURL(/\/chat$/)
    await expect(page.getByText(/tải lại trang \/chat sẽ không tự mở lại phiên này/)).toBeVisible()
    await expect(question(page)).toHaveAttribute("aria-readonly", "true")
    await question(page).press("Enter")
    expect(streamPosts(qa)).toHaveLength(1)
    const popupPromise = page.waitForEvent("popup")
    await recovery.focus(); await page.keyboard.press("Enter")
    const history = await popupPromise
    await expect(history).toHaveURL(new RegExp(`${href}$`))
    await expect(assistant(history).last()).toContainText("STREAMING · Lịch sử")
    await expect(history.getByRole("link", { name: "Tải lại lịch sử", exact: true })).toBeVisible()
    await expect(history.getByRole("button", { name: "Dừng tạo câu trả lời" })).toHaveCount(0)
    await expect(history.getByRole("region", { name: "Lịch sử trò chuyện", exact: true })).toHaveAttribute("aria-busy", "false")
    expect(streamPosts(qa)).toHaveLength(1)
    const conflict = history.waitForResponse(r => r.request().method() === "POST" && r.url().endsWith("/chat/stream"))
    await question(history).fill("intentional remote conflict")
    await history.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click()
    expect((await conflict).status()).toBe(409)
    await expect(question(history)).toHaveAttribute("aria-readonly", "false")
    await expect(assistant(history).last().getByRole("alert")).toBeVisible()
    await expect(assistant(history).first()).toContainText("STREAMING · Lịch sử")
    await expect(page).toHaveURL(new RegExp(`${href}$`), { timeout: 20_000 })
    await expect(assistant(page).last()).toContainText("Hoàn tất")
    await history.getByRole("link", { name: "Tải lại lịch sử", exact: true }).click()
    await expect(assistant(history)).toHaveCount(1)
    await expect(assistant(history).last()).toContainText("Hoàn tất")
    expect(qa.requests.filter(r => r.method === "POST" && r.path.endsWith("/sessions"))).toHaveLength(1)
    expect(streamPosts(qa).map(r => JSON.parse(r.body!).session_id)).toEqual([id, id])
    await history.close()
  })

  test("refreshing /chat during a deferred turn does not replay or pretend to restore; sidebar opens persisted partial history", async ({ page, qa }) => {
    await page.goto("/chat")
    await question(page).fill("refresh deferred fixture")
    await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click()
    const recovery = page.getByRole("link", { name: recoveryName, exact: true })
    await expect(assistant(page).last()).toContainText("Mock Markdown")
    const href = (await recovery.getAttribute("href"))!
    await page.reload()
    await expect(page).toHaveURL(/\/chat$/)
    await expect(page.getByRole("heading", { name: "Xin chào! Tôi là trợ lý tri thức nội bộ. Bạn muốn tìm hiểu điều gì hôm nay?" })).toBeVisible()
    await expect(page.getByRole("link", { name: recoveryName, exact: true })).toHaveCount(0)
    await page.locator(`a[href='${href}']`).filter({ hasText: "QA new chat" }).click()
    await expect(assistant(page).last()).toContainText("Chưa hoàn tất")
    await expect(assistant(page).last()).toContainText("Mock Markdown")
    await expect(question(page)).toHaveAttribute("aria-readonly", "false")
    expect(streamPosts(qa)).toHaveLength(1)
    expect(qa.requests.filter(r => r.method === "POST" && r.path.endsWith("/sessions"))).toHaveLength(1)
  })
})

for (const failure of ["http503", "delayed-terminal"] as const) {
  test(`history verification ${failure} retains text/recovery; later deliberate turn reuses session and canonicalizes`, async ({ page, qa }) => {
    if (failure === "http503") {
      let verificationReads = 0
      await page.route("**/lifecycle/sessions/*/messages?*", async route => {
        if (++verificationReads !== 1) { await route.fallback(); return }
        await route.fulfill({ status: 503, headers: { "Access-Control-Allow-Origin": "http://127.0.0.1:3100" }, json: { detail: "synthetic read unavailable" } })
      })
    } else qa.lagHistoryReads = 1
    await page.goto("/chat")
    await question(page).fill("first verification fixture")
    await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click()
    await expect(question(page)).toHaveAttribute("aria-readonly", "false")
    await expect(page.getByText(/Chưa xác minh được lịch sử đã lưu/)).toBeVisible()
    await expect(assistant(page).last()).toContainText("Hoàn tất")
    await expect(assistant(page).last()).toContainText("Mock Markdown")
    await expect(page).toHaveURL(/\/chat$/)
    const href = await page.getByRole("link", { name: recoveryName, exact: true }).getAttribute("href")
    await question(page).fill("second deliberate verification fixture")
    await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`${href}$`))
    await expect(assistant(page)).toHaveCount(2)
    expect(streamPosts(qa)).toHaveLength(2)
    expect(new Set(streamPosts(qa).map(r => JSON.parse(r.body!).session_id)).size).toBe(1)
    expect(qa.requests.filter(r => r.method === "POST" && r.path.endsWith("/sessions"))).toHaveLength(1)
  })
}

for (const status of ["PENDING", "STREAMING", "FAILED", "PARTIAL"]) {
  test(`restored ${status} remains a backend snapshot with explicit reload and no auto generation`, async ({ page, qa }) => {
    const initialHistory = page.waitForResponse(r => r.url().includes(`/sessions/${b}/messages`) && r.request().method() === "GET")
    await page.goto(`/chat/${b}`)
    const snapshot = await (await initialHistory).json()
    await expect(question(page)).toBeVisible()
    const last = snapshot.items.at(-1)
    const altered = { ...snapshot, total: 1, items: [{ ...last, content: "", status,
      completed_at: ["PENDING", "STREAMING"].includes(status) ? null : last.completed_at }] }
    let reads = 0
    await page.route(`**/lifecycle/sessions/${b}/messages?*`, async route => {
      reads++
      await route.fulfill({ headers: { "Access-Control-Allow-Origin": "http://127.0.0.1:3100" }, json: altered })
    })
    await page.reload()
    await expect(assistant(page)).toHaveCount(1)
    await expect(question(page)).toHaveAttribute("aria-readonly", "false")
    await expect(page.getByRole("button", { name: "Dừng tạo câu trả lời" })).toHaveCount(0)
    await expect(page.getByRole("region", { name: "Lịch sử trò chuyện", exact: true })).toHaveAttribute("aria-busy", "false")
    await expect(assistant(page).locator(".animate-spin")).toHaveCount(0)
    if (["PENDING", "STREAMING"].includes(status)) {
      await expect(assistant(page)).toContainText(`${status} · Lịch sử`)
      await expect(assistant(page)).toContainText(`Trạng thái backend: ${status}`)
      await page.getByRole("link", { name: "Tải lại lịch sử", exact: true }).click()
      await expect(assistant(page)).toContainText(`${status} · Lịch sử`)
      expect(reads).toBe(2)
    } else {
      await expect(assistant(page)).toContainText(status === "FAILED" ? "Thất bại" : "Chưa hoàn tất")
      await expect(assistant(page)).toContainText("Không có nội dung trả lời.")
      expect(reads).toBe(1)
    }
    expect(streamPosts(qa)).toHaveLength(0)
  })
}

test("completed reply retains exact clipboard text, message-local citation drawer and history ordinal fallback on mobile", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto(`/chat/${b}`)
  await expect(question(page)).toBeVisible()
  const persisted = page.waitForResponse(r => r.url().includes(`/sessions/${b}/messages`) && r.request().method() === "GET")
  await question(page).fill("copy citation fixture")
  await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click()
  const history = await (await persisted).json()
  await expect(question(page)).toHaveAttribute("aria-readonly", "false")
  const reply = assistant(page).last()
  const marker = reply.getByRole("button", { name: /^Xem nguồn \[1\]:/ }).first()
  const originalMarker = await marker.elementHandle()
  await marker.focus(); await page.keyboard.press("Enter")
  const drawer = page.getByRole("dialog", { name: "Nguồn của câu trả lời", exact: true })
  const close = drawer.getByRole("button", { name: "Đóng", exact: true })
  await expect(close).toBeFocused()
  expect(await originalMarker!.evaluate(node => node.isConnected), "Opening a citation must retain the opener DOM node for focus restoration").toBe(true)
  await expect(drawer).toContainText("Trang 1")
  await expect(drawer.locator("[data-selected='true']")).toContainText("Nguồn [1]")
  const bounds = await drawer.boundingBox()
  expect(bounds!.width).toBeLessThanOrEqual(375)
  await page.keyboard.press("Escape")
  await expect(drawer).toHaveCount(0)
  await expect(marker).toBeFocused()
  await page.evaluate(() => {
    const clipboard = navigator.clipboard, write = clipboard.writeText.bind(clipboard)
    clipboard.writeText = text => { Object.assign(window, { qaClipboardText: text }); return write(text) }
  })
  await reply.getByRole("button", { name: "Sao chép câu trả lời", exact: true }).click()
  await expect(reply.getByText("Đã sao chép", { exact: true })).toBeVisible()
  expect(await page.evaluate(() => (window as unknown as { qaClipboardText: string }).qaClipboardText)).toBe(history.items.at(-1).content)
  // Chromium's native Windows clipboard exposes CRLF; only its OS roundtrip is normalized.
  expect((await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, "\n")).toBe(history.items.at(-1).content)
  await reply.getByRole("button", { name: "Sao chép code", exact: true }).click()
  const code = "  const citation = '[1]';\n\tconst longLine = '" + "code".repeat(100) + "';\n"
  expect(await page.evaluate(() => (window as unknown as { qaClipboardText: string }).qaClipboardText)).toBe(code)
  expect((await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, "\n")).toBe(code)
  await context.clearPermissions()
  await context.grantPermissions([], { origin: "http://127.0.0.1:3100" })
  await reply.getByRole("button", { name: "Sao chép câu trả lời", exact: true }).click()
  await expect(reply.getByText("Không thể sao chép. Hãy chọn nội dung và sao chép thủ công.", { exact: true })).toBeVisible()
  await page.reload()
  const restored = assistant(page).last()
  await expect(restored).toContainText("Chưa có thông tin để nối số trích dẫn")
  await expect(restored.getByRole("button", { name: /^Xem nguồn/ })).toHaveCount(0)
  await restored.getByRole("button", { name: "Nguồn của câu trả lời (1)", exact: true }).click()
  await expect(page.getByRole("dialog", { name: "Nguồn của câu trả lời", exact: true })).toContainText("Trích dẫn đã lưu")
})

test.describe("route cleanup while generation is active", () => {
test.use({ streamDelayMs: 200 })
test("switching routes during a stream cleans up without contaminating the next session or replaying", async ({ page, qa }) => {
  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window), abortedSessions: string[] = []
    Object.assign(window, { qaAbortedSessions: abortedSessions })
    window.fetch = (input, init) => {
      const url = input instanceof Request ? input.url : String(input)
      if (url.endsWith("/chat/stream") && typeof init?.body === "string") {
        const id = JSON.parse(init.body).session_id
        init.signal?.addEventListener("abort", () => abortedSessions.push(id), { once: true })
      }
      return nativeFetch(input, init)
    }
  })
  await page.goto(`/chat/${a}`)
  await expect(question(page)).toBeVisible()
  await question(page).fill("session A switch fixture")
  await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click()
  await expect(assistant(page).last()).toContainText("Mock Markdown")
  await expect(page.getByRole("button", { name: "Dừng tạo câu trả lời" })).toBeVisible()
  await page.locator(`a[href='/chat/${b}']`).click()
  await expect(page).toHaveURL(new RegExp(`/chat/${b}$`))
  await expect.poll(() => page.evaluate(() => (window as unknown as { qaAbortedSessions: string[] }).qaAbortedSessions)).toContain(a)
  await expect(assistant(page)).toHaveCount(1)
  await expect(page.getByText("session A switch fixture", { exact: true }).filter({ visible: true })).toHaveCount(0)
  await expect(question(page)).toHaveAttribute("aria-readonly", "false")
  await expect(page.getByRole("button", { name: "Dừng tạo câu trả lời" })).toHaveCount(0)
  await question(page).fill("session B next fixture")
  await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click()
  await expect(question(page)).toHaveAttribute("aria-readonly", "false")
  await expect(assistant(page)).toHaveCount(2)
  await expect(page.getByText("session A switch fixture", { exact: true }).filter({ visible: true })).toHaveCount(0)
  expect(streamPosts(qa).map(r => JSON.parse(r.body!).session_id)).toEqual([a, b])
  expect(qa.requests.filter(r => r.method === "POST" && r.path.endsWith("/sessions"))).toHaveLength(0)
  await page.getByRole("link", { name: "QA session A — long history", exact: true }).click()
  await expect(question(page)).toHaveAttribute("aria-readonly", "false")
  await page.reload()
  await expect(assistant(page).last()).toContainText("Mock Markdown")
  await expect(question(page)).toHaveAttribute("aria-readonly", "false")
  await expect(page.getByText("session B next fixture", { exact: true }).filter({ visible: true })).toHaveCount(0)
  expect(streamPosts(qa)).toHaveLength(2)
})
})
