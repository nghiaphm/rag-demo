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
let currentPathname = "/hr";

function load(relative) {
  if (cache.has(relative)) return cache.get(relative);
  const base = fileURLToPath(new URL(`../${relative}`, import.meta.url));
  const file = fs.existsSync(`${base}.tsx`) ? `${base}.tsx` : `${base}.ts`;
  const exports = {};
  cache.set(relative, exports);
  const output = ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  new Function("exports", "require", output)(exports, specifier => {
    if (specifier === "next/navigation") {
      return { usePathname: () => currentPathname, useRouter: () => ({ push() {}, replace() {} }) };
    }
    if (specifier === "next/link") {
      return {
        default: ({ href, children, ...props }) => React.createElement("a", { href, ...props }, children),
      };
    }
    if (specifier === "@/components/layout/service-health") {
      return { ServiceHealth: () => React.createElement("span", { "data-service-health": true }, "OK") };
    }
    if (specifier === "@/components/layout/session-navigation") {
      return { SessionNavigation: () => React.createElement("div", { "data-sessions": true }) };
    }
    return specifier.startsWith("@/") ? load(specifier.slice(2)) : require(specifier);
  });
  return exports;
}

const { HrChatbotProvider, useHrChatbot } = load("components/hr/layout/hr-chatbot-provider");
const { HrTourProvider, useHrTour } = load("components/hr/tour/hr-tour-provider");
const { HrShell, matchesHrRoute } = load("components/hr/layout/hr-shell");
const { getHrRouteTitle } = load("components/hr/layout/hr-header-user");
const { AppShell } = load("components/layout/app-shell");

test("matchesHrRoute and getHrRouteTitle highlight active HR routes cleanly", () => {
  assert.equal(matchesHrRoute("/hr", "/hr", true), true);
  assert.equal(matchesHrRoute("/hr/documents", "/hr", true), false);
  assert.equal(matchesHrRoute("/hr/documents", "/hr/documents"), true);
  assert.equal(matchesHrRoute("/hr/guide", "/hr/guide"), true);

  assert.equal(getHrRouteTitle("/hr"), "Tổng quan nhân sự");
  assert.equal(getHrRouteTitle("/hr/documents"), "Tài liệu nhân sự");
  assert.equal(getHrRouteTitle("/hr/guide"), "Hướng dẫn sử dụng");
});

test("HrShell renders HR navigation including /hr/guide, Product Tour trigger, header demo user, and Workspace link", () => {
  currentPathname = "/hr/documents";
  const html = renderToStaticMarkup(
    React.createElement(
      HrChatbotProvider,
      null,
      React.createElement(
        HrTourProvider,
        null,
        React.createElement(
          HrShell,
          { apiBaseUrl: null },
          React.createElement("div", null, "HR Documents Content")
        )
      )
    )
  );
  assert.match(html, /HR Portal/);
  assert.match(html, /href="\/hr"/);
  assert.match(html, /href="\/hr\/documents"[^>]*aria-current="page"/);
  assert.match(html, /href="\/hr\/guide"/);
  assert.match(html, /Product Tour/);
  assert.doesNotMatch(html, /href="\/hr"[^>]*aria-current="page"/);
  assert.match(html, /Minh Anh/);
  assert.match(html, /Phòng Nhân sự/);
  assert.match(html, /Demo/);
  assert.match(html, /href="\/chat"/);
  assert.match(html, /HR Documents Content/);
});

test("AppShell keeps RAG Workspace primary routes and adds HR Demo Portal link", () => {
  currentPathname = "/chat";
  const html = renderToStaticMarkup(
    React.createElement(AppShell, { apiBaseUrl: null }, React.createElement("div", null, "Workspace Main"))
  );
  assert.match(html, /RAG Workspace/);
  assert.match(html, /href="\/chat"[^>]*aria-current="page"/);
  assert.match(html, /href="\/documents"/);
  assert.match(html, /href="\/hr"/);
  assert.match(html, /HR Demo Portal/);
  assert.match(html, /Workspace Main/);
});

test("useHrChatbot and useHrTour throw outside their providers", () => {
  function OrphanChatbot() {
    useHrChatbot();
    return null;
  }
  function OrphanTour() {
    useHrTour();
    return null;
  }
  assert.throws(
    () => renderToStaticMarkup(React.createElement(OrphanChatbot)),
    /HrChatbotProvider/
  );
  assert.throws(
    () => renderToStaticMarkup(React.createElement(OrphanTour)),
    /HrTourProvider/
  );
});
