import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import React from "react";
import ts from "typescript";
import { createQaMockServer } from "../scripts/qa-mock-api.mjs";

const require = createRequire(import.meta.url), cache = new Map();
let owner;
const hooks = { ...React,
  useId: () => `composer-${owner.question.replace(/\W/g, "")}`,
  useState: initial => {
    const current = owner, i = current.index++;
    if (!(i in current.slots)) current.slots[i] = typeof initial === "function" ? initial() : initial;
    const value = initial === "" ? current.question : current.slots[i];
    if (value?.submit && value?.getSnapshot) current.controller = value;
    return [value, () => {}];
  },
  useRef: initial => { const i = owner.index++; return owner.slots[i] ??= { current: initial }; },
  useEffect: effect => { const i = owner.index++; if (!(i in owner.slots)) { owner.slots[i] = true; owner.effects.push(effect); } },
  useSyncExternalStore: (_subscribe, snapshot) => snapshot(),
};
function load(relative) {
  if (cache.has(relative)) return cache.get(relative);
  const base = fileURLToPath(new URL(`../${relative}`, import.meta.url));
  const file = fs.existsSync(`${base}.tsx`) ? `${base}.tsx` : `${base}.ts`;
  const exports = {}; cache.set(relative, exports);
  new Function("exports", "require", ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText)(exports, name => {
    if (name === "react" && relative === "components/chat/chat-preview") return hooks;
    if (name === "next/navigation") return { useRouter: () => { const current = owner; return { replace: path => current.replacements.push(path) }; } };
    if (name === "@/hooks/use-sessions" && relative === "components/chat/session-chat") return {
      useSession: (_base, id) => ({ status: "ready", session: { session_id: id } }),
      useSessionHistory: () => ({ status: "ready", messages: [] }),
    };
    // These children aren't mounted; the test invokes the actual workspace/
    // composer callbacks. Avoid loading Markdown's ESM subtree unnecessarily.
    if (name === "@/components/chat/chat-message") return { ChatMessage: () => null };
    return name.startsWith("@/") ? load(name.slice(2)) : require(name);
  });
  return exports;
}
const { SessionChat } = load("components/chat/session-chat");
const { ChatComposer } = load("components/chat/chat-composer");
const { createApiClient } = load("lib/api/client");
const { createSession, listSessions } = load("lib/api/sessions");
const { SessionsController } = load("lib/sessions/controller");
const { subscribeSessionList } = load("lib/sessions/invalidation");
const { ChatController } = load("lib/chat/controller");
const { createChatServices } = load("lib/chat/services");
function find(element, type) {
  if (!element || typeof element !== "object") return null;
  if (element.type === type) return element;
  for (const child of React.Children.toArray(element.props?.children)) { const result = find(child, type); if (result) return result; }
  return null;
}
function workspace(apiBaseUrl, sessionId, question) {
  const current = { index: 0, slots: [], effects: [], cleanups: [], replacements: [], question, controller: null };
  owner = current;
  let element = SessionChat({ apiBaseUrl, sessionId });
  // Follow the real route/session -> history -> ChatPreview -> keyed workspace
  // composition; lookup/history hook results are fixture-ready, not browser DOM.
  while (typeof element.type === "function") element = element.type(element.props);
  for (const effect of current.effects.splice(0)) { const cleanup = effect(); if (cleanup) current.cleanups.push(cleanup); }
  owner = null;
  return { ...current, composer: find(element, ChatComposer).props,
    dispose: () => { for (const cleanup of current.cleanups.splice(0).reverse()) cleanup(); } };
}
async function until(predicate) {
  const deadline = Date.now() + 5000;
  while (!predicate()) { assert(Date.now() < deadline, "overlap condition timed out"); await new Promise(resolve => setImmediate(resolve)); }
}

