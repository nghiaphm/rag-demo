import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const require = createRequire(import.meta.url), cache = new Map();
const session = { session_id: "11111111-1111-4111-8111-111111111111", title: "Session A" };
let proposal = null, capturedDialog, pathname = "/documents";
const replacements = [];
function load(relative) {
  if (cache.has(relative)) return cache.get(relative);
  const base = fileURLToPath(new URL(`../${relative}`, import.meta.url));
  const file = fs.existsSync(`${base}.tsx`) ? `${base}.tsx` : `${base}.ts`;
  const exports = {};
  cache.set(relative, exports);
  const source = ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  new Function("exports", "require", source)(exports, name => {
    if (name === "react" && relative === "components/layout/session-navigation") return { ...React, useState: () => [proposal, () => {}] };
    if (name === "next/navigation") return { usePathname: () => pathname, useRouter: () => ({ push() {}, replace: path => replacements.push(path) }) };
    if (name === "next/link") return { default: ({ href, children, ...props }) => React.createElement("a", { href, ...props }, children) };
    if (name === "@/hooks/use-sessions") return { useSessions: () => ({ sessions: [session], total: 60, status: "ready", isCreating: false,
      isMutating: false, mutationError: null, error: null, reload() {}, createNew() {}, loadMore() {}, rename() {}, remove() {} }) };
    if (name === "@/components/layout/session-actions" && relative === "components/layout/session-navigation") {
      return { ...load("components/layout/session-actions"), SessionActionDialog: props => { capturedDialog = props; return null; } };
    }
    return name.startsWith("@/") ? load(name.slice(2)) : require(name);
  });
  return exports;
}
const { SessionNavigation } = load("components/layout/session-navigation");
const { SidebarProvider } = load("components/ui/sidebar");
function render() { return renderToStaticMarkup(React.createElement(SidebarProvider, null, React.createElement(SessionNavigation, { apiBaseUrl: "http://127.0.0.1:8000" }))); }

test("assembled sidebar has named menu trigger and refresh/pagination controls outside session links", () => {
  const html = render();
  assert.match(html, /aria-label="Thao tác với phiên Session A"/);
  assert.match(html, /aria-haspopup="menu"/);
  assert.match(html, /Làm mới phiên/); assert.match(html, /Tải thêm phiên/);
  for (const anchor of html.match(/<a\b[^>]*>[\s\S]*?<\/a>/g) ?? []) assert(!anchor.includes("<button"));
});

test("confirmed current-session deletion navigates to chat; deleting another session keeps current route", () => {
  proposal = { session, action: "delete", opener: null };
  for (const path of [`/chat/${session.session_id}`, "/documents", "/chat/22222222-2222-4222-8222-222222222222"]) {
    pathname = path; replacements.length = 0; render();
    capturedDialog.onDeleted({ session_id: session.session_id });
    assert.deepEqual(replacements, path === `/chat/${session.session_id}` ? ["/chat"] : []);
  }
  proposal = null;
});
