import type { Page } from "@playwright/test"
import { test, expect } from "./fixtures.mjs"

const session = "bbbbbbbb-1111-4111-8111-111111111111"
const cors = { "Access-Control-Allow-Origin": "http://127.0.0.1:3100" }
const question = (page: Page) => page.getByRole("textbox", { name: "Câu hỏi", exact: true })

for (const status of [422, 404, 409, 429, 503, "network"] as const) {
  test(`pre-header chat ${status} is safe, unlocks composer and never auto-replays`, async ({ page }) => {
    await page.goto(`/chat/${session}`)
    await expect(question(page)).toBeVisible()
    let attempts = 0
    await page.route("**/lifecycle/chat/stream", async route => {
      attempts++
      if (status === "network") await route.abort("failed")
      else await route.fulfill({ status, headers: cors, json: { detail: "UNSAFE_INTERNAL_FIXTURE", input: "UNSAFE_INTERNAL_FIXTURE" } })
    })
    await question(page).fill(`safe failure fixture ${status}`)
    await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click()
    await expect(question(page)).toHaveAttribute("aria-readonly", "false")
    const reply = page.getByRole("article", { name: "Câu trả lời của trợ lý", exact: true }).last()
    await expect(reply).toContainText("Thất bại")
    await expect(reply.getByRole("alert")).toBeVisible()
    await expect(page.getByText("UNSAFE_INTERNAL_FIXTURE", { exact: false })).toHaveCount(0)
    await expect(page.getByRole("button", { name: "Dừng tạo câu trả lời" })).toHaveCount(0)
    await expect(page.getByRole("link", { name: "Tải lại phiên để kiểm tra lịch sử trước khi gửi lại", exact: true })).toBeVisible()
    expect(attempts).toBe(1)
    if (status === 503) {
      await page.unroute("**/lifecycle/chat/stream")
      await question(page).fill("deliberate new question after service recovery")
      await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click()
      await expect(question(page)).toHaveAttribute("aria-readonly", "false")
      await expect(page.getByRole("article", { name: "Câu trả lời của trợ lý", exact: true }).last()).toContainText("Hoàn tất")
    }
  })
}

for (const status of [404, 410]) {
  test(`session lookup${status} reports unavailable session and keyboard return without generation`, async ({ page, qa }) => {
    await page.route(`**/lifecycle/sessions/${session}`, route => route.fulfill({ status, headers: cors, json: { detail: "UNSAFE_INTERNAL_FIXTURE" } }))
    await page.goto(`/chat/${session}`)
    await expect(page.getByRole("heading", { name: "Không tìm thấy phiên trò chuyện", exact: true })).toBeVisible()
    await expect(question(page)).toHaveCount(0)
    await page.getByRole("link", { name: "Về trang Chat", exact: true }).press("Enter")
    await expect(page).toHaveURL(/\/chat$/)
    expect(qa.requests.filter(r => r.method === "POST")).toHaveLength(0)
  })
}

test("invalid session route is clear and never submits a fabricated UUID", async ({ page, qa }) => {
  await page.goto("/chat/not-a-uuid")
  await expect(page.getByRole("heading", { name: "Session ID không hợp lệ", exact: true })).toBeVisible()
  expect(qa.requests.some(r => r.path.includes("not-a-uuid"))).toBe(false)
  await expect(question(page)).toHaveCount(0)
})

test("health checks are explicit, preserve readiness503, sanitize messages and do not probe Groq", async ({ page, qa }) => {
  let checks = 0, degraded = true
  await page.route("**/lifecycle/health", async route => {
    checks++
    await route.fulfill({ headers: cors, json: { status: "ok", llm_model: "qa/mock" } })
  })
  await page.route("**/lifecycle/health/dependencies", async route => {
    checks++
    await route.fulfill({ status: degraded ? 503 : 200, headers: cors, json: {
      status: degraded ? "degraded" : "ok", dependencies: {
        mongodb: { service: "mongodb", ok: !degraded, code: degraded ? "timeout" : "connected", message: "UNSAFE_INTERNAL_FIXTURE" },
        qdrant: { service: "qdrant", ok: true, code: "connected", message: "UNSAFE_INTERNAL_FIXTURE" },
      },
    } })
  })
  await page.goto("/chat")
  await page.getByText("Trạng thái dịch vụ", { exact: true }).press("Enter")
  await expect(page.getByText("Chưa kiểm tra kết nối dịch vụ.", { exact: true })).toBeVisible()
  expect(checks).toBe(0)
  await page.getByRole("button", { name: "Kiểm tra dịch vụ", exact: true }).click()
  await expect(page.getByText("Kết nối phụ thuộc chưa sẵn sàng (HTTP 503).", { exact: true })).toBeVisible()
  await expect(page.getByText("MongoDB: Hết thời gian chờ", { exact: true })).toBeVisible()
  await expect(page.getByText("UNSAFE_INTERNAL_FIXTURE", { exact: false })).toHaveCount(0)
  await expect(page.getByText(/Groq: chưa được kiểm tra bởi health này/)).toBeVisible()
  expect(checks).toBe(2)
  degraded = false
  await page.getByRole("button", { name: "Kiểm tra dịch vụ", exact: true }).click()
  await expect(page.getByText("MongoDB và Qdrant sẵn sàng.", { exact: true })).toBeVisible()
  expect(checks).toBe(4)
  expect(qa.requests.some(r => /groq|gemini/i.test(r.path))).toBe(false)
})

