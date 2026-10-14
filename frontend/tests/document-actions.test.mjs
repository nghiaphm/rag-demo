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
const { updateDocument, reindexDocument, deleteDocument } = load("lib/api/documents");
const { createApiClient } = load("lib/api/client");
const { DocumentActionsController } = load("lib/documents/actions-controller");
const { DocumentsController } = load("lib/documents/controller");
const { DocumentActions, DocumentActionFeedback } = load("components/documents/document-actions");
const id = n => `${n.toString(16).padStart(8, "0")}-1111-4111-8111-111111111111`;
const doc = (overrides = {}) => ({ document_id: id(1), file_name: "fixture.pdf", status: "INDEXED", active_version_id: id(2),
  chunk_count: 2, version_count: 1, cleanup_pending: false, created_at: "2026-10-14T00:00:00Z", updated_at: "2026-10-14T01:00:00Z",
  versions: [{ version_id: id(2), version: 1, file_name: "fixture.pdf", status: "INDEXED", checksum_sha256: "fixture",
    size_bytes: 10, chunk_count: 2, created_at: "2026-10-14T00:00:00Z", indexed_at: "2026-10-14T01:00:00Z" }], ...overrides });
const result = (overrides = {}) => ({ document_id: id(1), version_id: id(3), job_id: id(4), file_name: "fixture.txt", num_chunks: 2,
  status: "INDEXED", activated: true, ...overrides });
const deleted = (pending = false) => ({ httpStatus: pending ? 202 : 200, response: { document_id: id(1), status: "DELETED",
  deleted_chunks: pending ? 2 : 0, retained_files: 1, cleanup_pending: pending, raw_file_policy: "retained", retrieval_eligible: false } });
const file = () => new File(["mock content"], "fixture.txt");
const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, props));
const services = overrides => ({ get: async () => doc(), update: async () => result(), reindex: async () => result(),
  remove: async () => deleted(), reconcile: () => {}, ...overrides });

test("version/reindex/delete clients use exact methods, multipart and response ownership", async () => {
  const calls = [];
  const api = { request: async (route, options) => {
    calls.push([route, options]);
    return options.method === "DELETE" ? { status: 202, data: deleted(true).response } : { status: 201, data: result() };
  } };
  await updateDocument(api, id(1), file());
  await reindexDocument(api, id(1));
  const removal = await deleteDocument(api, id(1));
  assert.deepEqual(calls.map(([route, options]) => [route, options.method]), [[`/documents/${id(1)}`, "PUT"],
    [`/documents/${id(1)}/re-index`, "POST"], [`/documents/${id(1)}`, "DELETE"]]);
  assert.deepEqual([...calls[0][1].body.keys()], ["file"]);
  assert.equal(calls[1][1].body, undefined);
  assert.equal(calls[1][1].json, undefined);
  assert.equal(removal.httpStatus, 202);
  assert.equal(removal.response.cleanup_pending, true);
  for (const method of [updateDocument, reindexDocument]) {
    await assert.rejects(method({ request: async () => ({ status: 201, data: result({ document_id: id(99) }) }) }, id(1), file()), TypeError);
  }
});

test("idempotent DELETE accepts 200 and 202 but rejects inconsistent cleanup or invented raw deletion", async () => {
  let calls = 0;
  const api = { request: async () => { calls++; const response = deleted(calls === 1); return { status: response.httpStatus, data: response.response }; } };
  assert.equal((await deleteDocument(api, id(1))).httpStatus, 202);
  assert.equal((await deleteDocument(api, id(1))).response.deleted_chunks, 0);
  assert.equal(calls, 2);
  for (const value of [{ ...deleted().response, cleanup_pending: true }, { ...deleted().response, raw_file_policy: "deleted" },
    { ...deleted().response, document_id: id(99) }, { ...deleted().response, retrieval_eligible: true }]) {
    await assert.rejects(deleteDocument({ request: async () => ({ status: 200, data: value }) }, id(1)), TypeError);
  }
});

test("actual fetch wrapper never sets multipart Content-Type or retries a mutation failure", async () => {
  let calls = 0;
  const api = createApiClient({ baseUrl: "http://mock.invalid", fetch: async (_url, options) => {
    calls++;
    assert.equal(options.method, "PUT");
    assert.equal(options.headers.get("Content-Type"), null);
    return Response.json({ detail: "private" }, { status: 409 });
  } });
  await assert.rejects(updateDocument(api, id(1), file()), error => error.status === 409 && !error.message.includes("private"));
  assert.equal(calls, 1);
});

test("all protected actions require explicit confirmation before any request", async () => {
  const controller = new DocumentActionsController(services({ get: async () => assert.fail("unconfirmed action must not GET or mutate") }));
  for (const action of ["version", "reindex", "delete"]) assert.equal(await controller.run(action, doc(), false, file()), false);
});

test("stale snapshots refresh the shown document and do not issue the confirmed mutation", async () => {
  for (const change of [{ updated_at: "2026-10-14T02:00:00Z" }, { active_version_id: id(9) }, { version_count: 2 }, { status: "DELETED" }]) {
    let reconciled;
    const controller = new DocumentActionsController(services({ get: async () => doc(change),
      remove: async () => assert.fail("stale DELETE"), reconcile: value => { reconciled = value; } }));
    assert.equal(await controller.run("delete", doc(), true), false);
    assert.equal(controller.getSnapshot().phase, "error");
    assert.match(controller.getSnapshot().message, /đã thay đổi/);
    assert.deepEqual(reconciled, doc(change));
  }
});

