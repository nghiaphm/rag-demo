import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const require = createRequire(import.meta.url);
const cache = new Map();
function load(relative) {
  if (cache.has(relative)) return cache.get(relative);
  const base = fileURLToPath(new URL(`../${relative}`, import.meta.url));
  const filename = fs.existsSync(`${base}.tsx`) ? `${base}.tsx` : `${base}.ts`;
  const exports = {};
  cache.set(relative, exports);
  new Function("exports", "require", ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText)(exports, specifier => specifier.startsWith("@/") ? load(specifier.slice(2)) : require(specifier));
  return exports;
}
const { safeApiErrorMessage, safeStreamErrorMessage } = load("lib/api/error-ux");
const { createApiClient, ApiClientError } = load("lib/api/client");
const { checkHealth } = load("lib/api/health");
const { HealthController } = load("lib/health/controller");
const { ServiceHealthView } = load("components/layout/service-health");
const { SessionsController, SessionLookupController } = load("lib/sessions/controller");
const { HistoryController } = load("lib/sessions/history");
const { DocumentsController } = load("lib/documents/controller");
const { ChatController } = load("lib/chat/controller");
const { createChatStreamClient, ChatStreamClientError } = load("lib/api/chat");
const id = n => `${n.toString(16).padStart(8, "0")}-1111-4111-8111-111111111111`;
const privateText = "mongodb://private-credential/private-document";
const dependency = (name, ok, code = ok ? "connected" : "timeout") => ({ service: name, ok, code, message: privateText });
const healthyBody = () => ({ status: "ok", dependencies: { mongodb: dependency("mongodb", true), qdrant: dependency("qdrant", true) } });
const report = { api: "ok", status: "ok", httpStatus: 200, mongodb: { ok: true, code: "connected", message: "Sẵn sàng" }, qdrant: { ok: true, code: "connected", message: "Sẵn sàng" } };
const start = { event: "start", data: { sequence: 1, request_id: id(2), session_id: id(1), user_message_id: id(3), assistant_message_id: id(4), mode: "PERSISTENT" } };
const delta = { event: "delta", data: { sequence: 3, content: "Partial  text\n " } };
const done = { event: "done", data: { sequence: 4, status: "COMPLETED", usage: null } };
const services = overrides => ({ createSession: async () => ({ session_id: id(1) }), stream: async () => ({}), ...overrides });

test("HTTP 422/404/409/429/503 and network copy is safe and status-specific, never raw detail", () => {
  const messages = [];
  for (const status of [422, 404, 409, 429, 503]) {
    const message = safeApiErrorMessage({ status, kind: "http", message: privateText, detail: privateText, input: privateText });
    assert(!message.includes(privateText));
    messages.push(message);
  }
  assert.equal(new Set(messages).size, 5);
  assert.match(messages[0], /không hợp lệ/);
  assert.match(messages[2], /xung đột/);
  assert.match(messages[3], /Hãy chờ/);
  assert.match(messages[4], /chưa sẵn sàng/);
  assert.match(safeApiErrorMessage({ kind: "network", message: privateText }), /Kết nối bị gián đoạn/);
  assert.equal(typeof safeStreamErrorMessage("__proto__"), "string");
});

test("health reads exact routes and preserves typed 503 degraded readiness without leaking messages", async () => {
  const calls = [];
  const api = createApiClient({ baseUrl: "http://mock.invalid", fetch: async (url, options) => {
    calls.push([url, options.method]);
    if (url.endsWith("/health")) return Response.json({ status: "ok", llm_model: "fixture" });
    return Response.json({ status: "degraded", dependencies: { mongodb: dependency("mongodb", false), qdrant: dependency("qdrant", true) } }, { status: 503 });
  } });
  const result = await checkHealth(api);
  assert.equal(result.httpStatus, 503);
  assert.equal(result.status, "degraded");
  assert.equal(result.mongodb.ok, false);
  assert.equal(result.qdrant.ok, true);
  assert(!JSON.stringify(result).includes(privateText));
  assert.deepEqual(calls, [["http://mock.invalid/health", "GET"], ["http://mock.invalid/health/dependencies", "GET"]]);
  const html = renderToStaticMarkup(React.createElement(ServiceHealthView, { state: { status: "ready", report: result, error: null }, onCheck: () => {} }));
  assert.match(html, /HTTP 503/);
  assert.match(html, /MongoDB: Hết thời gian chờ/);
  assert.match(html, /Groq: chưa được kiểm tra/);
  assert(!html.includes(privateText));
});

