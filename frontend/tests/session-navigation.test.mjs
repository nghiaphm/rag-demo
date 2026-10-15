import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToString, renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const require = createRequire(import.meta.url), cache = new Map();
let pathname = "/documents", suspended = false, sessionReads = 0, urlReads = 0;
const sessions = [
  { session_id: "11111111-1111-4111-8111-111111111111", title: "Session A" },
  { session_id: "22222222-2222-4222-8222-222222222222", title: "Session B" },
];
const pendingPathname = new Promise(() => {});
function load(relative) {
  if (cache.has(relative)) return cache.get(relative);
  const base = fileURLToPath(new URL(`../${relative}`, import.meta.url));
  const file = fs.existsSync(`${base}.tsx`) ? `${base}.tsx` : `${base}.ts`;
  const exports = {};
  cache.set(relative, exports);
  const source = ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  new Function("exports", "require", source)(exports, specifier => {
    if (specifier === "next/navigation") return {
      usePathname: () => { urlReads++; if (suspended) throw pendingPathname; return pathname; },
      useRouter: () => ({ push: () => {} }),
    };
    if (specifier === "next/link") return { default: ({ href, children, ...props }) => React.createElement("a", { href, ...props }, children) };
    if (specifier === "@/hooks/use-sessions") return { useSessions: () => {
      sessionReads++;
      return { sessions, total: 2, status: "ready", isCreating: false, error: null, reload: () => {}, createNew: async () => null };
    } };
    if (specifier.startsWith("@/")) return load(specifier.slice(2));
    return require(specifier);
  });
  return exports;
}
const { SessionNavigation } = load("components/layout/session-navigation");
const { SidebarProvider } = load("components/ui/sidebar");
const tree = apiBaseUrl => React.createElement(SidebarProvider, null, React.createElement(SessionNavigation, { apiBaseUrl }));

test("pathname suspension renders local static fallback without reading session state", () => {
  suspended = true; sessionReads = 0; urlReads = 0;
  const boundary = SessionNavigation({ apiBaseUrl: "http://127.0.0.1:8000" });
  assert.equal(boundary.type, React.Suspense);
  const fallback = renderToStaticMarkup(boundary.props.fallback);
  assert.equal(urlReads, 0);
  assert.match(fallback, /role="status"/);
  assert.match(fallback, /Đang tải điều hướng phiên/);
  assert(!fallback.includes("aria-current"));
  assert(!fallback.includes("Chưa cấu hình API"));
  const html = renderToString(tree("http://127.0.0.1:8000"));
  assert.match(html, /Đang tải điều hướng phiên/);
  assert.equal(sessionReads, 0);
  assert.equal(urlReads, 1);
  suspended = false;
});

test("resolved session pathname marks exactly its own session active", () => {
  suspended = false;
  for (const session of sessions) {
    pathname = `/chat/${session.session_id}`;
    const html = renderToStaticMarkup(tree("http://127.0.0.1:8000"));
    assert.equal((html.match(/aria-current="page"/g) ?? []).length, 1);
    assert.match(html, new RegExp(`href="/chat/${session.session_id}" aria-current="page"`));
    assert.match(html, /Session A/); assert.match(html, /Session B/);
    assert(!html.includes("Đang tải điều hướng phiên"));
  }
});

test("documents and unmatched session routes keep session links without a false active item", () => {
  for (const path of ["/documents", "/chat/33333333-3333-4333-8333-333333333333"]) {
    pathname = path;
    const html = renderToStaticMarkup(tree("http://127.0.0.1:8000"));
    assert(!html.includes("aria-current="));
    assert.match(html, /Session A/); assert.match(html, /Session B/);
  }
});

test("unconfigured branch never reads pathname or starts session hooks", () => {
  sessionReads = 0; urlReads = 0; suspended = true;
  const html = renderToStaticMarkup(tree(null));
  assert.match(html, /Chưa cấu hình API/);
  assert.equal(sessionReads, 0); assert.equal(urlReads, 0);
  suspended = false;
});
