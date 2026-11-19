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
    if (specifier === "@/hooks/use-sessions") {
      return {
        useSessions: (_apiBaseUrl, surface = "workspace") => ({
          status: "ready",
          sessions: [
            {
              session_id: "55555555-5555-4555-8555-555555555555",
              title: `Hội thoại (${surface}): Nghỉ phép năm`,
              surface,
              scope: { mode: "ALL_ACTIVE", document_ids: [] },
              user_id: null,
              created_at: "2026-11-18T00:00:00Z",
              updated_at: "2026-11-18T00:00:00Z",
            },
          ],
          total: 1,
          isCreating: false,
          error: null,
          isMutating: false,
          mutationError: null,
          reload() {},
          loadMore() {},
          createNew() {},
          rename() {},
          remove() {},
        }),
      };
    }
    return specifier.startsWith("@/") ? load(specifier.slice(2)) : require(specifier);
  });
  return exports;
}

const { HrChatbotProvider } = load("components/hr/layout/hr-chatbot-provider");
const { HrTourProvider } = load("components/hr/tour/hr-tour-provider");
const { HrTourOverlay } = load("components/hr/tour/hr-tour-overlay");
const { HrDashboardView } = load("components/hr/dashboard/hr-dashboard-view");
const { HrDocumentsView } = load("components/hr/documents/hr-documents-view");
const { HrGuideView } = load("components/hr/guide/hr-guide-view");
const { HrChatbotHistory } = load("components/hr/chatbot/hr-chatbot-history");
const { HrChatbotWidget } = load("components/hr/chatbot/hr-chatbot-widget");
const { ChatComposer } = load("components/chat/chat-composer");
const { ChatMessage } = load("components/chat/chat-message");
const { getHrRouteDisplayTitle, isSafeHrRoute, rehypeHrRouteLinks } = load("lib/hr/page-context");

test("HrDashboardView renders KPIs, charts, live RAG summary, User Guide link, and Product Tour anchors", () => {
  const html = renderToStaticMarkup(
    React.createElement(
      HrChatbotProvider,
      null,
      React.createElement(
        HrTourProvider,
        null,
        React.createElement(HrDashboardView, { apiBaseUrl: "http://127.0.0.1:8000" })
      )
    )
  );
  assert.match(html, /Dashboard &amp; Analytics nhân sự/);
  assert.match(html, /href="\/hr\/guide"/);
  assert.match(html, /Product Tour/);
  assert.match(html, /data-tour="hr-kpi-strip"/);
  assert.match(html, /data-tour="hr-analytics-charts"/);
  assert.match(html, /data-tour="hr-live-kb"/);
  assert.match(html, /Tổng nhân sự/);
  assert.match(html, /184/);
  assert.match(html, /Kỹ thuật &amp; Sản phẩm/);
  assert.match(html, /Trạng thái nhân viên &amp; hợp đồng/);
  assert.match(html, /Kho tri thức RAG \(Dữ liệu thực từ API\)/);
  assert.match(html, /16/); // 10 + 6 totalChunks
});

test("HrDocumentsView renders category tabs, shared-KB disclosure, HR documents list, and tour anchors", () => {
  const html = renderToStaticMarkup(
    React.createElement(
      HrChatbotProvider,
      null,
      React.createElement(
        HrTourProvider,
        null,
        React.createElement(HrDocumentsView, { apiBaseUrl: "http://127.0.0.1:8000" })
      )
    )
  );
  assert.match(html, /HR Documents/);
  assert.match(html, /data-tour="hr-docs-filters"/);
  assert.match(html, /data-tour="hr-docs-workbench"/);
  assert.match(html, /Tất cả \(2\)/);
  assert.match(html, /Chính sách \(1\)/);
  assert.match(html, /Quy trình \(1\)/);
  assert.match(html, /chinh-sach-nghi-phep\.pdf/);
  assert.match(html, /quy-trinh-onboarding\.md/);
  assert.match(html, /dùng chung với/);
});

test("HrGuideView renders 4 guide sections, prompt templates, and scoped Product Tour launchers", () => {
  const html = renderToStaticMarkup(
    React.createElement(
      HrChatbotProvider,
      null,
      React.createElement(
        HrTourProvider,
        null,
        React.createElement(HrGuideView)
      )
    )
  );
  assert.match(html, /Hướng dẫn sử dụng HR Portal/);
  assert.match(html, /Chính sách nghỉ phép năm/);
  assert.match(html, /Thử câu hỏi này/);
  assert.match(html, /Tour Dashboard/);
  assert.match(html, /Tour Tài liệu/);
  assert.match(html, /Tour Trợ lý HR/);
});

