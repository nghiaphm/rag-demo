import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import ts from "typescript";

const require = createRequire(import.meta.url);
const root = fileURLToPath(new URL("../", import.meta.url));
const receipt = { document_id: "document", status: "INDEXED", activated: true };
const file = name => new File(["fixture"], name, { lastModified: 1 });

function harness(upload) {
  const cache = new Map(), cleanups = [];
  let state;
  function load(relative) {
    if (cache.has(relative)) return cache.get(relative);
    const exports = {}; cache.set(relative, exports);
    new Function("exports", "require", ts.transpileModule(fs.readFileSync(path.join(root, relative + ".ts"), "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText)(exports, name => {
      if (name === "react") return { useSyncExternalStore: (_subscribe, getSnapshot) => getSnapshot(), useRef: current => ({ current }), useState: initial => [initial, next => { state = next; }],
        useEffect: effect => { cleanups.push(effect()); } };
      if (name === "@/lib/api/client") return { createApiClient: () => ({}) };
      if (name === "@/lib/api/documents") return { uploadDocument: (_api, selected, signal) => upload(selected, signal) };
      return name.startsWith("@/") ? load(name.slice(2)) : require(name);
    });
    return exports;
  }
  const hook = load("hooks/use-chat-attachments").useChatAttachments("http://mock.invalid");
  return { ...hook, state: () => state, cleanup: () => cleanups.forEach(fn => fn?.()) };
}

test("selection starts shared upload immediately, validates before network and deduplicates pending files", async () => {
  let release, calls = 0;
  const attachments = harness(async () => { calls++; return new Promise(resolve => { release = resolve; }); });
  const selected = file("phuongtien.txt");
  attachments.choose([selected, selected, file("invalid.exe")]);
  attachments.choose([selected]);
  assert.equal(calls, 1);
  assert.equal(attachments.state().length, 2);
  assert.equal(attachments.capture()[0].controller.getSnapshot().phase, "submitting");
  assert.equal(attachments.capture()[1].controller.getSnapshot().phase, "error");
  release(receipt);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(attachments.capture()[0].controller.getSnapshot().result.document_id, "document");
  attachments.cleanup();
});

test("successful old submission clears only its snapshot, retaining newly added or readded file identities", async () => {
  const attachments = harness(async () => receipt);
  const selected = file("phuongtien.txt");
  attachments.choose([selected]);
  const submitted = attachments.capture();
  attachments.remove(submitted[0].id);
  attachments.choose([selected, file("new.txt")]);
  assert.notEqual(attachments.capture()[0].id, submitted[0].id);
  assert.equal(attachments.clearSubmitted(submitted), false);
  assert.deepEqual(attachments.capture().map(entry => entry.file.name), ["phuongtien.txt", "new.txt"]);
  const current = attachments.capture();
  assert.equal(attachments.clearSubmitted(current), true);
  attachments.choose([selected]);
  assert.equal(attachments.capture().length, 1);
  attachments.cleanup();
});

test("removed or unmounted uploads ignore late successful transports without reattaching or DELETE", async () => {
  let release, observedSignal;
  const attachments = harness(async (_file, signal) => { observedSignal = signal; return new Promise(resolve => { release = resolve; }); });
  attachments.choose([file("slow.txt")]);
  const entry = attachments.capture()[0];
  attachments.remove(entry.id);
  assert.equal(observedSignal.aborted, true);
  release(receipt);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(attachments.capture().length, 0);
  assert.equal(entry.controller.getSnapshot().result, null);
  attachments.choose([file("unmount.txt")]);
  const pending = attachments.capture()[0];
  attachments.cleanup();
  assert.equal(observedSignal.aborted, true);
  release(receipt);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(pending.controller.getSnapshot().result, null);
});
