import { test, expect } from "./fixtures.mjs"

test("DocumentScopeSelector switches ALL_ACTIVE to SELECTED_DOCUMENTS, persists on reload, and resets cleanly", async ({ page, qa }) => {
  await page.goto("/chat")
  await page.getByRole("button", { name: "Cuộc trò chuyện mới" }).click()
  await expect(page).toHaveURL(/\/chat\/[0-9a-f-]{36}$/)

  // Default mode is ALL_ACTIVE (filter visible=true across responsive desktop/mobile headers)
  await expect(page.getByText("Phạm vi: Tất cả tài liệu", { exact: true }).filter({ visible: true })).toBeVisible()
  await page.getByRole("button", { name: "Chọn tài liệu", exact: true }).filter({ visible: true }).click()

  const dialog = page.getByRole("dialog")
  await expect(dialog.getByText("Phạm vi tài liệu truy vấn", { exact: true })).toBeVisible()

  // Switch to SELECTED_DOCUMENTS mode and check the INDEXED fixture document
  await dialog.getByRole("radio", { name: /Chọn tài liệu \(SELECTED\)/ }).click()
  const docCheckbox = dialog.getByRole("checkbox", { name: /so-tay-nhan-vien\.pdf/ })
  await expect(docCheckbox).toBeVisible()
  await docCheckbox.check()
  await dialog.getByRole("button", { name: "Áp dụng phạm vi", exact: true }).click()

  await expect(dialog).toHaveCount(0)
  await expect(page.getByText("Phạm vi: 1 tài liệu đã chọn", { exact: true }).filter({ visible: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "Điều chỉnh phạm vi", exact: true }).filter({ visible: true })).toBeVisible()

  const scopePatchesAfterSelect = qa.requests.filter(
    r => r.method === "PATCH" && r.path.endsWith("/scope"),
  )
  expect(scopePatchesAfterSelect).toHaveLength(1)
  expect(JSON.parse(scopePatchesAfterSelect[0].body!)).toEqual({
    mode: "SELECTED_DOCUMENTS",
    document_ids: ["11111111-1111-4111-8111-111111111111"],
  })

  // Reload session page -> SELECTED_DOCUMENTS scope persists from GET /sessions/:id
  await page.reload()
  await expect(page.getByText("Phạm vi: 1 tài liệu đã chọn", { exact: true }).filter({ visible: true })).toBeVisible()

  // Reset scope back to ALL_ACTIVE via quick reset button
  await page.getByRole("button", { name: "Đặt lại phạm vi về tất cả tài liệu", exact: true }).filter({ visible: true }).click()
  await expect(page.getByText("Phạm vi: Tất cả tài liệu", { exact: true }).filter({ visible: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "Chọn tài liệu", exact: true }).filter({ visible: true })).toBeVisible()

  const scopePatchesAfterReset = qa.requests.filter(
    r => r.method === "PATCH" && r.path.endsWith("/scope"),
  )
  expect(scopePatchesAfterReset).toHaveLength(2)
  expect(JSON.parse(scopePatchesAfterReset[1].body!)).toEqual({
    mode: "ALL_ACTIVE",
    document_ids: [],
  })
})
