import { test, expect } from "./fixtures.mjs"

test("HR portal routes (/hr, /hr/documents, /hr/guide), multi-turn chatbot persistence, and workspace isolation", async ({ page, qa }) => {
  // 1. /hr Overview page: scoped .hr-theme + Live Knowledge Base strip from mock API
  await page.goto("/hr")
  await expect(page.locator(".hr-theme").first()).toBeVisible()
  await expect(page.getByRole("heading", { name: "Kho tri thức RAG (Dữ liệu thực từ API)" })).toBeVisible()
  await expect(page.getByText("Tổng tài liệu")).toBeVisible()

  // 2. Open HrChatbotWidget and send Turn 1 (creates an isolated surface='hr' session)
  await page.getByRole("button", { name: "Mở Trợ lý HR", exact: true }).click()
  const sheet = page.getByRole("dialog")
  await expect(sheet).toBeVisible()
  await expect(sheet.getByText("Trợ lý chính sách HR")).toBeVisible()

  await sheet.getByRole("textbox", { name: "Câu hỏi", exact: true }).fill("HR E2E turn 1")
  await sheet.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click()
  await expect(sheet.getByRole("textbox", { name: "Câu hỏi", exact: true })).toHaveAttribute("aria-readonly", "false")
  await expect(sheet.getByRole("article", { name: "Câu trả lời của trợ lý", exact: true })).toHaveCount(1)

  const hrSessionPosts = qa.requests.filter(
    r => r.method === "POST" && r.path.endsWith("/sessions") && JSON.parse(r.body || "{}").surface === "hr",
  )
  expect(hrSessionPosts).toHaveLength(1)

  // Close widget drawer before navigating across HR routes
  await page.keyboard.press("Escape")
  await expect(sheet).toHaveCount(0)

  // 3. Navigate to /hr/documents via HR Portal sidebar Link (preserves HrChatbotProvider across /hr/*)
  const hrNav = page.getByRole("navigation", { name: "Điều hướng HR Portal" })
  await hrNav.locator('a[href="/hr/documents"]').click()
  await expect(page).toHaveURL(/\/hr\/documents$/)
  await expect(page.locator(".hr-theme").first()).toBeVisible()
  await expect(page.getByRole("heading", { name: "HR Documents", exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: /so-tay-nhan-vien\.pdf/ })).toBeVisible()

  // Filter by "Quy trình" category tab -> quy-trinh-ho-tro.md matches
  await page.getByRole("tab", { name: /^Quy trình/ }).click()
  await expect(page.getByRole("button", { name: /quy-trinh-ho-tro\.md/ })).toBeVisible()
  await expect(page.getByRole("button", { name: /so-tay-nhan-vien\.pdf/ })).toHaveCount(0)

  // Reset to "Tất cả" tab, search and open document preview
  await page.getByRole("tab", { name: /^Tất cả/ }).click()
  await page.getByRole("textbox", { name: "Tìm tên tài liệu HR", exact: true }).fill("so-tay")
  await page.getByRole("button", { name: /so-tay-nhan-vien\.pdf/ }).click()
  await expect(page.getByRole("heading", { name: "so-tay-nhan-vien.pdf", exact: true })).toBeVisible()
  await expect(page.getByText("Nội dung xem trước (Phiên bản đang hoạt động)")).toBeVisible()
  expect(qa.requests.some(r => r.method === "GET" && r.path.includes("/preview"))).toBe(true)

  // 4. Navigate to /hr/guide via HR Portal sidebar Link: verify guide renders & HrChatbotWidget preserves Turn 1
  await hrNav.locator('a[href="/hr/guide"]').click()
  await expect(page).toHaveURL(/\/hr\/guide$/)
  await expect(page.locator(".hr-theme").first()).toBeVisible()
  await expect(page.getByRole("heading", { name: "Hướng dẫn sử dụng HR Portal", exact: true })).toBeVisible()

  await page.getByRole("button", { name: "Mở Trợ lý HR", exact: true }).first().click()
  const reopenedSheet = page.getByRole("dialog")
  await expect(reopenedSheet).toBeVisible()
  await expect(reopenedSheet.getByText("HR E2E turn 1", { exact: true })).toBeVisible()

  // Send Turn 2 inside the same persisted HR session
  await reopenedSheet.getByRole("textbox", { name: "Câu hỏi", exact: true }).fill("HR E2E turn 2")
  await reopenedSheet.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click()
  await expect(reopenedSheet.getByRole("textbox", { name: "Câu hỏi", exact: true })).toHaveAttribute("aria-readonly", "false")
  await expect(reopenedSheet.getByRole("article", { name: "Câu trả lời của trợ lý", exact: true })).toHaveCount(2)

  // Verify both HR stream calls reused the exact same session_id
  const streams = qa.requests.filter(r => r.method === "POST" && r.path.endsWith("/chat/stream"))
  expect(streams).toHaveLength(2)
  expect(new Set(streams.map(r => JSON.parse(r.body!).session_id)).size).toBe(1)

  // 5. Navigate to main workspace /chat: verify HR theme isolation and separate workspace session list
  await page.goto("/chat")
  await expect(page.locator(".hr-theme")).toHaveCount(0)
  await expect(page.getByRole("button", { name: "Cuộc trò chuyện mới" })).toBeVisible()
  await expect(page.getByText("HR E2E turn 1", { exact: true })).toHaveCount(0)
})
