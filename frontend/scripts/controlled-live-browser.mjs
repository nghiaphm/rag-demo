// F8-02 opt-in only. Not imported by npm test or the default mock E2E suite.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";
import { expect as baseExpect } from "@playwright/test";

const expect = baseExpect.configure({ timeout: 150_000 });
if (process.env.F8_02_EXECUTE !== "approved") throw new Error("Explicit live approval required");
const runDir = path.resolve(process.argv[2] ?? "");
assert(runDir.startsWith(path.resolve(".playwright-tmp") + path.sep));
const marker = path.basename(runDir);
assert(/^f8_02_[0-9a-f]{32}$/.test(marker));
const result = { status: "IN_PROGRESS", checks: {}, session_ids: [], document_ids: [], timings: [] };
const save = () => fs.writeFileSync(path.join(runDir, "browser.json"), JSON.stringify(result, null, 2));
let stage = "browser_launch", browser;
const deadline = setTimeout(() => {
  result.status = "BLOCKED"; result.blocked_stage = "overall_timeout"; save();
  void browser?.close().finally(() => process.exit(2));
}, 300_000);
save();
try {
  browser = await chromium.launch({ channel: "chromium", headless: true });
  const context = await browser.newContext({ baseURL: "http://127.0.0.1:3000", serviceWorkers: "block" });
  let streamPosts = 0;
  const runtimeErrors = [], unexpectedOrigins = [], histories = [];
  await context.route("**/*", async route => {
    const request = route.request(), url = new URL(request.url());
    if (!["http://127.0.0.1:3000", "http://127.0.0.1:8000"].includes(url.origin)) {
      unexpectedOrigins.push(url.origin); await route.abort(); return;
    }
    if (request.method() === "POST" && url.pathname === "/chat/stream" && ++streamPosts > 3) {
      await route.abort(); return;
    }
    await route.continue();
  });
  await context.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    window.f8Streams = [];
    window.fetch = async (input, init) => {
      const url = input instanceof Request ? input.url : String(input);
      if (!url.endsWith("/chat/stream")) return nativeFetch(input, init);
      const started = performance.now();
      const response = await nativeFetch(input, init);
      const record = { http_status: response.status, headers_ms: performance.now() - started,
        first_event_ms: null, first_delta_ms: null, terminal_ms: null, delta_count: 0, answer: "" };
      window.f8Streams.push(record);
      if (response.ok && response.body) void (async () => {
        const reader = response.clone().body.getReader(), decoder = new TextDecoder();
        let buffer = "";
        try {
          while (true) {
            const { value, done } = await reader.read();
            buffer += decoder.decode(value, { stream: !done });
            const frames = buffer.replace(/\r\n/g, "\n").split("\n\n"); buffer = frames.pop();
            for (const frame of frames) {
              const event = frame.split("\n").find(line => line.startsWith("event:"))?.slice(6).trim();
              const data = JSON.parse(frame.split("\n").filter(line => line.startsWith("data:")).map(line => line.slice(5).trimStart()).join("\n"));
              record.first_event_ms ??= performance.now() - started;
              if (event === "start") Object.assign(record, { request_id: data.request_id, session_id: data.session_id,
                assistant_message_id: data.assistant_message_id, user_message_id: data.user_message_id });
              if (event === "delta") { record.first_delta_ms ??= performance.now() - started; record.delta_count++; record.answer += data.content; }
              if (event === "done" || event === "error") Object.assign(record, { terminal_ms: performance.now() - started,
                status: data.status, terminal: event, usage: data.usage, error_code: data.error?.code ?? null });
            }
            if (done) break;
          }
        } catch { record.transport_incomplete = true; }
      })();
      return response;
    };
  });
  const page = await context.newPage();
  page.on("pageerror", error => runtimeErrors.push(error.name));
  page.on("response", async response => {
    try {
      const url = new URL(response.url()), method = response.request().method();
      if (method === "POST" && url.pathname === "/sessions" && response.status() === 201) {
        result.session_ids.push((await response.json()).session_id); save();
      }
      if (method === "POST" && url.pathname === "/documents/upload" && response.status() === 201) {
        result.document_ids.push((await response.json()).document_id); save();
      }
      if (method === "GET" && /\/sessions\/[^/]+\/messages$/.test(url.pathname) && response.status() === 200) {
        histories.push(await response.json());
      }
    } catch { /* incomplete responses are asserted by their owning stage */ }
  });
  stage = "health_ui";
  await page.goto("/documents");
  await page.getByText("Trạng thái dịch vụ", { exact: true }).click();
  await page.getByRole("button", { name: "Kiểm tra dịch vụ", exact: true }).click();
  await expect(page.getByText("MongoDB và Qdrant sẵn sàng.", { exact: true })).toBeVisible();
  await page.getByText("Trạng thái dịch vụ", { exact: true }).click();
  result.checks[stage] = "PASS"; save();
  stage = "prepare_test_document";
  const fileName = `${marker}.txt`;
  await page.getByRole("button", { name: "Thêm tài liệu", exact: true }).click();
  await page.getByLabel("File tài liệu", { exact: true }).setInputFiles({ name: fileName, mimeType: "text/plain",
    buffer: Buffer.from("F8-02 synthetic QA note. Project code is ORION-482. Support window is 09:00 to 17:00 UTC. Owner team is QA-BLUE.\n") });
  await page.getByRole("button", { name: "Tải lên", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("Phiên bản đã được index và kích hoạt");
  await page.getByRole("button", { name: "Đóng", exact: true }).click();
  await expect(page.getByRole("button", { name: new RegExp(fileName.replaceAll(".", "\\.")) })).toBeVisible();
  result.checks[stage] = "PASS"; save();
  stage = "new_chat_multi_turn";
  await page.getByRole("button", { name: "Cuộc trò chuyện mới", exact: true }).click();
  await expect(page).toHaveURL(/\/chat\/[0-9a-f-]{36}$/);
  const sessionId = page.url().split("/").at(-1);
  const textarea = page.getByRole("textbox", { name: "Câu hỏi", exact: true });
  const questions = [
    "What is the project code in the QA note? Reply in one short sentence and cite [1].",
    "What support window is listed in the QA note? Reply in one short sentence and cite [1].",
    "Which team owns that project? Reply in one short sentence and cite [1].",
  ];
  for (let turn = 0; turn < questions.length; turn++) {
    await textarea.fill(questions[turn]);
    await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click();
    await expect(textarea).toHaveAttribute("aria-readonly", "false");
    await expect.poll(() => page.evaluate(() => window.f8Streams.filter(item => item.terminal_ms !== null).length)).toBe(turn + 1);
    const streams = await page.evaluate(() => window.f8Streams);
    const stream = streams.at(-1);
    assert.equal(stream.session_id, sessionId); assert.equal(stream.terminal, "done"); assert.equal(stream.status, "COMPLETED");
    assert(stream.first_delta_ms !== null && stream.delta_count > 0);
    const persisted = histories.at(-1)?.items.find(message => message.message_id === stream.assistant_message_id);
    assert(persisted); assert.equal(persisted.session_id, sessionId); assert.equal(persisted.request_id, stream.request_id);
    assert.equal(persisted.content, stream.answer); assert.equal(persisted.status, stream.status);
    const timing = { ...stream }; delete timing.answer;
    result.timings.push(timing); save();
  }
  assert.equal(new Set(result.timings.map(item => item.request_id)).size, 3);
  assert.equal(new Set(result.timings.map(item => item.assistant_message_id)).size, 3);
  assert.equal(new Set(result.timings.flatMap(item => [item.user_message_id, item.assistant_message_id])).size, 6);
  assert.equal(streamPosts, 3); assert.equal(result.session_ids.length, 1);
  result.checks[stage] = "PASS"; save();
  stage = "live_citation";
  const reply = page.getByRole("article", { name: "Câu trả lời của trợ lý", exact: true }).last();
  await reply.getByRole("button", { name: /^Xem nguồn \[1\]:/ }).first().click();
  const drawer = page.getByRole("dialog", { name: "Nguồn của câu trả lời", exact: true });
  await expect(drawer).toContainText(fileName);
  await expect(drawer.locator("[data-selected='true']")).toContainText("Nguồn [1]");
  await drawer.getByRole("button", { name: "Đóng", exact: true }).click();
  result.checks[stage] = "PASS"; save();
  stage = "refresh_history";
  await page.reload();
  await expect(page.getByRole("article", { name: "Câu trả lời của trợ lý", exact: true })).toHaveCount(3);
  for (const text of questions) await expect(page.getByText(text, { exact: true })).toBeVisible();
  const restored = page.getByRole("article", { name: "Câu trả lời của trợ lý", exact: true }).last();
  await expect(restored).toContainText("Chưa có thông tin để nối số trích dẫn");
  await restored.getByRole("button", { name: "Nguồn của câu trả lời (1)", exact: true }).click();
  await expect(drawer).toContainText("Trích dẫn đã lưu");
  await drawer.getByRole("button", { name: "Đóng", exact: true }).click();
  result.checks[stage] = "PASS"; save();
  stage = "document_operation";
  await page.getByRole("link", { name: "Tài liệu", exact: true }).click();
  await page.getByRole("button", { name: new RegExp(fileName.replaceAll(".", "\\.")) }).click();
  await page.getByRole("region", { name: "Chi tiết tài liệu", exact: true }).getByRole("button", { name: "Xóa tài liệu", exact: true }).click();
  await page.getByRole("button", { name: "Xác nhận thao tác", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("HTTP 200");
  await expect(page.getByRole("dialog")).toContainText("Raw files được giữ");
  await page.getByRole("button", { name: "Đóng", exact: true }).click();
  result.checks[stage] = "PASS"; save();
  stage = "session_api_cleanup";
  const trigger = page.getByRole("button", { name: /^Thao tác với phiên / }).first();
  await trigger.click(); await page.getByRole("menuitem", { name: "Xóa phiên", exact: true }).click();
  await page.getByRole("button", { name: "Xác nhận xóa", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  assert.deepEqual(runtimeErrors, []); assert.deepEqual(unexpectedOrigins, []);
  result.checks[stage] = "PASS"; result.status = "PASS";
} catch (error) {
  result.status = "BLOCKED"; result.blocked_stage = stage; result.error_type = error.name;
} finally {
  clearTimeout(deadline);
  await browser?.close(); save();
  console.log(JSON.stringify({ live_browser_status: result.status, blocked_stage: result.blocked_stage, checks: result.checks }));
}
process.exitCode = result.status === "PASS" ? 0 : 2;