test("health validates both dependency reports and default REST 503 handling stays unchanged", async () => {
  const api = createApiClient({ baseUrl: "http://mock.invalid", fetch: async () => Response.json(healthyBody(), { status: 503 }) });
  await assert.rejects(api.request("/health/dependencies"), error => error.status === 503 && error.kind === "http");
  await assert.rejects(api.request("/health/dependencies", { acceptedStatuses: ["503"] }), TypeError);
  for (const body of [{ ...healthyBody(), status: "degraded" }, { status: "ok", dependencies: { mongodb: dependency("mongodb", true) } }]) {
    await assert.rejects(checkHealth({ request: async route => route === "/health" ? { status: 200, data: { status: "ok", llm_model: "fixture" } } : { status: 200, data: body } }), TypeError);
  }
});

test("health is manual, blocks duplicates, clears error/loading and runs no request loop", async () => {
  let calls = 0;
  let release;
  let fail = false;
  const controller = new HealthController(async () => { calls++; if (fail) throw new ApiClientError("network", privateText); return new Promise(resolve => { release = resolve; }); });
  assert.equal(calls, 0);
  const pending = controller.check();
  await controller.check();
  assert.equal(calls, 1);
  assert.equal(controller.getSnapshot().status, "loading");
  release(report);
  await pending;
  assert.equal(controller.getSnapshot().status, "ready");
  fail = true;
  await controller.check();
  assert.equal(calls, 2);
  assert.equal(controller.getSnapshot().status, "error");
  assert(!controller.getSnapshot().error.includes(privateText));
  assert.equal(controller.getSnapshot().report, null);
});

test("health unmount clears spinner and ignores late results", async () => {
  let release;
  const controller = new HealthController(async () => new Promise(resolve => { release = resolve; }));
  const pending = controller.check();
  controller.dispose();
  assert.equal(controller.getSnapshot().status, "idle");
  release(report);
  await pending;
  assert.equal(controller.getSnapshot().report, null);
});

test("session/document/history read errors keep HTTP-specific UX and unlock user retry", async () => {
  for (const status of [422, 404, 409, 429, 503]) {
    const error = new ApiClientError("http", privateText, status);
    const expected = safeApiErrorMessage(error);
    const sessions = new SessionsController({ list: async () => { throw error; }, create: async () => { throw error; } });
    await sessions.load();
    assert.equal(sessions.getSnapshot().status, "error");
    assert.equal(sessions.getSnapshot().error, expected);
    await sessions.createNew();
    assert.equal(sessions.getSnapshot().isCreating, false);
    const lookup = new SessionLookupController(id(1), { isValidId: () => true, get: async () => { throw error; } });
    await lookup.load();
    assert.equal(lookup.getSnapshot().status, status === 404 ? "missing" : "error");
    assert.equal(lookup.getSnapshot().error, expected);
    const history = new HistoryController(id(1), { list: async () => { throw error; } });
    await history.load();
    assert.equal(history.getSnapshot().status, "error");
    assert.equal(history.getSnapshot().error, expected);
    const documents = new DocumentsController({ list: async () => { throw error; }, get: async () => { throw error; } });
    await documents.reload();
    await documents.select(id(1));
    assert.equal(documents.getSnapshot().error, expected);
    assert.equal(documents.getSnapshot().detailError, expected);
    assert.notEqual(documents.getSnapshot().detailStatus, "loading");
  }
});

