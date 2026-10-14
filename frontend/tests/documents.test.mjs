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
const { listDocuments, getDocument } = load("lib/api/documents");
const { createApiClient } = load("lib/api/client");
const { DocumentsController } = load("lib/documents/controller");
const { DocumentsDataView, DocumentDetailPanel, DocumentsPreview } = load("components/documents/documents-preview");
const id = n => `${n.toString(16).padStart(8, "0")}-1111-4111-8111-111111111111`;
const document = (n, overrides = {}) => ({ document_id: id(n), file_name: `guide-${n}.pdf`, status: "INDEXED",
  active_version_id: id(100 + n), chunk_count: 3, version_count: 1, cleanup_pending: false,
  created_at: "2026-10-14T00:00:00Z", updated_at: "2026-10-14T01:00:00Z", deleted_at: null, ...overrides });
const detail = (n, overrides = {}) => ({ ...document(n), versions: [{ version_id: id(100 + n), version: 1,
  file_name: `guide-${n}.pdf`, status: "INDEXED", checksum_sha256: "fixture-checksum", size_bytes: 100,
  chunk_count: 3, created_at: "2026-10-14T00:00:00Z", indexed_at: "2026-10-14T00:10:00Z", embedding_model: null }], ...overrides });
const response = data => ({ status: 200, data, headers: new Headers() });
const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, props));
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
const first = document(1);
const second = document(2);

test("REST document clients use exact GET routes, offset/limit/include_deleted and plain array contract", async () => {
  const calls = [];
  const api = { request: async (route, init) => { calls.push([route, init.method]);
    return response(route.startsWith("/documents?") ? [first] : detail(1)); } };
  assert.deepEqual(await listDocuments(api), [first]);
  await listDocuments(api, { offset: 20, limit: 20, include_deleted: true });
  assert.equal((await getDocument(api, id(1))).active_version_id, id(101));
  assert.deepEqual(calls, [["/documents?offset=0&limit=100&include_deleted=false", "GET"],
    ["/documents?offset=20&limit=20&include_deleted=true", "GET"], [`/documents/${id(1)}`, "GET"]]);
});

test("query and ID validation stop invalid requests and reject envelope/malformed/scope responses", async () => {
  const noRequest = { request: () => assert.fail("invalid input must not fetch") };
  for (const query of [{ offset: -1 }, { limit: 0 }, { limit: 501 }, { include_deleted: "false" }]) {
    await assert.rejects(listDocuments(noRequest, query), TypeError);
  }
  await assert.rejects(getDocument(noRequest, "invented"), TypeError);
  for (const data of [{ items: [first], total: 1 }, [{ ...first, status: "UNKNOWN" }], [{ ...first, updated_at: "invalid" }],
    [first, first], [document(1, { status: "DELETED" })]]) {
    await assert.rejects(listDocuments({ request: async () => response(data) }), TypeError);
  }
  const deleted = document(1, { status: "DELETED" });
  assert.deepEqual(await listDocuments({ request: async () => response([deleted]) }, { include_deleted: true }), [deleted]);
  for (const data of [detail(2), { ...detail(1), versions: null }, { ...detail(1), versions: [{ ...detail(1).versions[0], size_bytes: -1 }] }]) {
    await assert.rejects(getDocument({ request: async () => response(data) }, id(1)), TypeError);
  }
});

test("nullable/optional document fields and independent PROCESSING status with old active version are accepted", async () => {
  const value = detail(1, { status: "PROCESSING" });
  delete value.deleted_at;
  delete value.versions[0].indexed_at;
  assert.equal((await getDocument({ request: async () => response(value) }, id(1))).status, "PROCESSING");
  const noActive = document(3, { active_version_id: null });
  assert.deepEqual(await listDocuments({ request: async () => response([noActive]) }), [noActive]);
});

test("mock HTTP preserves 404/503 errors, never issues mutations or retries", async () => {
  const calls = [];
  const api = createApiClient({ baseUrl: "http://mock.invalid", fetch: async (url, init) => {
    calls.push([url, init.method]);
    return Response.json({ detail: "private server detail" }, { status: url.includes("?") ? 503 : 404 });
  } });
  await assert.rejects(listDocuments(api), error => error.status === 503 && !error.message.includes("private"));
  await assert.rejects(getDocument(api, id(1)), error => error.status === 404);
  assert.equal(calls.length, 2);
  assert(calls.every(([, method]) => method === "GET"));
});

test("pagination uses raw page length; a full last page requires one empty probe without invented total", async () => {
  const queries = [];
  const controller = new DocumentsController({ list: async query => { queries.push(query); return query.offset === 0 ? [first, second] : []; }, get: async () => detail(1) }, 2);
  await controller.reload();
  assert.equal(controller.getSnapshot().hasMore, true);
  await controller.loadMore();
  assert.equal(controller.getSnapshot().hasMore, false);
  assert.deepEqual(controller.getSnapshot().items, [first, second]);
  assert.deepEqual(queries.map(q => q.offset), [0, 2]);
  await controller.loadMore();
  assert.equal(queries.length, 2);
  assert(!("total" in controller.getSnapshot()));
});

