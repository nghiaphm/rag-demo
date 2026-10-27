import { spawnSync } from "node:child_process"
import { fileURLToPath } from "node:url"
import { test, expect } from "./fixtures.mjs"
import type { Page } from "@playwright/test"

const picker = (page: Page) => page.locator('form:visible input[type="file"][aria-label="Chọn tệp đính kèm"]')
const question = (page: Page) => page.getByRole("textbox", { name: "Câu hỏi", exact: true })
const chips = (page: Page) => page.getByRole("list", { name: "Tệp đính kèm" })
const user = (page: Page) => page.getByRole("article", { name: "Tin nhắn của bạn", exact: true }).last()
const workbookPath = fileURLToPath(new URL("../.playwright-tmp/vehicles.xlsx", import.meta.url))

test.beforeAll(() => {
  const result = spawnSync(fileURLToPath(new URL("../../.venv/Scripts/python.exe", import.meta.url)), ["-c", String.raw`
import sys
from openpyxl import Workbook
w = Workbook()
s = w.active
s.title = 'Vehicles'
s.append(['Name','Speed'])
s.append(['Airplane',900])
s.append(['Bus',80])
s = w.create_sheet('Policies')
s.append(['Topic','Rule'])
s.append(['License','A valid license is required'])
w.save(sys.argv[1])
w.close()
`, workbookPath], { windowsHide: true, encoding: "utf8" })
  expect(result.status, result.stderr).toBe(0)
})

test("phuongtien.txt persists on its user message and previews after refresh/session switching", async ({ page, qa }) => {
  const text = "Phương tiện\r\nMáy bay: 900 km/h\n<script>window.__attachmentScript = true</script>"
  await page.goto("/chat")
  await picker(page).setInputFiles({ name: "phuongtien.txt", mimeType: "text/plain", buffer: Buffer.from(text) })
  await expect(chips(page)).toContainText("Ready")
  await question(page).fill("Explain these vehicles")
  await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click()
  await expect(page).toHaveURL(/\/chat\/[0-9a-f-]{36}$/)
  const sessionUrl = page.url()
  await expect(chips(page)).toHaveCount(0)
  let trigger = user(page).getByRole("button", { name: "Xem tệp đính kèm phuongtien.txt", exact: true })
  await trigger.click()
  const panel = page.getByRole("dialog", { name: "phuongtien.txt", exact: true })
  await expect(panel.getByLabel("Nội dung tài liệu")).toHaveText(text)
  expect(await page.evaluate(() => (window as unknown as Record<string, unknown>).__attachmentScript)).toBeUndefined()
  await page.keyboard.press("Escape")
  await expect(trigger).toBeFocused()
  await page.reload()
  trigger = user(page).getByRole("button", { name: "Xem tệp đính kèm phuongtien.txt", exact: true })
  await trigger.click()
  await expect(panel.getByLabel("Nội dung tài liệu")).toHaveText(text)
  await page.keyboard.press("Escape")
  await page.getByRole("link", { name: "QA session B — separate history", exact: true }).click()
  await expect(page.getByRole("button", { name: "Xem tệp đính kèm phuongtien.txt", exact: true })).toHaveCount(0)
  await page.goto(sessionUrl)
  await expect(user(page).getByRole("button", { name: "Xem tệp đính kèm phuongtien.txt", exact: true })).toBeVisible()
  const requests = qa.requests.filter(r => r.method === "POST" && r.path.endsWith("/chat/stream"))
  expect(requests).toHaveLength(1)
  const references = JSON.parse(requests[0].body!).attachments
  expect(references).toHaveLength(1)
  expect(Object.keys(references[0]).sort()).toEqual(["document_id", "version_id"])
  expect(qa.requests.filter(r => r.method === "DELETE")).toEqual([])
  expect(qa.requests.some(r => r.path === `/lifecycle/documents/${references[0].document_id}/versions/${references[0].version_id}/preview`)).toBe(true)
})

