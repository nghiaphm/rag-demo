import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import { createQaMockServer } from "../scripts/qa-mock-api.mjs";

const require = createRequire(import.meta.url), cache = new Map();
let active;
// Exercise production component callbacks/hooks without a DOM renderer. This
// harness cannot verify focus, keyboard events, portals, layout, or hydration.
const hooks = {
  ...React,
  useState: initial => {
    const owner = active, index = owner.index++;
    if (!(index in owner.slots)) owner.slots[index] = typeof initial === "function" ? initial() : initial;
    return [owner.slots[index], value => { owner.slots[index] = typeof value === "function" ? value(owner.slots[index]) : value; }];
  },
  useMemo: factory => {
    const owner = active, index = owner.index++;
    if (!(index in owner.slots)) owner.slots[index] = factory();
    const value = owner.slots[index];
    if (value?.getSnapshot && (value.submit || value.run)) owner.controller = value;
    return value;
  },
  useRef: initial => {
    const owner = active, index = owner.index++;
    return owner.slots[index] ??= { current: initial };
  },
  useSyncExternalStore: (_subscribe, snapshot) => snapshot(),
  useEffect: effect => {
    const owner = active, index = owner.index++;
    if (!(index in owner.slots)) { owner.slots[index] = true; owner.effects.push(effect); }
  },
};
function load(relative) {
  if (cache.has(relative)) return cache.get(relative);
  const base = fileURLToPath(new URL(`../${relative}`, import.meta.url));
  const file = fs.existsSync(`${base}.tsx`) ? `${base}.tsx` : `${base}.ts`;
  const exports = {}; cache.set(relative, exports);
  new Function("exports", "require", ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText)(exports, name => {
    if (name === "react" && ["components/documents/document-upload", "components/documents/document-actions"].includes(relative)) return hooks;
    return name.startsWith("@/") ? load(name.slice(2)) : require(name);
  });
  return exports;
}
const { createApiClient } = load("lib/api/client");
const { listDocuments, getDocument, updateDocument, reindexDocument } = load("lib/api/documents");
const { DocumentsController } = load("lib/documents/controller");
const { DocumentsDataView, DocumentDetailPanel } = load("components/documents/documents-preview");
const { DocumentUpload, UploadFeedback } = load("components/documents/document-upload");
const { DocumentActions, DocumentActionFeedback } = load("components/documents/document-actions");
const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, props));
function find(element, predicate) {
  if (!element || typeof element !== "object") return null;
  if (predicate(element)) return element;
  for (const child of React.Children.toArray(element.props?.children)) { const match = find(child, predicate); if (match) return match; }
  return null;
}
function mounted(Component, props) {
  const owner = { index: 0, slots: [], effects: [], cleanups: [], controller: null };
  return {
    owner,
    render() {
      owner.index = 0; active = owner;
      const element = Component(typeof props === "function" ? props() : props);
      const tree = element.type(element.props);
      for (const effect of owner.effects.splice(0)) { const cleanup = effect(); if (cleanup) owner.cleanups.push(cleanup); }
      active = null; return tree;
    },
    dispose() { for (const cleanup of owner.cleanups.splice(0).reverse()) cleanup(); },
  };
}
const tick = () => new Promise(resolve => setImmediate(resolve));
async function until(predicate) {
  const deadline = Date.now() + 5000;
  while (!predicate()) { assert(Date.now() < deadline, "document UI did not settle"); await tick(); }
}
const file = name => new File(["synthetic fixture only\n"], name);
const named = (tree, label) => find(tree, e => e.props?.children === label && typeof e.props.onClick === "function");
async function fixture(run) {
  const server = createQaMockServer({ delayMs: 1, deltaMs: 0 }), calls = [];
  server.on("request", req => calls.push([req.method, req.url, req.headers["content-type"]]));
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${server.address().port}/lifecycle`, api = createApiClient({ baseUrl: base });
  const list = new DocumentsController({ list: (query, signal) => listDocuments(api, query, signal), get: (id, signal) => getDocument(api, id, signal) });
  try { await list.reload(); await run({ base, api, list, calls }); } finally {
    list.dispose(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
  }
}
function actionsFor(base, list) {
  return mounted(DocumentActions, () => {
    const panel = DocumentDetailPanel({ document: list.getSnapshot().detail, apiBaseUrl: base, reconcile: list.reconcile });
    return find(panel, e => e.type === DocumentActions).props;
  });
}
function propose(ui, label) { named(ui.render(), label).props.onClick(); return ui.render(); }
function confirm(ui) { named(ui.render(), "Xác nhận thao tác").props.onClick(); }
async function finished(ui) { await until(() => ["done", "error", "uncertain"].includes(ui.owner.controller.getSnapshot().phase)); }

test("wired upload callback reloads list after real multipart201; pending/duplicate/cancel guards do not fake progress", () => fixture(async ({ base, list, calls }) => {
  const view = DocumentsDataView({ state: list.getSnapshot(), controller: list, apiBaseUrl: base });
  const element = find(view, e => e.type === DocumentUpload);
  const ui = mounted(element.type, element.props);
  try {
    let root = ui.render(); root.props.onOpenChange(true); root = ui.render();
    const input = find(root, e => e.props?.id === "document-upload-file");
    input.props.onChange({ target: { files: [file("fixture.exe")] } });
    let form = find(ui.render(), e => e.type === "form");
    form.props.onSubmit({ preventDefault() {} }); await tick();
    assert.equal(calls.filter(([m]) => m === "POST").length, 0);
    input.props.onChange({ target: { files: [new File([], "empty.txt")] } });
    assert.equal(ui.owner.controller.getSnapshot().phase, "error");
    input.props.onChange({ target: { files: [file("qa-upload.txt")] } });
    form = find(ui.render(), e => e.type === "form");
    form.props.onSubmit({ preventDefault() {} }); form.props.onSubmit({ preventDefault() {} });
    assert.equal(ui.owner.controller.getSnapshot().phase, "submitting");
    const pending = render(UploadFeedback, { state: ui.owner.controller.getSnapshot() });
    assert(!pending.includes("%")); assert(!pending.includes("INDEXED"));
    ui.render().props.onOpenChange(false); assert.equal(ui.render().props.open, true);
    await until(() => ui.owner.controller.getSnapshot().phase === "received" && list.getSnapshot().items.some(d => d.file_name === "qa-upload.txt"));
    assert.equal(calls.filter(([m]) => m === "POST").length, 1);
    const multipart = calls.find(([m]) => m === "POST");
    assert.match(multipart[2], /^multipart\/form-data; boundary=/);
    assert.equal(list.getSnapshot().status, "ready");
    assert.match(render(UploadFeedback, { state: ui.owner.controller.getSnapshot() }), /được index và kích hoạt/);
  } finally { ui.dispose(); }
}));

test("wired version and re-index confirmations update selected detail and list using authoritative reads", () => fixture(async ({ base, api, list, calls }) => {
  const initial = list.getSnapshot().items.find(d => d.status === "INDEXED");
  await list.select(initial.document_id);
  const ui = actionsFor(base, list);
  try {
    let tree = propose(ui, "Phiên bản mới");
    tree.props.onOpenChange(false); assert.equal(ui.render().props.open, false);
    assert.equal(calls.filter(([m]) => ["PUT", "POST"].includes(m)).length, 0);
    tree = propose(ui, "Phiên bản mới");
    find(tree, e => e.props?.id === "document-version-file").props.onChange({ target: { files: [file("qa-version.txt")] } });
    confirm(ui); confirm(ui);
    assert.equal(ui.owner.controller.getSnapshot().phase, "checking");
    ui.render().props.onOpenChange(false); assert.equal(ui.render().props.open, true);
    await finished(ui);
    assert.equal(calls.filter(([m]) => m === "PUT").length, 1);
    const version = list.getSnapshot().detail;
    assert.equal(version.version_count, initial.version_count + 1);
    assert.notEqual(version.active_version_id, initial.active_version_id);
    assert.equal(list.getSnapshot().items.find(d => d.document_id === initial.document_id).active_version_id, version.active_version_id);
    assert.deepEqual(await getDocument(api, initial.document_id), version);
    propose(ui, "Re-index"); confirm(ui); await finished(ui);
    assert.equal(list.getSnapshot().detail.version_count, initial.version_count + 2);
    assert.equal(list.getSnapshot().detail.versions[0].file_name, "qa-version.txt");
    assert.notEqual(list.getSnapshot().detail.active_version_id, version.active_version_id);
    assert.equal(calls.filter(([m, p]) => m === "POST" && p.endsWith("/re-index")).length, 1);
  } finally { ui.dispose(); }
}));

test("failed version preserves old active; delete202 removes visible row, retained detail enables deliberate cleanup200", () => fixture(async ({ base, list, calls }) => {
  const initial = list.getSnapshot().items.find(d => d.status === "INDEXED");
  await list.select(initial.document_id);
  let ui = actionsFor(base, list);
  try {
    const tree = propose(ui, "Phiên bản mới");
    find(tree, e => e.props?.id === "document-version-file").props.onChange({ target: { files: [file("qa-fail.txt")] } });
    confirm(ui); await finished(ui);
    const failed = list.getSnapshot().detail;
    assert.equal(failed.active_version_id, initial.active_version_id); assert.equal(failed.status, "INDEXED");
    assert.equal(failed.versions[0].status, "FAILED");
    assert.equal(ui.owner.controller.getSnapshot().receipt, null);
    assert.match(render(DocumentActionFeedback, { state: ui.owner.controller.getSnapshot() }), /Không tự gửi lại/);
    propose(ui, "Xóa tài liệu"); confirm(ui); await finished(ui);
    let state = list.getSnapshot();
    assert.equal(state.detail.status, "DELETED"); assert.equal(state.detail.cleanup_pending, true);
    assert(!state.items.some(d => d.document_id === initial.document_id));
    assert.match(render(DocumentActionFeedback, { state: ui.owner.controller.getSnapshot() }), /HTTP 202/);
    assert.match(render(DocumentActionFeedback, { state: ui.owner.controller.getSnapshot() }), /Raw files được giữ/);
    confirm(ui); await tick(); assert.equal(calls.filter(([m]) => m === "DELETE").length, 1);
    // A parent rerender is represented by a fresh mounted actions instance.
    ui.dispose(); ui = actionsFor(base, list);
    propose(ui, "Thử cleanup lại"); confirm(ui); await finished(ui);
    state = list.getSnapshot(); assert.equal(state.detail.cleanup_pending, false);
    assert.match(render(DocumentActionFeedback, { state: ui.owner.controller.getSnapshot() }), /HTTP 200/);
    await list.setIncludeDeleted(true);
    assert(list.getSnapshot().items.some(d => d.document_id === initial.document_id && d.status === "DELETED"));
  } finally { ui.dispose(); }
}));

test("stale confirmation refreshes without mutation; refresh failure retains receipt and exposes stale-data warning", () => fixture(async ({ base, api, list, calls }) => {
  const initial = list.getSnapshot().items.find(d => d.status === "INDEXED");
  await list.select(initial.document_id);
  const ui = actionsFor(base, list);
  try {
    propose(ui, "Re-index");
    await reindexDocument(api, initial.document_id);
    confirm(ui); await finished(ui);
    assert.equal(calls.filter(([m]) => m === "POST").length, 1);
    assert.match(ui.owner.controller.getSnapshot().message, /đã thay đổi/);
    assert.equal(list.getSnapshot().detail.version_count, initial.version_count + 1);
    // Disconnect only the post-mutation detail GET in the production client.
    const nativeFetch = globalThis.fetch;
    let afterPut = false;
    globalThis.fetch = async (url, init) => {
      if (init.method === "GET" && afterPut) throw new Error("fixture disconnected");
      const response = await nativeFetch(url, init);
      if (init.method === "PUT") afterPut = true;
      return response;
    };
    try {
      const tree = propose(ui, "Phiên bản mới");
      find(tree, e => e.props?.id === "document-version-file").props.onChange({ target: { files: [file("qa-refresh-fail.txt")] } });
      confirm(ui); await finished(ui);
      const state = ui.owner.controller.getSnapshot();
      assert.equal(state.refreshError, true); assert(state.receipt);
      assert.match(render(DocumentActionFeedback, { state }), /lần tải trước/);
    } finally { globalThis.fetch = nativeFetch; }
  } finally { ui.dispose(); }
}));

test("selection/filter unmount aborts a pending action; late receipt cannot overwrite a different document", () => fixture(async ({ base, list, calls }) => {
  const initial = list.getSnapshot().items.find(d => d.status === "INDEXED");
  const other = list.getSnapshot().items.find(d => d.document_id !== initial.document_id);
  await list.select(initial.document_id);
  const ui = actionsFor(base, list);
  const nativeFetch = globalThis.fetch;
  let release, sent = false;
  globalThis.fetch = async (url, init) => {
    const response = await nativeFetch(url, init);
    if (init.method === "POST" && String(url).endsWith("/re-index")) { sent = true; await new Promise(resolve => { release = resolve; }); }
    return response;
  };
  try {
    propose(ui, "Re-index"); confirm(ui); await until(() => sent);
    ui.dispose(); assert.equal(ui.owner.controller.getSnapshot().phase, "uncertain");
    await list.setIncludeDeleted(true); await list.select(other.document_id);
    release(); await tick(); await tick();
    assert.equal(list.getSnapshot().detail.document_id, other.document_id);
    assert.equal(calls.filter(([m, p]) => m === "POST" && p.endsWith("/re-index")).length, 1);
  } finally { globalThis.fetch = nativeFetch; release?.(); ui.dispose(); }
}));

test("lifecycle profile stays isolated; default document mutations fail closed and invalid multipart cannot create data", () => fixture(async ({ base, api }) => {
  const before = await listDocuments(api);
  const malformed = await fetch(`${base}/documents/upload`, { method: "POST", body: new FormData() });
  assert.equal(malformed.status, 422);
  assert.deepEqual(await listDocuments(api), before);
  const plain = createApiClient({ baseUrl: base.replace(/\/lifecycle$/, "") });
  await assert.rejects(updateDocument(plain, before[0].document_id, file("synthetic.txt")), e => e.status === 503);
}));

test("upload unmount ignores a late201 and never refreshes the list or automatically resends", () => fixture(async ({ base, list, calls }) => {
  const view = DocumentsDataView({ state: list.getSnapshot(), controller: list, apiBaseUrl: base });
  const element = find(view, e => e.type === DocumentUpload);
  const ui = mounted(element.type, element.props);
  const nativeFetch = globalThis.fetch;
  let release, sent = false;
  globalThis.fetch = async (url, init) => {
    const response = await nativeFetch(url, init);
    if (init.method === "POST") { sent = true; await new Promise(resolve => { release = resolve; }); }
    return response;
  };
  try {
    let tree = ui.render(); tree.props.onOpenChange(true); tree = ui.render();
    find(tree, e => e.props?.id === "document-upload-file").props.onChange({ target: { files: [file("qa-late.txt")] } });
    find(ui.render(), e => e.type === "form").props.onSubmit({ preventDefault() {} });
    await until(() => sent);
    const before = list.getSnapshot(), reads = calls.filter(([m]) => m === "GET").length;
    ui.dispose(); release(); await tick(); await tick();
    assert.equal(ui.owner.controller.getSnapshot().phase, "uncertain");
    assert.equal(ui.owner.controller.getSnapshot().result, null);
    assert.equal(list.getSnapshot(), before);
    assert.equal(calls.filter(([m]) => m === "GET").length, reads);
    assert.equal(calls.filter(([m]) => m === "POST").length, 1);
  } finally { globalThis.fetch = nativeFetch; release?.(); ui.dispose(); }
}));
