import { test, expect } from "./fixtures.mjs"
import type { Page } from "@playwright/test"

// Next.js can retain an inactive route's DOM. Select the active composer's input.
const filePicker = (page: Page) => page.locator('form:visible input[type="file"][aria-label="Chọn tệp đính kèm"]')

const file = (name = "attachment.txt") => ({ name, mimeType: "text/plain", buffer: Buffer.from("Attachment fixture") })
const receipt = (overrides = {}) => ({ document_id: "11111111-1111-4111-8111-111111111111", version_id: "22222222-2222-4222-8222-222222222222",
  job_id: "33333333-3333-4333-8333-333333333333", file_name: "attachment.txt", num_chunks: 1, status: "INDEXED", activated: true, ...overrides })

async function mockUpload(page: Page) {
  await page.route("**/lifecycle/documents/upload", route => route.fulfill({ status: 201, json: receipt() }))
}

for (const width of [375, 1280]) {
  test(`${width}px picker keyboard, deduplication, indexed receipt and removal preserve draft without DELETE`, async ({ page, qa }) => {
    await page.setViewportSize({ width, height: 800 })
    let uploads = 0
    const mutations: string[] = []
    page.on("request", request => { if (request.method() === "DELETE") mutations.push(request.url()) })
    await page.route("**/lifecycle/documents/upload", async route => {
      uploads++
      expect(route.request().method()).toBe("POST")
      expect(route.request().headers()["content-type"]).toContain("multipart/form-data; boundary=")
      expect(route.request().postData()).toContain('name="file"')
      await route.fulfill({ status: 201, json: receipt() })
    })
    await page.goto("/chat")
    const question = page.getByRole("textbox", { name: "Câu hỏi", exact: true })
    await question.fill("Draft survives attachment edits")
    const chooser = page.waitForEvent("filechooser")
    await page.getByRole("button", { name: "Thêm tệp đính kèm" }).focus()
    await page.keyboard.press("Enter")
    await (await chooser).setFiles(file())
    const chips = page.getByRole("list", { name: "Tệp đính kèm" })
    await expect(chips.getByRole("listitem")).toHaveCount(1)
    await expect(chips).toContainText("Ready")
    await expect(page.getByRole("button", { name: "Tải lên", exact: true })).toHaveCount(0)
    // Dispatch identical File metadata twice, then re-select to check deduplication across selections.
    await filePicker(page).evaluate((input: HTMLInputElement) => {
      const data = new DataTransfer()
      const same = new File(["other"], "duplicate.md", { lastModified: 1 })
      data.items.add(same); data.items.add(same)
      input.files = data.files; input.dispatchEvent(new Event("change", { bubbles: true }))
    })
    await expect(chips.getByRole("listitem")).toHaveCount(2)
    await expect.poll(() => uploads).toBe(2)
    await filePicker(page).evaluate((input: HTMLInputElement) => {
      const data = new DataTransfer()
      data.items.add(new File(["other"], "duplicate.md", { lastModified: 1 }))
      input.files = data.files; input.dispatchEvent(new Event("change", { bubbles: true }))
    })
    await expect(chips.getByRole("listitem")).toHaveCount(2)
    await page.getByRole("button", { name: "Gỡ duplicate.md", exact: true }).click()
    await expect(chips).toContainText("Ready")
    await expect(chips.getByRole("listitem")).toHaveAttribute("data-document-id", receipt().document_id)
    await expect(question).toHaveValue("Draft survives attachment edits")
    expect(uploads).toBe(2)
    const bounds = await chips.boundingBox()
    expect(bounds!.x).toBeGreaterThanOrEqual(0)
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width)
    await page.getByRole("button", { name: "Gỡ attachment.txt", exact: true }).press("Enter")
    await expect(chips).toHaveCount(0)
    await expect(question).toHaveValue("Draft survives attachment edits")
    expect(mutations).toEqual([])
    expect(qa.requests.filter(r => r.method === "DELETE")).toEqual([])
  })
}

