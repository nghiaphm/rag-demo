import assert from "node:assert/strict";
import fs from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const cache = new Map();
function load(relative) {
  if (cache.has(relative)) return cache.get(relative);
  const exports = {};
  cache.set(relative, exports);
  const file = fileURLToPath(new URL(`../${relative}.ts`, import.meta.url));
  const output = ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  new Function("exports", "require", output)(exports, specifier => load(specifier.slice(2)));
  return exports;
}

const { HR_ANALYTICS_FIXTURE } = load("fixtures/hr-analytics");
const { HR_GUIDE_SECTIONS, HR_PROMPT_TEMPLATES } = load("fixtures/hr-guide");
const { HR_PRODUCT_TOUR_STEPS, getHrTourSteps } = load("fixtures/hr-tour");
const {
  readTourCompletionState,
  writeTourCompletionState,
  shouldAutoPromptHrTour,
  getTourProgressLabel,
  getNextTourStepIndex,
  getPrevTourStepIndex,
  computeSpotlightFrame,
  computePopoverPosition,
} = load("lib/hr/tour");
const {
  summarizeDepartmentShares,
  summarizeContractStatuses,
  summarizeKnowledgeBaseDocuments,
} = load("lib/hr/analytics");
const {
  classifyHrDocument,
  countDocumentsByCategory,
  filterHrDocuments,
} = load("lib/hr/document-categories");
const {
  ALLOWED_HR_ROUTES,
  HR_ROUTE_MANIFEST,
  buildHrDashboardSnapshot,
  buildHrUiContext,
  collectVisibleHrDomFeatures,
  deriveRelatedHrPages,
  extractHrNavigationSuggestions,
  isSafeHrRoute,
  rehypeHrRouteLinks,
  resolveHrRouteFromPathname,
} = load("lib/hr/page-context");
const { ChatController } = load("lib/chat/controller");

test("HR analytics helpers summarize department shares, contracts, and real DocumentInfo stats", () => {
  const deptShares = summarizeDepartmentShares(HR_ANALYTICS_FIXTURE.departments);
  assert.equal(deptShares.length, 6);
  assert.equal(deptShares[0].barWidthPercent, 100);
  const totalDept = deptShares.reduce((sum, item) => sum + item.count, 0);
  assert.equal(totalDept, HR_ANALYTICS_FIXTURE.totalEmployees);

  const contractShares = summarizeContractStatuses(HR_ANALYTICS_FIXTURE.contractStatuses);
  const totalContracts = contractShares.reduce((sum, item) => sum + item.count, 0);
  assert.equal(totalContracts, HR_ANALYTICS_FIXTURE.totalEmployees);

  const kb = summarizeKnowledgeBaseDocuments([
    {
      document_id: "1",
      file_name: "chinh-sach-nghi-phep.pdf",
      status: "INDEXED",
      chunk_count: 14,
      version_count: 1,
      cleanup_pending: false,
      created_at: "2026-11-01T00:00:00Z",
      updated_at: "2026-11-01T00:00:00Z",
    },
    {
      document_id: "2",
      file_name: "quy-trinh-onboarding.md",
      status: "PROCESSING",
      chunk_count: 0,
      version_count: 1,
      cleanup_pending: false,
      created_at: "2026-11-01T00:00:00Z",
      updated_at: "2026-11-01T00:00:00Z",
    },
    {
      document_id: "3",
      file_name: "corrupt.pdf",
      status: "FAILED",
      chunk_count: 0,
      version_count: 1,
      cleanup_pending: false,
      created_at: "2026-11-01T00:00:00Z",
      updated_at: "2026-11-01T00:00:00Z",
    },
  ]);
  assert.deepEqual(kb, {
    totalDocuments: 3,
    indexedDocuments: 1,
    processingDocuments: 1,
    failedDocuments: 1,
    totalChunks: 14,
  });
});