test("filter reset aborts old response and clears selected detail/page state", async () => {
  const old = deferred();
  const signals = [];
  const controller = new DocumentsController({ list: (query, signal) => { signals.push(signal);
    return query.include_deleted ? Promise.resolve([document(3, { status: "DELETED" })]) : old.promise; }, get: async () => detail(1) }, 2);
  const pending = controller.reload();
  await controller.setIncludeDeleted(true);
  assert.equal(signals[0].aborted, true);
  old.resolve([first, second]);
  await pending;
  assert.equal(controller.getSnapshot().items[0].status, "DELETED");
  assert.equal(controller.getSnapshot().selectedId, null);
  assert.equal(controller.getSnapshot().nextOffset, 1);
});

test("load-more failure retains items; explicit retry repeats offset once and blocks duplicate loads", async () => {
  let fail = true;
  const page = deferred();
  const offsets = [];
  const controller = new DocumentsController({ list: async query => { offsets.push(query.offset);
    if (query.offset === 0) return [first];
    if (fail) throw new Error("private");
    return page.promise; }, get: async () => detail(1) }, 1);
  await controller.reload();
  await controller.loadMore();
  assert.equal(controller.getSnapshot().status, "error");
  assert.deepEqual(controller.getSnapshot().items, [first]);
  fail = false;
  const retry = controller.retry();
  await controller.loadMore();
  page.resolve([]);
  await retry;
  assert.deepEqual(offsets, [0, 1, 1]);
  assert.equal(controller.getSnapshot().status, "ready");
});

test("detail selection aborts stale requests and never shows previous document on error", async () => {
  const old = deferred();
  const controller = new DocumentsController({ list: async () => [], get: async docId => {
    if (docId === id(1)) return old.promise;
    if (docId === id(2)) return detail(2);
    throw { status: 404 };
  } });
  const pending = controller.select(id(1));
  assert.equal(controller.getSnapshot().detailStatus, "loading");
  await controller.select(id(2));
  old.resolve(detail(1));
  await pending;
  assert.equal(controller.getSnapshot().detail.document_id, id(2));
  await controller.select(id(3));
  assert.equal(controller.getSnapshot().detailStatus, "missing");
  assert.equal(controller.getSnapshot().detail, null);
});

test("list/detail errors recover on user retry and dispose blocks late updates", async () => {
  let fail = true;
  const controller = new DocumentsController({ list: async () => { if (fail) throw new Error("private"); return []; },
    get: async () => { if (fail) throw new Error("private"); return detail(1); } });
  await controller.reload();
  await controller.select(id(1));
  assert.equal(controller.getSnapshot().status, "error");
  assert.equal(controller.getSnapshot().detailStatus, "error");
  fail = false;
  await controller.retry();
  await controller.select(id(1));
  assert.equal(controller.getSnapshot().detailStatus, "ready");
  const late = deferred();
  const disposed = new DocumentsController({ list: async () => late.promise, get: async () => detail(1) });
  const pending = disposed.reload();
  disposed.dispose();
  late.resolve([first]);
  await pending;
  assert.deepEqual(disposed.getSnapshot().items, []);
});

test("UI loading/empty/error/missing config states are distinct and expose appropriate retries", () => {
  const controller = new DocumentsController({ list: async () => [], get: async () => detail(1) });
  const base = controller.getSnapshot();
  const loading = render(DocumentsDataView, { controller, state: { ...base, status: "loading", detailStatus: "loading" } });
  assert.match(loading, /Đang tải danh sách tài liệu/);
  assert.match(loading, /Đang tải chi tiết tài liệu/);
  assert(!loading.includes("Chưa có tài liệu trong"));
  assert.match(render(DocumentsDataView, { controller, state: { ...base, status: "ready" } }), /Chưa có tài liệu trong danh sách này/);
  const error = render(DocumentsDataView, { controller, state: { ...base, status: "error", error: "safe error", detailStatus: "error" } });
  assert.match(error, /Thử lại danh sách/);
  assert.match(error, /Thử lại chi tiết/);
  assert.match(render(DocumentsPreview, { apiBaseUrl: null }), /Chưa cấu hình NEXT_PUBLIC_API_BASE_URL/);
});

test("detail UI keeps status separate from old active version and shows version status plus cleanup", () => {
  const failed = render(DocumentDetailPanel, { document: detail(1, { status: "FAILED" }) });
  assert.match(failed, /Trạng thái tài liệu/);
  assert.match(failed, /Active version ID/);
  assert(failed.includes(id(101)));
  assert.match(failed, /Đang hoạt động/);
  assert.match(failed, /FAILED/);
  assert.match(failed, /Đã lập chỉ mục/);
  const deleted = render(DocumentDetailPanel, { document: detail(1, { status: "DELETED", cleanup_pending: true }) });
  assert.match(deleted, /Tài liệu đã bị xóa khỏi nguồn truy xuất/);
  assert.match(deleted, /Đang chờ dọn dữ liệu/);
  const noActive = render(DocumentDetailPanel, { document: detail(1, { active_version_id: null }) });
  assert.match(noActive, /Chưa có phiên bản hoạt động/);
  assert(!noActive.includes("Tài liệu INDEXED và có phiên bản hoạt động"));
});

test("overlapping pages fail explicitly instead of duplicating documents", async () => {
  const controller = new DocumentsController({ list: async () => [first], get: async () => detail(1) }, 1);
  await controller.reload();
  await controller.loadMore();
  assert.equal(controller.getSnapshot().status, "error");
  assert.equal(controller.getSnapshot().items.length, 1);
  assert.equal(controller.getSnapshot().nextOffset, 1);
});