test("failed upload retries explicitly; invalid files never call upload", async ({ page }) => {
  let attempts = 0
  await page.route("**/lifecycle/documents/upload", async route => {
    attempts++
    await route.fulfill(attempts === 1 ? { status: 503, json: { detail: "private error" } } : { status: 201, json: receipt() })
  })
  await page.goto("/chat")
  const picker = filePicker(page)
  await picker.setInputFiles([file("invalid.exe"), { ...file("empty.txt"), buffer: Buffer.alloc(0) }])
  const chips = page.getByRole("list", { name: "Tệp đính kèm" })
  await expect(chips.getByRole("status").filter({ hasText: "Failed" })).toHaveCount(2)
  await expect(chips.getByRole("button", { name: "Thử lại" }).first()).toBeDisabled()
  expect(attempts).toBe(0)
  await picker.setInputFiles(file())
  const chip = chips.getByRole("listitem").filter({ hasText: "attachment.txt" })
  await expect(chip).toContainText("Failed")
  await expect(chip).not.toContainText("private error")
  expect(attempts).toBe(1)
  await chip.getByRole("button", { name: "Thử lại", exact: true }).click()
  await expect(chip).toContainText("Ready")
  expect(attempts).toBe(2)
})

for (const result of [{ status: "PROCESSING", activated: false }, { status: "FAILED", activated: false }, { status: "INDEXED", activated: false }, { status: undefined, activated: true }]) {
  test(`receipt ${JSON.stringify(result)} never claims Ready`, async ({ page }) => {
    await page.route("**/lifecycle/documents/upload", route => route.fulfill({ status: 201, json: receipt(result) }))
    await page.goto("/chat")
    await filePicker(page).setInputFiles(file())
    const chips = page.getByRole("list", { name: "Tệp đính kèm" })
    await expect(chips).toContainText("Failed")
    await expect(chips).not.toContainText("Ready")
    await expect(chips.getByRole("listitem")).toHaveAttribute("data-document-id", receipt().document_id)
  })
}

test.describe("Stop during an active stream", () => {
  test.use({ streamDelayMs: 200 })
  test("removing an uploading chip ignores late completion; Send/Stop and SSE payload remain intact", async ({ page, qa }) => {
    let release!: () => void, uploads = 0
    const gate = new Promise<void>(resolve => { release = resolve })
    const deletes: string[] = []
    page.on("request", request => { if (request.method() === "DELETE") deletes.push(request.url()) })
    await page.route("**/lifecycle/documents/upload", async route => {
      uploads++
      await gate
      await route.fulfill({ status: 201, json: receipt() }).catch(() => {})
    })
    try {
      await page.goto("/chat")
      const question = page.getByRole("textbox", { name: "Câu hỏi", exact: true })
      await question.fill("Keep streaming behavior")
      await filePicker(page).setInputFiles(file())
      const chips = page.getByRole("list", { name: "Tệp đính kèm" })
      await expect(chips).toContainText("Uploading")
      await expect.poll(() => uploads).toBe(1)
      await expect(chips.getByRole("button", { name: "Tải lên", exact: true })).toHaveCount(0)
      await page.getByRole("button", { name: "Gỡ attachment.txt", exact: true }).click()
      release()
      await expect(chips).toHaveCount(0)
      await expect(question).toHaveValue("Keep streaming behavior")
      await filePicker(page).setInputFiles(file())
      await expect(chips).toContainText("Ready")
      await question.press("Enter")
      await expect(page.getByText("Mock Markdown", { exact: true })).toBeVisible()
      await page.getByRole("button", { name: "Dừng tạo câu trả lời", exact: true }).click()
      await expect(question).toHaveAttribute("aria-readonly", "false")
      await expect(page.getByText("Bạn đã dừng tạo câu trả lời.", { exact: true })).toBeVisible()
      await expect(chips).toContainText("Ready")
      await page.getByRole("button", { name: "Gỡ attachment.txt", exact: true }).click()
      await expect(chips).toHaveCount(0)
      const streams = qa.requests.filter(r => r.method === "POST" && r.path.endsWith("/chat/stream"))
      expect(streams).toHaveLength(1)
      expect(Object.keys(JSON.parse(streams[0].body!)).sort()).toEqual(["question", "session_id"])
      expect(deletes).toEqual([])
    } finally { release() }
  })
})

