import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ts from "typescript";
import { createQaMockServer } from "../scripts/qa-mock-api.mjs";

const require = createRequire(import.meta.url), cache = new Map();
function load(relative) {
  if (cache.has(relative)) return cache.get(relative);
  const base = fileURLToPath(new URL(`../${relative}`, import.meta.url));
  const file = fs.existsSync(`${base}.tsx`) ? `${base}.tsx` : `${base}.ts`;
  const exports = {};
  cache.set(relative, exports);
  new Function("exports", "require", ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText)(exports, name => {
    if (name.startsWith("@/")) return load(name.slice(2));
    if (name === "react-markdown") return { default: ReactMarkdown };
    if (name === "remark-gfm") return { default: remarkGfm };
    return require(name);
  });
  return exports;
}
const { ChatController } = load("lib/chat/controller");
const { createChatServices } = load("lib/chat/services");
const { SessionsController } = load("lib/sessions/controller");
const { subscribeSessionList, invalidateSessionList } = load("lib/sessions/invalidation");
const { createApiClient } = load("lib/api/client");
const { listSessions, createSession } = load("lib/api/sessions");
const { historyMessageToViewMessage } = load("lib/sessions/history");
const { canonicalChatPath } = load("lib/chat/recovery");
const { ChatRecovery } = load("components/chat/chat-recovery");
const { ChatMessage } = load("components/chat/chat-message");
const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, props));
const tick = () => new Promise(resolve => setImmediate(resolve));
async function until(predicate) {
  const deadline = Date.now() + 3000;
  while (!predicate()) { assert(Date.now() < deadline, "condition did not settle"); await tick(); }
}
async function fixture(run, options = {}) {
  const calls = [];
  const server = createQaMockServer({ delayMs: 0, deltaMs: 0, ...options });
  server.on("request", req => calls.push([req.method, req.url]));
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const url = `http://127.0.0.1:${server.address().port}`;
  try { await run(url, calls); } finally {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
}

test("composer service creation reconciles sidebar before terminal; three turns reuse one session and distinct request IDs", () => fixture(async (url, calls) => {
  const api = createApiClient({ baseUrl: url });
  const sidebar = new SessionsController({ list: (signal, query) => listSessions(api, query, signal), create: signal => createSession(api, {}, signal) });
  const unsubscribe = subscribeSessionList(url + "/", sidebar.invalidate);
  const chat = new ChatController(createChatServices(url));
  try {
    await sidebar.load();
    const pending = chat.submit("first fixture");
    assert.equal(await chat.submit("duplicate"), false);
    await until(() => sidebar.getSnapshot().sessions.some(s => s.session_id === chat.getSnapshot().sessionId));
    assert.equal(chat.getSnapshot().isGenerating, true);
    assert.equal(canonicalChatPath(null, chat.getSnapshot()), null);
    assert.match(render(ChatRecovery, { state: chat.getSnapshot(), initialSessionId: null }), /target="_blank"/);
    await pending;
    const id = chat.getSnapshot().sessionId;
    for (const question of ["second fixture", "third fixture"]) await chat.submit(question);
    const state = chat.getSnapshot();
    assert.equal(state.sessionId, id);
    assert.equal(state.historyVerified, true);
    assert.equal(canonicalChatPath(null, state), `/chat/${id}`);
    assert.equal(canonicalChatPath(id, state), null);
    assert.equal(calls.filter(([m, p]) => m === "POST" && p === "/sessions").length, 1);
    assert.equal(calls.filter(([m, p]) => m === "POST" && p === "/chat/stream").length, 3);
    assert.equal(new Set(state.messages.filter(m => m.role === "assistant").map(m => m.requestId)).size, 3);
    const refreshed = await createChatServices(url).loadHistory(id, new AbortController().signal);
    assert.deepEqual(refreshed.map(m => [m.messageId, m.content, m.status]), state.messages.map(m => [m.messageId, m.content, m.status]));
  } finally { unsubscribe(); sidebar.dispose(); chat.dispose(); }
}, { deltaMs: 3 }));

test("invalidation stays scoped and coalesces across protected mutations, including failures", async () => {
  let reads = 0, release, otherReads = 0;
  const sidebar = new SessionsController({ list: async () => { reads++; return { items: [], total: 0, offset: 0, limit: 50 }; },
    create: () => assert.fail(), remove: () => new Promise(resolve => { release = resolve; }) });
  const off = subscribeSessionList("http://fixture/api", sidebar.invalidate);
  const otherOff = subscribeSessionList("http://fixture/other", () => otherReads++);
  await sidebar.load();
  const removing = sidebar.remove("a", true);
  invalidateSessionList("http://fixture/api/"); invalidateSessionList("http://fixture/api");
  assert.equal(reads, 1);
  release({ session_id: "a" }); await removing; await tick();
  assert.equal(reads, 2); assert.equal(otherReads, 0);
  const failing = new SessionsController({ list: async () => { reads++; return { items: [], total: 0, offset: 0, limit: 50 }; },
    create: () => new Promise((_, reject) => { release = reject; }) });
  const creating = failing.createNew(); failing.invalidate(); failing.invalidate();
  release(new Error("unknown response")); await creating; await tick();
  assert.equal(reads, 3);
  off(); otherOff(); sidebar.dispose(); failing.dispose();
  invalidateSessionList("http://fixture/api"); assert.equal(reads, 3);
});

test("Stop/disconnect keep recovery session and exact partial text without automatic canonical navigation or replay", () => fixture(async (url, calls) => {
  const controller = new ChatController(createChatServices(url));
  await controller.submit("[disconnect]");
  let state = controller.getSnapshot();
  const id = state.sessionId;
  assert.equal(state.isGenerating, false); assert.equal(state.historyVerified, false);
  assert.equal(state.messages.at(-1).status, "PARTIAL");
  assert.equal(canonicalChatPath(null, state), null);
  assert.match(render(ChatRecovery, { state, initialSessionId: null }), new RegExp(`/chat/${id}`));
  const pending = controller.submit("stop fixture");
  await until(() => controller.getSnapshot().messages.at(-1).content.length > 0);
  const partial = controller.getSnapshot().messages.at(-1).content;
  assert.equal(controller.stop(), true); await pending;
  state = controller.getSnapshot();
  assert.equal(state.messages.at(-1).content, partial);
  assert.equal(state.isGenerating, false); assert.equal(canonicalChatPath(null, state), null);
  await tick();
  assert.equal(calls.filter(([m, p]) => m === "POST" && p === "/sessions").length, 1);
  assert.equal(calls.filter(([m, p]) => m === "POST" && p === "/chat/stream").length, 2);
  controller.dispose();
}, { deltaMs: 3 }));

test("failed verification and delayed terminal history retain the recovery link; a later verified turn can canonicalize", () => fixture(async url => {
  const services = createChatServices(url);
  let fail = true;
  const controller = new ChatController({ ...services, loadHistory: async (id, signal) => {
    if (fail) throw new Error("read unavailable");
    return services.loadHistory(id, signal);
  } });
  await controller.submit("first");
  const id = controller.getSnapshot().sessionId;
  assert(controller.getSnapshot().persistenceError);
  assert.equal(canonicalChatPath(null, controller.getSnapshot()), null);
  fail = false; await controller.submit("second deliberate question");
  assert.equal(canonicalChatPath(null, controller.getSnapshot()), `/chat/${id}`);
  const delayed = new ChatController({ ...services, loadHistory: async (id, signal) => (await services.loadHistory(id, signal)).map(m => m.role === "assistant" ? { ...m, status: "STREAMING" } : m) }, id);
  await delayed.submit("third");
  assert(delayed.getSnapshot().persistenceError);
  assert.equal(delayed.getSnapshot().historyVerified, false);
  assert.equal(delayed.getSnapshot().messages.at(-1).status, "COMPLETED");
  assert.equal(delayed.getSnapshot().isGenerating, false);
  controller.dispose(); delayed.dispose();
}));

test("restored PENDING/STREAMING are preserved snapshots without live spinners; terminal errors and explicit reload remain", () => {
  for (const role of ["USER", "ASSISTANT"]) for (const status of ["PENDING", "STREAMING", "PARTIAL", "FAILED"]) {
    const dto = { session_id: "saved", message_id: "message", request_id: "request", role, content: "", status,
      model: null, citations: [], usage: null, error_code: null };
    const message = historyMessageToViewMessage(dto);
    const state = { sessionId: "saved", messages: [message], isGenerating: false, historyVerified: false, persistenceError: null };
    const html = render(ChatMessage, { message });
    assert.equal(message.status, status);
    assert(!html.includes("animate-spin")); assert(!html.includes("Đang chuẩn bị"));
    const recovery = render(ChatRecovery, { state, initialSessionId: "saved" });
    if (status === "PENDING" || status === "STREAMING") {
      assert.match(html, new RegExp(`Trạng thái backend: ${status}`));
      assert.match(recovery, /href="\/chat\/saved"/); assert.match(recovery, /Tải lại lịch sử/);
      assert.match(recovery, /không kết nối/);
      const live = render(ChatMessage, { message: { ...message, origin: undefined, role: "assistant" } });
      assert.match(live, /animate-spin/);
    } else assert.equal(recovery, "");
  }
});

test("opening historical STREAMING does not resume; deliberate submit receives backend409 once and can reread after terminal", () => fixture(async (url, calls) => {
  const services = createChatServices(url);
  const session = await services.createSession(new AbortController().signal);
  const remoteAbort = new AbortController();
  let started = false;
  const remote = services.stream({ session_id: session.session_id, question: "remote mock" }, {
    signal: remoteAbort.signal, onEvent: event => { if (event.event === "start") started = true; },
  });
  try {
    await until(() => started);
    const history = await services.loadHistory(session.session_id, new AbortController().signal);
    assert(history.some(m => m.status === "STREAMING"));
    const controller = new ChatController(services, session.session_id, history);
    const postsBefore = calls.filter(([m, p]) => m === "POST" && p === "/chat/stream").length;
    await tick();
    assert.equal(calls.filter(([m, p]) => m === "POST" && p === "/chat/stream").length, postsBefore);
    await controller.submit("deliberate question");
    const state = controller.getSnapshot();
    assert.equal(state.isGenerating, false); assert.equal(state.historyVerified, false);
    assert.equal(state.messages.at(-1).status, "FAILED");
    assert.match(state.messages.at(-1).error.message, /xung đột|đang/i);
    assert(state.messages.some(m => m.origin === "history" && m.status === "STREAMING"));
    await tick();
    assert.equal(calls.filter(([m, p]) => m === "POST" && p === "/chat/stream").length, postsBefore + 1);
    await remote;
    const refreshed = await services.loadHistory(session.session_id, new AbortController().signal);
    assert.equal(refreshed.length, 2); assert.equal(refreshed.at(-1).status, "COMPLETED");
    controller.dispose();
  } finally { remoteAbort.abort(); await remote.catch(() => {}); }
}, { deltaMs: 8 }));