for (const cancelA of [false, true]) test(`two route workspaces keep payload/state/signals isolated; cancelA=${cancelA}`, async () => {
  const server = createQaMockServer({ delayMs: 0, deltaMs: 3 });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${server.address().port}`, api = createApiClient({ baseUrl: base });
  const nativeFetch = globalThis.fetch, requests = [];
  let release;
  const bothOpen = new Promise(resolve => { release = resolve; });
  const sidebar = new SessionsController({ list: (signal, query) => listSessions(api, query, signal), create: signal => createSession(api, {}, signal) });
  const unsubscribe = subscribeSessionList(base, sidebar.invalidate);
  let a, b;
  try {
    const first = await createSession(api, {}), second = await createSession(api, {});
    a = workspace(base, first.session_id, "A fixture");
    b = workspace(base, second.session_id, cancelA ? "B fixture" : "B [error]");
    globalThis.fetch = async (url, init) => {
      const response = await nativeFetch(url, init);
      if (init.method === "POST" && String(url).endsWith("/chat/stream")) {
        requests.push({ body: JSON.parse(init.body), signal: init.signal });
        if (requests.length === 2) release();
        await bothOpen;
      }
      return response;
    };
    a.composer.onSubmit(); b.composer.onSubmit();
    assert(a.controller.getSnapshot().isGenerating); assert(b.controller.getSnapshot().isGenerating);
    await until(() => requests.length === 2 && a.controller.getSnapshot().messages.at(-1).content && b.controller.getSnapshot().messages.at(-1).content);
    assert.notEqual(requests[0].signal, requests[1].signal);
    const expected = new Map([[first.session_id, "A fixture"], [second.session_id, cancelA ? "B fixture" : "B [error]"]]);
    for (const { body } of requests) assert.equal(body.question, expected.get(body.session_id));
    await sidebar.load();
    assert.equal(a.controller.getSnapshot().sessionId, first.session_id);
    assert.equal(b.controller.getSnapshot().sessionId, second.session_id);
    if (cancelA) {
      a.composer.onStop();
      assert.equal(requests.find(r => r.body.session_id === first.session_id).signal.aborted, true);
      assert.equal(requests.find(r => r.body.session_id === second.session_id).signal.aborted, false);
    }
    await until(() => !a.controller.getSnapshot().isGenerating && !b.controller.getSnapshot().isGenerating);
    const sa = a.controller.getSnapshot(), sb = b.controller.getSnapshot();
    assert.equal(sa.messages[0].content, "A fixture"); assert.equal(sb.messages[0].content, expected.get(second.session_id));
    assert.notEqual(sa.messages.at(-1).messageId, sb.messages.at(-1).messageId);
    assert.notEqual(sa.messages.at(-1).requestId, sb.messages.at(-1).requestId);
    assert.equal(sa.messages.at(-1).status, cancelA ? "PARTIAL" : "COMPLETED");
    assert.equal(sb.messages.at(-1).status, cancelA ? "COMPLETED" : "PARTIAL");
    assert.equal(requests.length, 2);
    assert.deepEqual(a.replacements, []); assert.deepEqual(b.replacements, []);
  } finally {
    release(); globalThis.fetch = nativeFetch; a?.dispose(); b?.dispose(); unsubscribe(); sidebar.dispose();
    server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
  }
});

test("two composers without a session create one distinct backend session each and reuse only their own receipt", async () => {
  const server = createQaMockServer({ delayMs: 0, deltaMs: 0 });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  const nativeFetch = globalThis.fetch, creates = [], streams = [];
  const a = new ChatController(createChatServices(base)), b = new ChatController(createChatServices(base));
  globalThis.fetch = async (url, init) => {
    if (init.method === "POST" && String(url).endsWith("/sessions")) creates.push(JSON.parse(init.body));
    if (init.method === "POST" && String(url).endsWith("/chat/stream")) streams.push(JSON.parse(init.body));
    return nativeFetch(url, init);
  };
  try {
    const turns = [a.submit("new A"), b.submit("new B")];
    assert.equal(await a.submit("duplicate A"), false); assert.equal(await b.submit("duplicate B"), false);
    await Promise.all(turns);
    const sa = a.getSnapshot(), sb = b.getSnapshot();
    assert.notEqual(sa.sessionId, sb.sessionId);
    assert.equal(sa.historyVerified, true); assert.equal(sb.historyVerified, true);
    assert.deepEqual(creates, [{}, {}]);
    assert.deepEqual(new Map(streams.map(s => [s.question, s.session_id])), new Map([["new A", sa.sessionId], ["new B", sb.sessionId]]));
  } finally {
    globalThis.fetch = nativeFetch; a.dispose(); b.dispose();
    server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
  }
});