test("HR document category classifier and filters handle Vietnamese and English keywords deterministically", () => {
  assert.equal(classifyHrDocument("Chính sách nghỉ phép 2026.pdf"), "POLICY");
  assert.equal(classifyHrDocument("employee-leave-policy.md"), "POLICY");
  assert.equal(classifyHrDocument("Nội quy lao động & Bảo mật.pdf"), "REGULATION");
  assert.equal(classifyHrDocument("Quy trình Onboarding nhân viên.docx"), "PROCEDURE");
  assert.equal(classifyHrDocument("notes.txt"), "OTHER");

  const docs = [
    { document_id: "1", file_name: "Chính sách phúc lợi.pdf" },
    { document_id: "2", file_name: "Quy định bảo mật.md" },
    { document_id: "3", file_name: "Quy trình onboarding.xlsx" },
    { document_id: "4", file_name: "misc.txt" },
  ];
  assert.deepEqual(countDocumentsByCategory(docs), {
    ALL: 4,
    POLICY: 1,
    REGULATION: 1,
    PROCEDURE: 1,
    OTHER: 1,
  });

  assert.equal(filterHrDocuments(docs, { category: "POLICY" }).length, 1);
  assert.equal(filterHrDocuments(docs, { category: "ALL", query: "bao mat" }).length, 1);
  assert.equal(filterHrDocuments(docs, { category: "PROCEDURE", query: "khong-ton-tai" }).length, 0);
});

test("HR guide fixtures provide 4 structured guide sections and prompt templates", () => {
  assert.equal(HR_GUIDE_SECTIONS.length, 4);
  assert(HR_PROMPT_TEMPLATES.length >= 6);
  for (const item of HR_PROMPT_TEMPLATES) {
    assert.ok(item.prompt.length > 10);
  }
});

test("HR product tour fixtures support full cross-route and scoped module tours", () => {
  assert.equal(HR_PRODUCT_TOUR_STEPS.length, 6);
  assert.equal(getHrTourSteps("all").length, 6);
  assert.equal(getHrTourSteps("dashboard").length, 3);
  assert.equal(getHrTourSteps("documents").length, 2);
  assert.equal(getHrTourSteps("copilot").length, 1);
  assert.equal(getHrTourSteps("copilot")[0].opensChatbot, true);

  const store = new Map();
  const fakeStorage = {
    getItem: (key) => store.get(key) ?? null,
    setItem: (key, value) => store.set(key, value),
  };
  assert.equal(readTourCompletionState(fakeStorage), null);
  assert.equal(shouldAutoPromptHrTour("/hr", null), true);
  assert.equal(shouldAutoPromptHrTour("/hr/guide", null), false);

  writeTourCompletionState(fakeStorage, "completed");
  assert.equal(readTourCompletionState(fakeStorage), "completed");
  assert.equal(shouldAutoPromptHrTour("/hr", "completed"), false);

  assert.equal(getTourProgressLabel(0, HR_PRODUCT_TOUR_STEPS), "Bước 1 / 6");
  assert.equal(getNextTourStepIndex(0, 6), 1);
  assert.equal(getNextTourStepIndex(5, 6), null);
  assert.equal(getPrevTourStepIndex(0), null);
  assert.equal(getPrevTourStepIndex(2), 1);

  assert.deepEqual(
    computeSpotlightFrame({ top: 100, left: 200, width: 400, height: 120 }, { width: 1280, height: 800 }, 8),
    { top: 92, left: 192, width: 416, height: 136 },
  );

  const flipped = computePopoverPosition(
    { top: 680, left: 400, width: 300, height: 90 },
    { width: 1280, height: 800 },
    { width: 360, height: 240 },
    "bottom",
  );
  assert.equal(flipped.placement, "top");
});