test("HrTourOverlay stays empty during SSR without hydration mismatch", () => {
  const html = renderToStaticMarkup(
    React.createElement(
      HrChatbotProvider,
      null,
      React.createElement(
        HrTourProvider,
        null,
        React.createElement(HrTourOverlay)
      )
    )
  );
  assert.equal(html, "");
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

test("ChatMessage supports optional renderAssistantActions for HR navigation buttons without altering default Workspace rendering", () => {
  const sampleMessage = {
    key: "a1",
    messageId: "m1",
    requestId: "r1",
    role: "assistant",
    content: "Bạn có thể chuyển sang `/hr/documents` để tải tài liệu.",
    status: "COMPLETED",
    model: "openai/gpt-oss-120b",
    sources: [],
    citations: [],
    usage: null,
    error: null,
  };

  const defaultHtml = renderToStaticMarkup(React.createElement(ChatMessage, { message: sampleMessage }));
  assert.doesNotMatch(defaultHtml, /Đi tới trang liên quan/);

  const hrHtml = renderToStaticMarkup(
    React.createElement(ChatMessage, {
      message: sampleMessage,
      renderAssistantActions: () => React.createElement("a", { href: "/hr/documents" }, "Đi tới trang liên quan"),
    })
  );
  assert.match(hrHtml, /href="\/hr\/documents"/);
  assert.match(hrHtml, /Đi tới trang liên quan/);
});

test("HrChatbotHistory renders HR-filtered session history, active state, and New Chat action", () => {
  const html = renderToStaticMarkup(
    React.createElement(HrChatbotHistory, {
      apiBaseUrl: "http://127.0.0.1:8000",
      activeSessionId: "55555555-5555-4555-8555-555555555555",
      onNewChat() {},
      onSelectSession() {},
      onActiveSessionDeleted() {},
    })
  );
  assert.match(html, /Lịch sử hội thoại HR/);
  assert.match(html, /Cuộc trò chuyện mới/);
  assert.match(html, /Hội thoại \(hr\): Nghỉ phép năm/);
  assert.match(html, /Đang mở/);
  assert.match(html, /Thao tác với phiên/);
});

test("ChatComposer supports HR attachment upload button without altering default /documents link", () => {
  const hrHtml = renderToStaticMarkup(
    React.createElement(ChatComposer, {
      apiBaseUrl: "http://127.0.0.1:8000",
      value: "",
      showAttachments: true,
      documentsHref: "/hr/documents",
      onChange() {},
      onSubmit() {},
      onStop() {},
    })
  );
  assert.match(hrHtml, /aria-label="Thêm tệp đính kèm"/);
  assert.match(hrHtml, /aria-label="Chọn tệp đính kèm"/);
});

test("ChatMessage renders inline whitelisted HR routes as in-tab Next links without target=_blank", () => {
  const sampleMessage = {
    key: "a-inline",
    messageId: "m-inline",
    requestId: "r-inline",
    role: "assistant",
    content: "Truy cập URL: /hr/documents hoặc xem [Tổng quan nhân sự](/hr) và [External](https://example.test).",
    status: "COMPLETED",
    model: "openai/gpt-oss-120b",
    sources: [],
    citations: [],
    usage: null,
    error: null,
  };

  const html = renderToStaticMarkup(
    React.createElement(ChatMessage, {
      message: sampleMessage,
      extraRehypePlugins: [rehypeHrRouteLinks],
      renderInternalLink: (href, children) =>
        isSafeHrRoute(href)
          ? React.createElement(
              "a",
              { href, "data-hr-inline-link": "true" },
              typeof children === "string" && isSafeHrRoute(children.trim())
                ? getHrRouteDisplayTitle(href)
                : children
            )
          : null,
    })
  );

  assert.match(html, /href="\/hr\/documents" data-hr-inline-link="true">Tài liệu nhân sự<\/a>/);
  assert.match(html, /href="\/hr" data-hr-inline-link="true">Tổng quan nhân sự<\/a>/);
  assert.match(html, /href="https:\/\/example\.test"[^>]*target="_blank"/);
  assert.doesNotMatch(html, /href="\/hr\/documents"[^>]*target="_blank"/);
});