for (const width of [375, 1280]) {
  test(`${width}px phuongtien.txt auto-upload and exact safe preview; close/Escape preserve attachment`, async ({ page, qa }) => {
    await mockUpload(page)
    await page.setViewportSize({ width, height: 800 })
    await page.goto("/chat")
    const text = "Phương tiện\r\n  Xe máy\n<script>window.__previewInjected = true</script>\n"
    await filePicker(page).setInputFiles({ ...file("phuongtien.txt"), buffer: Buffer.from(text) })
    const chips = page.getByRole("list", { name: "Tệp đính kèm" })
    await expect(chips).toContainText("Ready")
    await expect(page.getByRole("button", { name: "Tải lên", exact: true })).toHaveCount(0)
    const trigger = page.getByRole("button", { name: "Xem trước phuongtien.txt", exact: true })
    await trigger.press("Enter")
    const panel = page.getByRole("dialog", { name: "phuongtien.txt", exact: true })
    await expect(panel).toBeVisible()
    await expect(panel.getByRole("button", { name: "Đóng xem trước" })).toBeFocused()
    const content = panel.getByLabel("Nội dung tài liệu")
    await expect(content).toBeVisible()
    expect(await content.textContent()).toBe(text)
    expect(await page.evaluate(() => (window as unknown as Record<string, unknown>).__previewInjected)).toBeUndefined()
    // Visibility precedes the end of the Sheet's slide-in animation.
    await expect.poll(async () => (await panel.boundingBox())!.x).toBeGreaterThanOrEqual(0)
    await expect.poll(async () => {
      const bounds = (await panel.boundingBox())!
      return bounds.x + bounds.width
    }).toBeLessThanOrEqual(width)
    await panel.getByRole("button", { name: "Đóng xem trước" }).click()
    await expect(panel).toHaveCount(0)
    await expect(chips).toContainText("Ready")
    await expect(trigger).toBeFocused()
    await trigger.click()
    await page.keyboard.press("Escape")
    await expect(panel).toHaveCount(0)
    await expect(trigger).toBeFocused()
    await page.getByRole("button", { name: "Gỡ phuongtien.txt", exact: true }).click()
    await expect(chips).toHaveCount(0)
    expect(qa.requests.filter(request => request.method === "DELETE")).toEqual([])
  })
}

test("preview limits large TXT, reports encoding/read failures and explicitly declines PDF", async ({ page }) => {
  await mockUpload(page)
  await page.goto("/chat")
  await filePicker(page).setInputFiles({ ...file("large.txt"), buffer: Buffer.alloc(300_000, 97) })
  await page.getByRole("button", { name: "Xem trước large.txt" }).click()
  let panel = page.getByRole("dialog", { name: "large.txt", exact: true })
  await expect(panel).toContainText("256 KiB")
  expect((await panel.getByLabel("Nội dung tài liệu").textContent())!.length).toBe(256 * 1024)
  await page.keyboard.press("Escape")
  await filePicker(page).setInputFiles({ ...file("encoding.txt"), buffer: Buffer.from([0xff, 0xff]) })
  await page.getByRole("button", { name: "Xem trước encoding.txt" }).click()
  panel = page.getByRole("dialog", { name: "encoding.txt", exact: true })
  await expect(panel.getByRole("alert")).toContainText("encoding")
  await page.keyboard.press("Escape")
  await filePicker(page).setInputFiles(file("read-error.txt"))
  await page.evaluate(() => { Blob.prototype.arrayBuffer = async () => { throw new Error("private device path") } })
  await page.getByRole("button", { name: "Xem trước read-error.txt" }).click()
  panel = page.getByRole("dialog", { name: "read-error.txt", exact: true })
  await expect(panel.getByRole("alert")).toContainText("Không thể đọc file")
  await expect(panel).not.toContainText("private device path")
  await page.keyboard.press("Escape")
  await filePicker(page).setInputFiles(file("example.pdf"))
  await page.getByRole("button", { name: "Xem trước example.pdf" }).click()
  panel = page.getByRole("dialog", { name: "example.pdf", exact: true })
  await expect(panel).toContainText("Chưa hỗ trợ xem trước định dạng này")
  await expect(panel.getByLabel("Nội dung tài liệu")).toHaveCount(0)
})