test("pre-header chat HTTP failures keep safe status copy, terminal FAILED and no automatic resend", async () => {
  for (const status of [422, 404, 409, 429, 503]) {
    let calls = 0;
    const error = new ChatStreamClientError("before_response", "http", privateText, status);
    const controller = new ChatController(services({ stream: async () => { calls++; throw error; } }), id(1));
    await controller.submit("fixture");
    assert.equal(calls, 1);
    assert.equal(controller.getSnapshot().isGenerating, false);
    assert.equal(controller.getSnapshot().messages[0].status, "FAILED");
    assert.equal(controller.getSnapshot().messages[1].status, "FAILED");
    assert.equal(controller.getSnapshot().messages[1].error.message, safeApiErrorMessage(error));
  }
});

test("post-header SSE error preserves partial/usage/code, sanitizes message and never retries", async () => {
  let calls = 0;
  const usage = { input_tokens: 1, output_tokens: 2, total_tokens: 3 };
  const controller = new ChatController(services({ stream: async (_payload, options) => {
    calls++;
    for (const event of [start, delta, { event: "error", data: { sequence: 4, status: "PARTIAL", usage,
      error: { code: "RAG_STREAM_ERROR", message: privateText, retryable: true } } }]) options.onEvent(event);
    return {};
  } }), id(1));
  await controller.submit("fixture");
  const state = controller.getSnapshot();
  assert.equal(state.isGenerating, false);
  assert.equal(state.messages[1].content, delta.data.content);
  assert.equal(state.messages[1].status, "PARTIAL");
  assert.deepEqual(state.messages[1].usage, usage);
  assert.equal(state.messages[1].error.code, "RAG_STREAM_ERROR");
  assert(!state.messages[1].error.message.includes(privateText));
  assert.equal(calls, 1);
});

test("hung pre-header stream releases loading at client deadline without transport cooperation", async () => {
  const controller = new ChatController(services({ stream: async () => new Promise(() => {}) }), id(1), [], 10);
  await controller.submit("fixture");
  assert.equal(controller.getSnapshot().isGenerating, false);
  assert.equal(controller.getSnapshot().messages[1].error.code, "CLIENT_STREAM_TIMEOUT");
  assert.equal(controller.getSnapshot().messages[1].status, "FAILED");
});

test("hung session creation releases loading and never starts generation", async () => {
  const controller = new ChatController(services({ createSession: async () => new Promise(() => {}), stream: async () => assert.fail() }), null, [], 10);
  await controller.submit("fixture");
  assert.equal(controller.getSnapshot().isGenerating, false);
  assert.equal(controller.getSnapshot().sessionId, null);
});

test("hung post-terminal persistence read preserves COMPLETED and ends verification spinner", async () => {
  const controller = new ChatController(services({ stream: async (_payload, options) => {
    for (const event of [start, delta, done]) options.onEvent(event);
    return {};
  }, loadHistory: async () => new Promise(() => {}) }), id(1), [], 10);
  await controller.submit("fixture");
  assert.equal(controller.getSnapshot().isGenerating, false);
  assert.equal(controller.getSnapshot().isVerifyingHistory, false);
  assert.equal(controller.getSnapshot().messages[1].status, "COMPLETED");
  assert(controller.getSnapshot().persistenceError);
});

test("real SSE reader is cancelled at deadline and partial text survives an indefinitely open body", async () => {
  let cancelled = false;
  const encoder = new TextEncoder();
  const stream = createChatStreamClient({ baseUrl: "http://mock.invalid", fetch: async () => new Response(new ReadableStream({ start(controller) {
    const events = [start, { event: "metadata", data: { sequence: 2, model: null, sources: [] } }, delta];
    controller.enqueue(encoder.encode(events.map(event => `event: ${event.event}\ndata: ${JSON.stringify(event.data)}\n\n`).join("")));
  }, cancel() { cancelled = true; } }), { headers: { "Content-Type": "text/event-stream" } }) });
  const controller = new ChatController(services({ stream: stream.stream }), id(1), [], 20);
  await controller.submit("fixture");
  assert.equal(cancelled, true);
  assert.equal(controller.getSnapshot().messages[1].status, "PARTIAL");
  assert.equal(controller.getSnapshot().messages[1].content, delta.data.content);
  assert.equal(controller.getSnapshot().isGenerating, false);
});
