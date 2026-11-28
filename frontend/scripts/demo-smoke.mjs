// Owned Next.js server (next dev when port 3000/lock are free, or isolated standalone server) + RAM-only mock;
// zero live backend/provider calls, screenshots, or video.
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import net from "node:net";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import { chromium, expect } from "@playwright/test";
import { createQaMockServer } from "./qa-mock-api.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const mockOrigin = "http://127.0.0.1:4011";
const temporary = fileURLToPath(new URL("../.playwright-tmp/demo-smoke/", import.meta.url));
mkdirSync(temporary, { recursive: true });

// Keep TMP/TEMP/TMPDIR scoped to Windows only; on Linux, long workspace paths exceed
// the 108-byte AF_UNIX sun_path limit for Chromium's SingletonSocket inside TMPDIR.
const childTmpEnv =
  process.platform === "win32"
    ? { TMP: temporary, TEMP: temporary, TMPDIR: temporary }
    : {};

async function canBind(port, host) {
  const probe = net.createServer();
  try {
    probe.listen({ port, host, exclusive: true });
    await once(probe, "listening");
    await new Promise((resolve, reject) => probe.close(error => error ? reject(error) : resolve()));
    return true;
  } catch (error) {
    if (error && (error.code === "EAFNOSUPPORT" || error.code === "EADDRNOTAVAIL")) return true;
    return false;
  }
}

async function isHttpListening(port) {
  for (const host of ["127.0.0.1", "[::1]"]) {
    try {
      await fetch(`http://${host}:${port}/`, { signal: AbortSignal.timeout(400) });
      return true;
    } catch { /* connection refused means nothing listening */ }
  }
  return false;
}

async function isPortCompletelyFree(port) {
  if (await isHttpListening(port)) return false;
  return (await canBind(port, "127.0.0.1")) && (await canBind(port, "::")) && (await canBind(port, "0.0.0.0"));
}

async function requireFreePort(port) {
  if (!(await isPortCompletelyFree(port))) {
    throw new Error(`Port ${port} is already in use`);
  }
}

async function allocateFreePort() {
  const probe = net.createServer();
  probe.listen(0, "127.0.0.1");
  await once(probe, "listening");
  const allocated = probe.address().port;
  await new Promise((resolve, reject) => probe.close(error => error ? reject(error) : resolve()));
  return allocated;
}

let uiPort = 3000;
let ui = `http://127.0.0.1:${uiPort}`;

let server, browser, context;
let devOutput = "";
let timedOut = false;
const mock = createQaMockServer({ delayMs: 40, deltaMs: 10 });
const failures = [];
const posts = [];
const sessionCreates = [];
const passed = [];
const check = name => { passed.push(name); console.log(`PASS ${name}`); };

