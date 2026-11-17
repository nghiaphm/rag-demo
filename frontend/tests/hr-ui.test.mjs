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
  const file = fs.existsSync(`${base}.tsx`) ? `${base}.tsx` : `${base}.ts`;
  const exports = {};
  cache.set(relative, exports);
  const output = ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  new Function("exports", "require", output)(exports, specifier => {
    if (specifier === "next/navigation") {
      return { usePathname: () => "/hr", useRouter: () => ({ push() {}, replace() {} }) };
    }
    if (specifier === "next/link") {
      return { default: ({ href, children, ...props }) => React.createElement("a", { href, ...props }, children) };
    }
    if (specifier === "@/hooks/use-documents") {
      return {
        useDocuments: () => ({
          state: {
            status: "ready",
            items: [
              {
                document_id: "11111111-1111-4111-8111-111111111111",
                file_name: "chinh-sach-nghi-phep.pdf",
                status: "INDEXED",
                active_version_id: "22222222-2222-4222-8222-222222222222",
                chunk_count: 10,
                version_count: 1,
                cleanup_pending: false,
                created_at: "2026-11-01T00:00:00Z",
                updated_at: "2026-11-01T00:00:00Z",
              },
              {
                document_id: "33333333-3333-4333-8333-333333333333",
                file_name: "quy-trinh-onboarding.md",
                status: "INDEXED",
                active_version_id: "44444444-4444-4444-8444-444444444444",
                chunk_count: 6,
                version_count: 1,
                cleanup_pending: false,
                created_at: "2026-11-01T00:00:00Z",
                updated_at: "2026-11-01T00:00:00Z",
              },
            ],
            includeDeleted: false,
            nextOffset: 2,
            hasMore: false,
            error: null,
            selectedId: null,
            detailStatus: "idle",
            detail: null,
            detailError: null,
          },
          controller: {
            reload() {},
            refresh() {},
            loadMore() {},
            select() {},
          },
        }),
      };
    }
    return specifier.startsWith("@/") ? load(specifier.slice(2)) : require(specifier);
  });
  return exports;
}

const { HrChatbotProvider } = load("components/hr/layout/hr-chatbot-provider");
const { HrDashboardView } = load("components/hr/dashboard/hr-dashboard-view");
const { HrDocumentsView } = load("components/hr/documents/hr-documents-view");
const { HrGuideView } = load("components/hr/guide/hr-guide-view");
const { HrChatbotWidget } = load("components/hr/chatbot/hr-chatbot-widget");

test("HrDashboardView renders KPIs, department chart, contract chart, and live RAG summary", () => {
  const html = renderToStaticMarkup(
    React.createElement(
      HrChatbotProvider,
      null,
      React.createElement(HrDashboardView, { apiBaseUrl: "http://127.0.0.1:8000" })
    )
  );
  assert.match(html, /Dashboard &amp; Analytics nhân sự/);
  assert.match(html, /Tổng nhân sự/);
  assert.match(html, /184/);
  assert.match(html, /Kỹ thuật &amp; Sản phẩm/);
  assert.match(html, /Trạng thái nhân viên &amp; hợp đồng/);
  assert.match(html, /Kho tri thức RAG \(Dữ liệu thực từ API\)/);
  assert.match(html, /16/); // 10 + 6 totalChunks
});

test("HrDocumentsView renders category tabs, shared-KB disclosure, and HR documents list", () => {
  const html = renderToStaticMarkup(
    React.createElement(
      HrChatbotProvider,
      null,
      React.createElement(HrDocumentsView, { apiBaseUrl: "http://127.0.0.1:8000" })
    )
  );
  assert.match(html, /HR Documents/);
  assert.match(html, /Tất cả \(2\)/);
  assert.match(html, /Chính sách \(1\)/);
  assert.match(html, /Quy trình \(1\)/);
  assert.match(html, /chinh-sach-nghi-phep\.pdf/);
  assert.match(html, /quy-trinh-onboarding\.md/);
  assert.match(html, /dùng chung với/);
});

test("HrGuideView renders 4 guide sections and clickable prompt templates", () => {
  const html = renderToStaticMarkup(
    React.createElement(
      HrChatbotProvider,
      null,
      React.createElement(HrGuideView)
    )
  );
  assert.match(html, /Hướng dẫn sử dụng HR Portal/);
  assert.match(html, /Chính sách nghỉ phép năm/);
  assert.match(html, /Thử câu hỏi này/);
});

test("HrChatbotWidget renders accessible floating launcher in both configured and unconfigured states", () => {
  for (const apiBaseUrl of [null, "http://127.0.0.1:8000"]) {
    const html = renderToStaticMarkup(
      React.createElement(
        HrChatbotProvider,
        null,
        React.createElement(HrChatbotWidget, { apiBaseUrl })
      )
    );
    assert.match(html, /aria-label="Mở Trợ lý HR"/);
    assert.match(html, /Trợ lý HR/);
  }
});