test("real multi-sheet XLSX file auto-uploads and displays read-only tables before/after send and refresh", async ({ page, qa }) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto("/chat")
  await picker(page).setInputFiles(workbookPath)
  await expect(chips(page)).toContainText("Ready")
  await page.getByRole("button", { name: "Xem trước vehicles.xlsx", exact: true }).click()
  const panel = page.getByRole("dialog", { name: "vehicles.xlsx", exact: true })
  await expect(panel.getByRole("region", { name: "Sheet Vehicles", exact: true })).toContainText("Airplane")
  await expect(panel.getByRole("region", { name: "Sheet Vehicles", exact: true })).toContainText("900")
  await expect(panel.getByRole("region", { name: "Sheet Policies", exact: true })).toContainText("valid license")
  await expect(panel.getByRole("textbox")).toHaveCount(0)
  await page.keyboard.press("Escape")
  await question(page).fill("Airplane speed")
  await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click()
  await expect(page).toHaveURL(/\/chat\/[0-9a-f-]{36}$/)
  await page.reload()
  await user(page).getByRole("button", { name: "Xem tệp đính kèm vehicles.xlsx", exact: true }).click()
  await expect(panel.getByRole("region", { name: "Sheet Vehicles", exact: true })).toContainText("900")
  expect(qa.requests.filter(r => r.method === "POST" && r.path.endsWith("/documents/upload"))).toHaveLength(1)
  expect(qa.requests.filter(r => r.method === "DELETE")).toEqual([])
})

test("legacy history stays unchanged and unavailable document previews do not remove the persisted chip", async ({ page }) => {
  await page.goto("/chat/bbbbbbbb-1111-4111-8111-111111111111")
  await expect(user(page)).toContainText("QA question")
  await expect(page.getByLabel("Tệp đính kèm tin nhắn")).toHaveCount(0)
  await picker(page).setInputFiles({ name: "phuongtien.txt", mimeType: "text/plain", buffer: Buffer.from("Vehicles") })
  await expect(chips(page)).toContainText("Ready")
  await question(page).fill("New turn")
  await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click()
  await expect(question(page)).toHaveValue("")
  await page.route("**/documents/*/versions/*/preview", route => route.fulfill({ status: 410, json: { detail: "Deleted" } }))
  const trigger = user(page).getByRole("button", { name: "Xem tệp đính kèm phuongtien.txt", exact: true })
  await trigger.click()
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("đã bị xóa")
  await page.keyboard.press("Escape")
  await expect(trigger).toBeVisible()
})

test("uploading/invalid attachments cannot be sent; MIME validation prevents fake Excel uploads", async ({ page, qa }) => {
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  await page.route("**/lifecycle/documents/upload", async route => { await gate; await route.fallback() })
  try {
    await page.goto("/chat")
    await question(page).fill("Wait for the file")
    await picker(page).setInputFiles({ name: "vehicles.xlsx", mimeType: "text/plain", buffer: Buffer.from("not a spreadsheet") })
    await expect(chips(page)).toContainText("Failed")
    await expect(chips(page)).toContainText("MIME")
    await page.getByRole("button", { name: "Xem trước vehicles.xlsx", exact: true }).click()
    await expect(page.getByRole("dialog").getByRole("alert")).toContainText("MIME")
    await page.keyboard.press("Escape")
    await expect(page.getByRole("button", { name: "Gửi câu hỏi", exact: true })).toBeDisabled()
    expect(qa.requests.filter(r => r.method === "POST")).toHaveLength(0)
    await page.getByRole("button", { name: "Gỡ vehicles.xlsx", exact: true }).click()
    await picker(page).setInputFiles(workbookPath)
    await expect(chips(page)).toContainText("Uploading")
    await expect(page.getByRole("button", { name: "Gửi câu hỏi", exact: true })).toBeDisabled()
    release()
    await expect(chips(page)).toContainText("Ready")
    await expect(page.getByRole("button", { name: "Gửi câu hỏi", exact: true })).toBeEnabled()
  } finally { release() }
})
