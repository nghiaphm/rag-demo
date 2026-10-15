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
let sidebarController, chatController, composer;
const effects = [], replacements = [];
function load(relative) {
  if (cache.has(relative)) return cache.get(relative);
  const base = fileURLToPath(new URL(`../${relative}`, import.meta.url));
  const file = fs.existsSync(`${base}.tsx`) ? `${base}.tsx` : `${base}.ts`;
  const exports = {}; cache.set(relative, exports);
  new Function("exports", "require", ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText)(exports, name => {
    if (name === "react" && relative === "hooks/use-sessions") return { ...React,
      useMemo: factory => sidebarController ??= factory(), useEffect: effect => effects.push(effect) };
    if (name === "react" && relative === "components/chat/chat-preview") return { ...React,
      useState: initial => {
        const state = React.useState(initial);
        if (initial === "") return ["composer fixture question", state[1]];
        if (state[0] instanceof load("lib/chat/controller").ChatController) {
          chatController ??= state[0]; return [chatController, state[1]];
        }
        return state;
      }, useEffect: effect => effects.push(effect) };
    if (name === "@/components/chat/chat-composer") return { ChatComposer: props => { composer = props; return React.createElement("div", { "data-composer": true }); } };
    if (name === "next/navigation") return { usePathname: () => "/chat", useRouter: () => ({ replace: path => replacements.push(path), push() {} }) };
    if (name === "next/link") return { default: ({ href, children, ...props }) => React.createElement("a", { href, ...props }, children) };
    if (name === "react-markdown") return { default: ReactMarkdown };
    if (name === "remark-gfm") return { default: remarkGfm };
    return name.startsWith("@/") ? load(name.slice(2)) : require(name);
  });
  return exports;
}
const { SessionNavigation } = load("components/layout/session-navigation");
const { ChatPreview } = load("components/chat/chat-preview");
const { SidebarProvider } = load("components/ui/sidebar");

// Execute the real hook subscription/effect and workspace submit callback around
// real controllers/HTTP. SSR/effect harness only: no DOM hydration/focus claim.
test("assembled sidebar hook and workspace reconcile composer creation without navigating an active stream", async () => {
  const server = createQaMockServer({ delayMs: 0, deltaMs: 3 });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const apiBaseUrl = `http://127.0.0.1:${server.address().port}`;
  const cleanups = [];
  function render() {
    return renderToStaticMarkup(React.createElement(SidebarProvider, null,
      React.createElement(SessionNavigation, { apiBaseUrl }), React.createElement(ChatPreview, { apiBaseUrl })));
  }
  async function until(predicate) {
    const deadline = Date.now() + 5000;
    while (!predicate()) { assert(Date.now() < deadline, "workspace condition did not settle"); await new Promise(resolve => setImmediate(resolve)); }
  }
  try {
    render();
    for (const effect of effects.splice(0)) { const cleanup = effect(); if (cleanup) cleanups.push(cleanup); }
    await until(() => sidebarController.getSnapshot().status === "ready");
    composer.onSubmit(); composer.onSubmit();
    await until(() => sidebarController.getSnapshot().sessions.some(s => s.session_id === chatController.getSnapshot().sessionId));
    const id = chatController.getSnapshot().sessionId;
    assert.equal(chatController.getSnapshot().isGenerating, true);
    assert.deepEqual(replacements, []);
    const html = render();
    assert.match(html, new RegExp(`href="/chat/${id}"`));
    assert.match(html, /Mở lịch sử trong tab mới/);
    await until(() => replacements.length > 0);
    assert.deepEqual(replacements, [`/chat/${id}`]);
    assert.equal(chatController.getSnapshot().historyVerified, true);
    assert.equal(chatController.getSnapshot().messages.length, 2);
    const before = sidebarController.getSnapshot();
    for (const cleanup of cleanups.splice(0).reverse()) cleanup();
    load("lib/sessions/invalidation").invalidateSessionList(apiBaseUrl);
    assert.equal(sidebarController.getSnapshot(), before);
  } finally {
    for (const cleanup of cleanups.reverse()) cleanup();
    server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
  }
});