test("completed chat resets sent draft, attachments and open preview; selecting the same file again works", async ({ page, qa }) => {
  await mockUpload(page)
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  await page.route("**/lifecycle/chat/stream", async route => { await gate; await route.fallback() })
  try {
    await page.goto("/chat")
    const question = page.getByRole("textbox", { name: "Câu hỏi", exact: true })
    await question.fill("Successful attachment turn")
    await filePicker(page).setInputFiles(file("phuongtien.txt"))
    const chips = page.getByRole("list", { name: "Tệp đính kèm" })
    await expect(chips).toContainText("Ready")
    await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click()
    await expect(question).toHaveValue("Successful attachment turn")
    await expect(chips).toContainText("Ready")
    await page.getByRole("button", { name: "Xem trước phuongtien.txt" }).click()
    await expect(page.getByRole("dialog", { name: "phuongtien.txt", exact: true })).toBeVisible()
    release()
    await expect(page.getByRole("dialog", { name: "phuongtien.txt", exact: true })).toHaveCount(0)
    await expect(page).toHaveURL(/\/chat\/[0-9a-f-]{36}$/)
    await expect(question).toHaveValue("")
    await expect(chips).toHaveCount(0)
    await expect(filePicker(page)).toHaveValue("")
    await expect(page.getByRole("article", { name: "Câu trả lời của trợ lý", exact: true })).toContainText("Hoàn tất")
    await filePicker(page).setInputFiles(file("phuongtien.txt"))
    await expect(chips).toContainText("Ready")
    expect(qa.requests.filter(request => request.method === "DELETE")).toEqual([])
  } finally { release() }
})

for (const replacement of ["new.txt", "phuongtien.txt"]) {
  test(`old completion preserves ${replacement} selected during the turn, including remove/readd identity`, async ({ page }) => {
    await mockUpload(page)
    let release!: () => void
    const gate = new Promise<void>(resolve => { release = resolve })
    await page.route("**/lifecycle/chat/stream", async route => { await gate; await route.fallback() })
    try {
      await page.goto("/chat")
      const question = page.getByRole("textbox", { name: "Câu hỏi", exact: true })
      await question.fill("Old request")
      await filePicker(page).setInputFiles(file("phuongtien.txt"))
      const chips = page.getByRole("list", { name: "Tệp đính kèm" })
      await expect(chips).toContainText("Ready")
      await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click()
      await page.getByRole("button", { name: "Gỡ phuongtien.txt", exact: true }).click()
      await filePicker(page).setInputFiles(file(replacement))
      await expect(chips).toContainText("Ready")
      await page.getByRole("button", { name: `Xem trước ${replacement}`, exact: true }).click()
      release()
      const panel = page.getByRole("dialog", { name: replacement, exact: true })
      await expect(page.getByRole("article", { name: "Câu trả lời của trợ lý", exact: true, includeHidden: true })).toContainText("Hoàn tất")
      await expect(page.locator("textarea")).toHaveValue("")
      await expect(panel).toBeVisible()
      await page.keyboard.press("Escape")
      await expect(chips.getByRole("listitem")).toHaveCount(1)
      await expect(chips).toContainText(replacement)
      await expect(page).toHaveURL(/\/chat$/)
    } finally { release() }
  })
}

test("chat error keeps the submitted question and ready attachments for deliberate retry", async ({ page }) => {
  await mockUpload(page)
  await page.route("**/lifecycle/chat/stream", route => route.fulfill({ status: 503, json: { detail: "private" } }))
  await page.goto("/chat")
  const question = page.getByRole("textbox", { name: "Câu hỏi", exact: true })
  await question.fill("Keep this draft for retry")
  await filePicker(page).setInputFiles(file("phuongtien.txt"))
  const chips = page.getByRole("list", { name: "Tệp đính kèm" })
  await expect(chips).toContainText("Ready")
  await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click()
  await expect(page.getByRole("article", { name: "Câu trả lời của trợ lý", exact: true })).toContainText("Thất bại")
  await expect(question).toHaveAttribute("aria-readonly", "false")
  await expect(question).toHaveValue("Keep this draft for retry")
  await expect(chips).toContainText("Ready")
  await expect(page).toHaveURL(/\/chat$/)
})
