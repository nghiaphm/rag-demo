import assert from "node:assert/strict";
import fs from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const cache = new Map();
function load(relative) {
  if (cache.has(relative)) return cache.get(relative);
  const exports = {}; cache.set(relative, exports);
  const file = fileURLToPath(new URL(`../${relative}.ts`, import.meta.url));
  new Function("exports", "require", ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText)(exports, name => { assert(name.startsWith("@/")); return load(name.slice(2)); });
  return exports;
}
const { DocumentsController } = load("lib/documents/controller");
const doc = n => ({ document_id: String(n), status: "INDEXED", active_version_id: `v${n}`, versions: [] });

test("reconciliation releases an aborted list page so Load more can continue before the old transport settles", async () => {
  let resolveOld;
  const offsets = [];
  const controller = new DocumentsController({ list: async ({ offset }) => {
    offsets.push(offset);
    if (offsets.length === 1) return [doc(1), doc(2)];
    if (offsets.length === 2) return new Promise(resolve => { resolveOld = resolve; });
    return [doc(3)];
  }, get: async () => doc(1) }, 2);
  await controller.reload(); await controller.select("1");
  const pendingPage = controller.loadMore();
  controller.reconcile({ ...doc(1), status: "DELETED", active_version_id: null });
  await controller.loadMore();
  resolveOld([doc(2), doc(3)]); await pendingPage;
  assert.deepEqual(offsets, [0, 2, 1]);
  assert.deepEqual(controller.getSnapshot().items.map(d => d.document_id), ["2", "3"]);
  assert.equal(controller.getSnapshot().hasMore, false);
  assert.equal(controller.getSnapshot().detail.status, "DELETED");
  controller.dispose();
});