test("HR page context registry covers /hr, /hr/documents, /hr/guide and builds accurate ChatUiContext", () => {
  assert.deepEqual([...ALLOWED_HR_ROUTES], ["/hr", "/hr/documents", "/hr/guide"]);
  assert.equal(resolveHrRouteFromPathname("/hr"), "/hr");
  assert.equal(resolveHrRouteFromPathname("/hr/documents"), "/hr/documents");
  assert.equal(resolveHrRouteFromPathname("/hr/guide"), "/hr/guide");

  const dashCtx = buildHrUiContext({ route: "/hr", title: "Tổng quan nhân sự" }, "/hr");
  assert.equal(dashCtx.route, "/hr");
  assert.equal(dashCtx.portal, "hr");
  assert.ok(dashCtx.available_features.length >= 3);
  assert.deepEqual(
    dashCtx.related_pages.map((p) => p.route),
    ["/hr/documents", "/hr/guide"],
  );

  const docsCtx = buildHrUiContext(
    {
      route: "/hr/documents",
      title: "Tài liệu nhân sự",
      selectedDocumentId: "doc-1",
      selectedDocumentName: "chinh-sach-nghi-phep.pdf",
      selectedCategory: "POLICY",
    },
    "/hr/documents",
  );
  assert.equal(docsCtx.route, "/hr/documents");
  assert.equal(docsCtx.selected_document_name, "chinh-sach-nghi-phep.pdf");
  assert.equal(docsCtx.selected_category, "Chính sách");
  assert.deepEqual(
    docsCtx.related_pages.map((p) => p.route),
    ["/hr", "/hr/guide"],
  );

  const guideCtx = buildHrUiContext({ route: "/hr/guide", title: "Hướng dẫn sử dụng" }, "/hr/guide");
  assert.equal(guideCtx.route, "/hr/guide");
  assert.deepEqual(
    guideCtx.related_pages.map((p) => p.route),
    ["/hr", "/hr/documents"],
  );

  // Verify Single Source of Truth manifest derivation & dynamic live/DOM feature introspection
  assert.deepEqual(Object.keys(HR_ROUTE_MANIFEST), [...ALLOWED_HR_ROUTES]);
  assert.deepEqual(
    deriveRelatedHrPages("/hr/documents").map((item) => item.route),
    ["/hr", "/hr/guide"],
  );
  assert.ok(dashCtx.available_features[0].includes("Tỉ lệ nghỉ việc (2.1%)"));
  assert.ok(docsCtx.available_features[0].includes("Tài liệu chung"));

  const fakeDomRoot = {
    querySelectorAll: () => [
      { getAttribute: () => "Biểu đồ thống kê phòng ban theo thời gian thực." },
      { getAttribute: () => "Biểu đồ thống kê phòng ban theo thời gian thực." },
    ],
  };
  assert.deepEqual(collectVisibleHrDomFeatures(fakeDomRoot), [
    "Biểu đồ thống kê phòng ban theo thời gian thực.",
  ]);

  const liveDocsCtx = buildHrUiContext(
    {
      route: "/hr/documents",
      searchQuery: "nghi phep",
      liveFeatures: ["Danh sách hiện đang hiển thị 1 / 4 tài liệu trong kho RAG."],
    },
    "/hr/documents",
    fakeDomRoot,
  );
  assert.equal(
    liveDocsCtx.available_features[0],
    "Danh sách hiện đang hiển thị 1 / 4 tài liệu trong kho RAG.",
  );
  assert.ok(
    liveDocsCtx.available_features.includes('Từ khóa tìm kiếm đang áp dụng trên trang: "nghi phep".'),
  );
  assert.ok(
    liveDocsCtx.available_features.includes("Biểu đồ thống kê phòng ban theo thời gian thực."),
  );
});

test("extractHrNavigationSuggestions allows only whitelisted HR routes and ignores unsafe or current URLs", () => {
  assert.equal(isSafeHrRoute("/hr/documents"), true);
  assert.equal(isSafeHrRoute("/chat"), false);
  assert.equal(isSafeHrRoute("https://evil.example/hr"), false);

  const answer = [
    "### 4. Các trang liên quan",
    "- Kho tài liệu (`/hr/documents`) để xem và tải file.",
    "- Trang hiện tại (`/hr`) không nên gợi ý lại.",
    "- Trang hướng dẫn (`/hr/guide`) để thử câu hỏi mẫu.",
    "- URL ngoài https://evil.example/hr/documents hoặc /admin hay /documents phải bị bỏ qua.",
  ].join("\n");

  const suggestions = extractHrNavigationSuggestions(answer, "/hr");
  assert.deepEqual(
    suggestions.map((item) => item.route),
    ["/hr/documents", "/hr/guide"],
  );
});