test("documents empty state has deliberate refresh, no stuck loading or hidden polling", async ({ page, qa }) => {
  qa.profile = "/empty"
  await page.goto("/documents")
  await expect(page.getByText("Chưa có tài liệu trong danh sách này.", { exact: true })).toBeVisible()
  expect(qa.requests.filter(r => r.path.endsWith("/documents"))).toHaveLength(1)
  qa.profile = "/lifecycle"
  await page.getByRole("button", { name: "Làm mới", exact: true }).click()
  await expect(page.getByRole("list", { name: "Danh sách tài liệu", exact: true }).getByRole("listitem")).toHaveCount(3)
  expect(qa.requests.filter(r => r.path.endsWith("/documents"))).toHaveLength(2)
})

test("documents offset pagination reaches21 items and explicit refresh resets to the first20", async ({ page }) => {
  const snapshotResponse = page.waitForResponse(r => r.url().includes("/lifecycle/documents?") && r.request().method() === "GET")
  await page.goto("/documents")
  const snapshot = await (await snapshotResponse).json()
  const items = Array.from({ length: 21 }, (_, index) => ({ ...snapshot[0],
    document_id: `90000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
    file_name: `qa-pagination-${index + 1}.txt`,
  }))
  const offsets: number[] = []
  await page.route("**/lifecycle/documents?*", async route => {
    const url = new URL(route.request().url()), offset = Number(url.searchParams.get("offset")), limit = Number(url.searchParams.get("limit"))
    offsets.push(offset)
    expect(limit).toBe(20)
    await route.fulfill({ headers: cors, json: items.slice(offset, offset + limit) })
  })
  await page.reload()
  const list = page.getByRole("list", { name: "Danh sách tài liệu", exact: true })
  await expect(list.getByRole("listitem")).toHaveCount(20)
  await page.getByRole("button", { name: "Tải thêm tài liệu", exact: true }).click()
  await expect(list.getByRole("listitem")).toHaveCount(21)
  await expect(page.getByRole("button", { name: "Tải thêm tài liệu", exact: true })).toHaveCount(0)
  await page.getByRole("button", { name: "Làm mới", exact: true }).click()
  await expect(list.getByRole("listitem")).toHaveCount(20)
  expect(offsets).toEqual([0, 20, 0])
})

test.describe("reader intent and responsive browser checks", () => {
  test.use({ streamDelayMs: 200 })
  test("stream scroll respects reading older text; keyboard jump resumes and mobile document stays within viewport", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" })
    await page.goto("/chat")
    await page.keyboard.press("Tab")
    await expect(page.getByRole("link", { name: "Chuyển đến nội dung chính", exact: true })).toBeFocused()
    await page.keyboard.press("Enter")
    await expect(page.locator("#main-content")).toBeFocused()
    await question(page).fill("reader intent fixture")
    await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click()
    const transcript = page.getByRole("region", { name: "Lịch sử trò chuyện", exact: true })
    await expect(transcript).toContainText("Đoạn 4:")
    await transcript.hover(); await page.mouse.wheel(0, -10000)
    await expect.poll(() => transcript.evaluate(node => node.scrollTop)).toBeLessThan(50)
    const before = await transcript.evaluate(node => node.scrollTop)
    await expect(transcript).toContainText("Đoạn 8:")
    expect(Math.abs(await transcript.evaluate(node => node.scrollTop) - before)).toBeLessThan(5)
    const jump = page.getByRole("button", { name: "Nội dung mới — Về cuối", exact: true })
    await jump.focus(); await page.keyboard.press("Enter")
    await expect.poll(() => transcript.evaluate(node => node.scrollHeight - node.clientHeight - node.scrollTop)).toBeLessThanOrEqual(48)
    await page.getByRole("button", { name: "Dừng tạo câu trả lời", exact: true }).press("Enter")
    await expect(question(page)).toHaveAttribute("aria-readonly", "false")
    await page.setViewportSize({ width: 320, height: 568 })
    await page.goto("/documents")
    await page.getByRole("button", { name: /so-tay-nhan-vien\.pdf/ }).click()
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1)
    expect(await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches)).toBe(true)
  })
})