async function run() {
  await requireFreePort(4011);
  const devLockPath = fileURLToPath(new URL("../.next/dev/lock", import.meta.url));
  const standaloneServerPath = fileURLToPath(new URL("../.next/standalone/server.js", import.meta.url));
  const useDevServer = (await isPortCompletelyFree(3000)) && !existsSync(devLockPath);

  mock.listen(4011, "127.0.0.1");
  await once(mock, "listening"); // EADDRINUSE fails closed; never reuse another mock.

  if (useDevServer) {
    uiPort = 3000;
    ui = `http://127.0.0.1:${uiPort}`;
    server = spawn(process.execPath, ["node_modules/next/dist/bin/next", "dev", "--hostname", "127.0.0.1", "--port", "3000"], {
      cwd: root, windowsHide: true, stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, NEXT_PUBLIC_API_BASE_URL: `${mockOrigin}/lifecycle`, ...childTmpEnv },
    });
  } else {
    if (!existsSync(standaloneServerPath)) {
      const buildScript = fileURLToPath(new URL("./build-e2e.mjs", import.meta.url));
      let build = spawnSync(process.execPath, [buildScript], { cwd: root, stdio: "inherit", windowsHide: true });
      if (build.status !== 0) {
        build = spawnSync(process.execPath, [buildScript], { cwd: root, stdio: "inherit", windowsHide: true });
      }
      if (build.status !== 0) throw new Error("Standalone demo build failed");
    }
    uiPort = await allocateFreePort();
    ui = `http://127.0.0.1:${uiPort}`;
    server = spawn(process.execPath, [standaloneServerPath], {
      cwd: root, windowsHide: true, stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, HOSTNAME: "127.0.0.1", PORT: String(uiPort), NEXT_PUBLIC_API_BASE_URL: `${mockOrigin}/lifecycle`, ...childTmpEnv },
    });
  }

  server.on("error", error => failures.push(error.message));
  for (const output of [server.stdout, server.stderr]) output.on("data", chunk => { devOutput = (devOutput + chunk).slice(-12000); });
  const readyDeadline = Date.now() + 90_000;
  while (true) {
    if (server.exitCode !== null || failures.length) throw new Error("Owned Next.js demo server failed to start");
    try {
      const response = await fetch(`${ui}/chat`, { signal: AbortSignal.timeout(5000) });
      if (response.ok && server.exitCode === null) break;
    } catch { /* Poll only the owned UI readiness, never API mutations. */ }
    if (Date.now() > readyDeadline) throw new Error("Next.js demo server readiness timeout");
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  check(`fresh ${useDevServer ? "next dev" : "standalone"} startup /chat HTTP 200 (port ${uiPort})`);
  browser = await chromium.launch({ channel: "chromium", headless: true, env: { ...process.env, ...childTmpEnv } });
  context = await browser.newContext({ serviceWorkers: "block", viewport: { width: 1280, height: 800 } });
  await context.route("**/*", async route => {
    const request = route.request();
    const origin = new URL(request.url()).origin;
    if (![ui, mockOrigin].includes(origin)) {
      failures.push(`Unexpected origin: ${origin}`);
      await route.abort(); return;
    }
    if (request.method() === "POST" && request.url().endsWith("/sessions")) {
      sessionCreates.push(request.postDataJSON());
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

  // HR Portal Dashboard + isolated HrChatbotWidget verification
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`${ui}/hr`);
  await expect(page.locator(".hr-theme").first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("heading", { name: "Kho tri thức RAG (Dữ liệu thực từ API)" })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Mở Trợ lý HR", exact: true }).click();
  const hrDialog = page.getByRole("dialog");
  await expect(hrDialog).toBeVisible();
  await hrDialog.getByRole("textbox", { name: "Câu hỏi", exact: true }).fill("HR demo smoke turn");
  await hrDialog.getByRole("button", { name: "Gửi câu hỏi", exact: true }).click();
  await expect(hrDialog.getByRole("article", { name: "Câu trả lời của trợ lý", exact: true })).toContainText("Mock Markdown", { timeout: 60_000 });
  await expect(hrDialog.getByRole("textbox", { name: "Câu hỏi", exact: true })).toHaveAttribute("aria-readonly", "false", { timeout: 60_000 });
  assert.equal(posts.length, 2);
  assert.notEqual(posts[1].session_id, posts[0].session_id);
  assert.equal(sessionCreates.some(body => body?.surface === "hr"), true);
  check("hr dashboard + isolated HrChatbotWidget SSE turn");

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
  if (server.exitCode === null && server.signalCode === null) throw new Error("Owned demo server did not exit");
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
    await requireFreePort(uiPort);
    await requireFreePort(4011);
    console.log(`PASS teardown: owned server/mock stopped; ports ${uiPort}/4011 free`);
  } catch (error) {
    console.error(`Demo cleanup FAIL: ${error.message}`);
    process.exitCode = 1;
  }
}
if (!process.exitCode) console.log(`Demo smoke: ${passed.length}/${passed.length} PASS; live provider calls=0`);