test("ChatController forwards uiContext when provided and omits it for standard RAG Workspace turns", async () => {
  const capturedPayloads = [];
  const sessionId = "11111111-1111-4111-8111-111111111111";
  const controller = new ChatController(
    {
      createSession: async () => ({ session_id: sessionId }),
      stream: async (payload, options) => {
        capturedPayloads.push(payload);
        await options?.onEvent?.({
          event: "start",
          data: {
            sequence: 1,
            request_id: "22222222-2222-4222-8222-222222222222",
            session_id: sessionId,
            user_message_id: "33333333-3333-4333-8333-333333333333",
            assistant_message_id: "44444444-4444-4444-8444-444444444444",
            mode: "PERSISTENT",
          },
        });
        await options?.onEvent?.({
          event: "delta",
          data: { sequence: 2, content: "Hướng dẫn chi tiết." },
        });
        await options?.onEvent?.({
          event: "done",
          data: { sequence: 3, status: "COMPLETED", usage: null },
        });
        return {
          events: [],
          start: {
            event: "start",
            data: {
              sequence: 1,
              request_id: "22222222-2222-4222-8222-222222222222",
              session_id: sessionId,
              user_message_id: "33333333-3333-4333-8333-333333333333",
              assistant_message_id: "44444444-4444-4444-8444-444444444444",
              mode: "PERSISTENT",
            },
          },
          metadata: null,
          citations: [],
          deltas: [],
          terminal: { event: "done", data: { sequence: 3, status: "COMPLETED", usage: null } },
          answer: "Hướng dẫn chi tiết.",
          usage: null,
        };
      },
    },
    sessionId,
  );

  await controller.submit("Chính sách nghỉ phép năm?");
  assert.equal("ui_context" in capturedPayloads[0], false);

  const uiContext = buildHrUiContext({ route: "/hr/guide", title: "Hướng dẫn sử dụng" }, "/hr/guide");
  await controller.submit("Hướng dẫn thao tác trang hiện tại", [], { uiContext });
  assert.equal(capturedPayloads[1].question, "Hướng dẫn thao tác trang hiện tại");
  assert.equal(capturedPayloads[1].ui_context.route, "/hr/guide");
});

test("rehypeHrRouteLinks converts whitelisted HR routes in text and inline code while preserving pre/external URLs", () => {
  const tree = {
    type: "root",
    children: [
      {
        type: "element",
        tagName: "p",
        properties: {},
        children: [
          { type: "text", value: "Truy cập /hr/documents hoặc " },
          { type: "element", tagName: "code", properties: {}, children: [{ type: "text", value: "/hr/guide" }] },
          { type: "text", value: " hoặc https://evil.example/hr và /documents." },
        ],
      },
      {
        type: "element",
        tagName: "pre",
        properties: {},
        children: [
          { type: "element", tagName: "code", properties: {}, children: [{ type: "text", value: "/hr/documents" }] },
        ],
      },
    ],
  };

  rehypeHrRouteLinks()(tree);
  const pChildren = tree.children[0].children;
  const links = pChildren.filter((n) => n.type === "element" && n.tagName === "a");
  assert.deepEqual(
    links.map((n) => [n.properties.href, n.children[0].value]),
    [
      ["/hr/documents", "Tài liệu nhân sự"],
      ["/hr/guide", "Hướng dẫn sử dụng"],
    ],
  );
  assert.equal(tree.children[1].children[0].tagName, "code");
});

test("buildHrDashboardSnapshot and buildHrUiContext attach structured HR Dashboard metrics across all HR routes", () => {
  const withLiveKb = buildHrDashboardSnapshot(HR_ANALYTICS_FIXTURE, {
    totalDocuments: 5,
    indexedDocuments: 4,
    processingDocuments: 1,
    failedDocuments: 0,
    totalChunks: 72,
  });
  assert.equal(withLiveKb.total_employees, HR_ANALYTICS_FIXTURE.totalEmployees);
  assert.equal(withLiveKb.kpis.length, 4);
  assert.equal(withLiveKb.departments.length, 6);
  assert.equal(withLiveKb.contract_statuses.length, 4);
  assert.deepEqual(withLiveKb.knowledge_base, {
    total_documents: 5,
    indexed_documents: 4,
    processing_documents: 1,
    failed_documents: 0,
    total_chunks: 72,
  });

  // On /hr with live dashboardSnapshot passed via useHrPageContext
  const dashboardCtx = buildHrUiContext(
    { route: "/hr", dashboardSnapshot: withLiveKb },
    "/hr",
  );
  assert.deepEqual(dashboardCtx.dashboard_snapshot, withLiveKb);

  // Even on /hr/documents or /hr/guide, HR Dashboard metrics remain attached so users can ask to analyze HR Dashboard anytime
  const docsCtx = buildHrUiContext({ route: "/hr/documents" }, "/hr/documents");
  assert.equal(docsCtx.dashboard_snapshot.total_employees, HR_ANALYTICS_FIXTURE.totalEmployees);
  assert.equal(docsCtx.dashboard_snapshot.departments[0].department, "Kỹ thuật & Sản phẩm");
  assert.equal(docsCtx.dashboard_snapshot.departments[0].count, 68);
});