test("deleted/processing/no-active documents cannot update or reindex", async () => {
  for (const [action, current] of [["version", doc({ status: "DELETED" })], ["version", doc({ status: "PROCESSING" })],
    ["reindex", doc({ active_version_id: null })]]) {
    const controller = new DocumentActionsController(services({ get: async () => current,
      update: async () => assert.fail(), reindex: async () => assert.fail() }));
    assert.equal(await controller.run(action, current, true, file()), false);
    assert.equal(controller.getSnapshot().phase, "error");
  }
});

test("new version failure reads persisted failed version while retaining old active ID", async () => {
  const failed = doc({ version_count: 2, updated_at: "2026-10-14T02:00:00Z", versions: [
    { ...doc().versions[0], version_id: id(3), version: 2, status: "FAILED" }, doc().versions[0] ] });
  let gets = 0;
  let reconciled;
  const controller = new DocumentActionsController(services({ get: async () => ++gets === 1 ? doc() : failed,
    update: async () => { throw { status: 500 }; }, reconcile: value => { reconciled = value; } }));
  await controller.run("version", doc(), true, file());
  assert.equal(controller.getSnapshot().phase, "uncertain");
  assert.equal(reconciled.active_version_id, id(2));
  assert.equal(reconciled.versions[0].status, "FAILED");
  assert.equal(controller.getSnapshot().receipt, null);
});

test("successful reindex reconciles authoritative detail rather than blindly promoting response version", async () => {
  let gets = 0;
  let reconciled;
  const current = doc({ version_count: 2, active_version_id: id(8) });
  const controller = new DocumentActionsController(services({ get: async () => ++gets === 1 ? doc() : current,
    reconcile: value => { reconciled = value; } }));
  assert.equal(await controller.run("reindex", doc(), true), true);
  assert.equal(controller.getSnapshot().receipt.result.version_id, id(3));
  assert.equal(reconciled.active_version_id, id(8));
});

test("202 cleanup can be retried only by a new confirmation, with retained files and zero chunks on repeated DELETE", async () => {
  let removes = 0;
  let current = doc();
  const controller = new DocumentActionsController(services({ get: async () => current,
    remove: async () => { removes++; current = doc({ status: "DELETED", active_version_id: null, cleanup_pending: removes === 1 });
      return deleted(removes === 1); } }));
  await controller.run("delete", doc(), true);
  assert.equal(controller.getSnapshot().receipt.result.httpStatus, 202);
  assert.equal(await controller.run("delete", current, true), false);
  assert.equal(removes, 1);
  controller.reset();
  await controller.run("delete", current, true);
  assert.equal(removes, 2);
  assert.equal(controller.getSnapshot().receipt.result.response.retained_files, 1);
  assert.equal(controller.getSnapshot().receipt.result.response.deleted_chunks, 0);
});

test("duplicate confirm, navigation and late mutation results cannot apply stale detail", async () => {
  let release;
  let called;
  const started = new Promise(resolve => { called = resolve; });
  const controller = new DocumentActionsController(services({ remove: async () => { called(); return new Promise(resolve => { release = resolve; }); },
    reconcile: () => assert.fail("aborted action must not apply detail") }));
  const pending = controller.run("delete", doc(), true);
  await started;
  assert.equal(await controller.run("delete", doc(), true), false);
  controller.dispose();
  release(deleted());
  await pending;
  assert.equal(controller.getSnapshot().phase, "uncertain");
});

test("failed reconciliation keeps receipt but warns old detail is not current", async () => {
  let gets = 0;
  const controller = new DocumentActionsController(services({ get: async () => { if (++gets === 1) return doc(); throw new Error("private"); } }));
  await controller.run("reindex", doc(), true);
  assert.equal(controller.getSnapshot().refreshError, true);
  assert(controller.getSnapshot().receipt);
  const html = render(DocumentActionFeedback, { state: controller.getSnapshot() });
  assert.match(html, /Dữ liệu bên dưới là lần tải trước/);
});

test("Documents controller never applies action state to another selection or leaks stale list pages", async () => {
  let release;
  const controller = new DocumentsController({ list: async () => new Promise(resolve => { release = resolve; }),
    get: async docId => doc({ document_id: docId }) });
  const pending = controller.reload();
  await controller.select(id(1));
  const removed = doc({ status: "DELETED", active_version_id: null });
  controller.reconcile(removed);
  release([doc()]);
  await pending;
  assert.equal(controller.getSnapshot().detail.status, "DELETED");
  assert.deepEqual(controller.getSnapshot().items, []);
  await controller.select(id(99));
  controller.reconcile(removed);
  assert.equal(controller.getSnapshot().detail.document_id, id(99));
});

test("soft-delete receipt UI describes retained raw files and pending vector cleanup without claiming physical deletion", () => {
  const html = render(DocumentActionFeedback, { state: { phase: "done", receipt: { action: "delete", result: deleted(true) }, message: null, refreshError: false } });
  assert.match(html, /HTTP 202/);
  assert.match(html, /Raw files được giữ/);
  assert.match(html, /DELETE lại/);
  assert(!html.includes("raw files đã xóa"));
  const disabled = render(DocumentActions, { document: doc(), apiBaseUrl: null });
  assert.equal((disabled.match(/\sdisabled=""/g) ?? []).length, 3);
});
