// Owned next dev + RAM-only mock; no live backend, providers, screenshots or video.
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import net from "node:net";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import { chromium, expect } from "@playwright/test";
import { createQaMockServer } from "./qa-mock-api.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const ui = "http://127.0.0.1:3000";
const mockOrigin = "http://127.0.0.1:4011";
const temporary = fileURLToPath(new URL("../.playwright-tmp/demo-smoke/", import.meta.url));
mkdirSync(temporary, { recursive: true });

async function requireFreePort(port) {
  const probe = net.createServer();
  probe.listen(port, "127.0.0.1");
  await once(probe, "listening");
  await new Promise((resolve, reject) => probe.close(error => error ? reject(error) : resolve()));
}

let server, browser, context;
let devOutput = "";
let timedOut = false;
const mock = createQaMockServer({ delayMs: 40, deltaMs: 10 });
const failures = [];
const posts = [];
const passed = [];
const check = name => { passed.push(name); console.log(`PASS ${name}`); };

async function run() {
  await requireFreePort(3000);
  mock.listen(4011, "127.0.0.1");
  await once(mock, "listening"); // EADDRINUSE fails closed; never reuse another mock.
  server = spawn(process.execPath, ["node_modules/next/dist/bin/next", "dev", "--hostname", "127.0.0.1", "--port", "3000"], {
    cwd: root, windowsHide: true, stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, NEXT_PUBLIC_API_BASE_URL: `${mockOrigin}/lifecycle`, TMP: temporary, TEMP: temporary, TMPDIR: temporary },
  });
  server.on("error", error => failures.push(error.message));
  for (const output of [server.stdout, server.stderr]) output.on("data", chunk => { devOutput = (devOutput + chunk).slice(-12000); });
  const readyDeadline = Date.now() + 90_000;
  while (true) {
    if (server.exitCode !== null || failures.length) throw new Error("Owned next dev failed to start");
    try {
      const response = await fetch(`${ui}/chat`, { signal: AbortSignal.timeout(5000) });
      if (response.ok) break;
    } catch { /* Poll only the owned UI readiness, never API mutations. */ }
    if (Date.now() > readyDeadline) throw new Error("next dev readiness timeout");
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  check("fresh next dev startup /chat HTTP 200");
  browser = await chromium.launch({ channel: "chromium", headless: true, env: { ...process.env, TMP: temporary, TEMP: temporary, TMPDIR: temporary } });
  context = await browser.newContext({ serviceWorkers: "block", viewport: { width: 1280, height: 800 } });
  await context.route("**/*", async route => {
    const request = route.request();
    const origin = new URL(request.url()).origin;
    if (![ui, mockOrigin].includes(origin)) {
      failures.push(`Unexpected origin: ${origin}`);
      await route.abort(); return;
    }
    if (request.method() === "POST" && request.url().endsWith("/chat/stream")) posts.push(request.postDataJSON());
    await route.continue();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(60_000);
  page.on("pageerror", error => failures.push(error.message));
  await page.goto(ui);
  await expect(page).toHaveURL(`${ui}/chat`, { timeout: 60_000 });
  await page.getByRole("button", { name: "Cuộc trò chuyện mới", exact: true }).click();
  await expect(page).toHaveURL(/\/chat\/[0-9a-f-]{36}$/, { timeout: 60_000 });
  const sessionUrl = page.url();
  check("root redirect + hydrated New Chat navigation");
  await page.getByRole("textbox", { name: "Câu hỏi", exact: true }).fill("F8-03 synthetic demo smoke");
  await page.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click();
  const assistant = page.getByRole("article", { name: "Câu trả lời của trợ lý", exact: true });
  await expect(assistant).toContainText("Mock Markdown", { timeout: 60_000 });
  await expect(page.getByRole("textbox", { name: "Câu hỏi", exact: true })).toHaveAttribute("aria-readonly", "false", { timeout: 60_000 });
  assert.equal(posts.length, 1);
  assert.equal(posts[0].session_id, new URL(sessionUrl).pathname.split("/").at(-1));
  check("one mock SSE turn, correct session, terminal releases composer");
  await page.reload();
  await expect(assistant).toHaveCount(1, { timeout: 60_000 });
  await expect(page.getByText("F8-03 synthetic demo smoke", { exact: true })).toBeVisible();
  assert.equal(page.url(), sessionUrl);
  assert.equal(posts.length, 1);
  check("refresh restores mock history without replay");
  await page.goto(`${ui}/documents`);
  await expect(page.getByRole("button", { name: "Thêm tài liệu", exact: true })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Thêm tài liệu", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  check("documents route + upload dialog Escape");
  await page.setViewportSize({ width: 375, height: 568 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  check("documents 375px no page horizontal overflow");
  assert.deepEqual(failures, []);
  check("browser runtime clean + request origins restricted to UI/mock");
}

const deadline = setTimeout(() => { timedOut = true; void browser?.close(); if (server) void stopDev(); }, 240_000);
async function stopDev() {
  if (!server || server.exitCode !== null || server.signalCode !== null) return;
  if (process.platform === "win32") {
    const result = spawnSync("taskkill", ["/PID", String(server.pid), "/T", "/F"], { windowsHide: true, stdio: "ignore" });
    // The CLI can exit while taskkill is enumerating its tree. Wait for Node's
    // exit notification before diagnosing a nonzero taskkill result as failure.
    if (result.status !== 0) server.kill();
  } else server.kill("SIGTERM");
  for (let attempt = 0; attempt < 30 && server.exitCode === null && server.signalCode === null; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  if (server.exitCode === null && server.signalCode === null) throw new Error("Owned next dev did not exit");
}

try {
  await run();
  assert.equal(timedOut, false);
} catch (error) {
  console.error(`Demo smoke FAIL: ${error.message}`);
  console.error(devOutput);
  process.exitCode = 1;
} finally {
  clearTimeout(deadline);
  const teardown = await Promise.allSettled([context?.close(), browser?.close(), stopDev()]);
  mock.closeAllConnections();
  if (mock.listening) await new Promise(resolve => mock.close(resolve));
  try {
    assert.equal(teardown.some(result => result.status === "rejected"), false, "Owned process/browser teardown failed");
    await requireFreePort(3000);
    await requireFreePort(4011);
    console.log("PASS teardown: owned dev/mock stopped; ports 3000/4011 free");
  } catch (error) {
    console.error(`Demo cleanup FAIL: ${error.message}`);
    process.exitCode = 1;
  }
}
if (!process.exitCode) console.log(`Demo smoke: ${passed.length}/${passed.length} PASS; live provider calls=0`);
