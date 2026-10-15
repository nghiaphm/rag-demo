import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import ts from "typescript";
import { createQaMockServer } from "../scripts/qa-mock-api.mjs";

const require = createRequire(import.meta.url), cache = new Map();
function load(relative) {
  if (cache.has(relative)) return cache.get(relative);
  const exports = {}; cache.set(relative, exports);
  new Function("exports", "require", ts.transpileModule(fs.readFileSync(fileURLToPath(new URL(`../${relative}.ts`, import.meta.url)), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText)(exports, name => name.startsWith("@/") ? load(name.slice(2)) : require(name));
  return exports;
}
const { createApiClient } = load("lib/api/client");
const { createChatServices } = load("lib/chat/services");
const { ChatController } = load("lib/chat/controller");
const { createChatStreamClient } = load("lib/api/chat");
const { canonicalChatPath } = load("lib/chat/recovery");
const { listSessions, createSession, updateSessionTitle, deleteSession, listSessionMessages } = load("lib/api/sessions");
const { uploadDocument, getDocument, updateDocument, reindexDocument, deleteDocument, listDocuments } = load("lib/api/documents");

test("one isolated HTTP workspace supports session CRUD/three-turn SSE/history plus document lifecycle without cross-session data", async () => {
  const server = createQaMockServer({ delayMs: 0, deltaMs: 0 }), calls = [];
  server.on("request", req => calls.push([req.method, req.url]));
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${server.address().port}/lifecycle`, api = createApiClient({ baseUrl: base });
  const chat = new ChatController(createChatServices(base));
  try {
    for (let i = 0; i < 3; i++) {
      const turn = chat.submit(`QA turn ${i + 1}`);
      assert.equal(await chat.submit("duplicate"), false);
      await turn;
      assert.equal(chat.getSnapshot().historyVerified, true);
      assert.equal(chat.getSnapshot().messages.at(-1).status, "COMPLETED");
    }
    const id = chat.getSnapshot().sessionId;
    const renamed = await updateSessionTitle(api, id, "  QA renamed  ");
    assert.equal(renamed.title, "QA renamed");
    assert((await listSessions(api)).items.some(s => s.session_id === id && s.title === renamed.title));
    const restored = await listSessionMessages(api, id);
    assert.equal(restored.items.length, 6);
    assert(restored.items.every(m => m.session_id === id));
    assert.equal(new Set(restored.items.filter(m => m.role === "ASSISTANT").map(m => m.request_id)).size, 3);
    const other = await createSession(api, {});
    assert.deepEqual((await listSessionMessages(api, other.session_id)).items, []);
    assert.match(restored.items.at(-1).content, /giữ  khoảng trắng\n\n/);

    const file = new File(["only a synthetic fixture\n"], "qa-functional.txt");
    const uploaded = await uploadDocument(api, file);
    assert.equal(uploaded.status, "INDEXED"); assert.equal(uploaded.activated, true);
    const version = await updateDocument(api, uploaded.document_id, file);
    const reindex = await reindexDocument(api, uploaded.document_id);
    const detail = await getDocument(api, uploaded.document_id);
    assert.equal(detail.version_count, 3); assert.equal(detail.active_version_id, reindex.version_id);
    assert.equal(new Set([uploaded.version_id, version.version_id, reindex.version_id]).size, 3);
    assert.equal((await deleteDocument(api, uploaded.document_id)).httpStatus, 202);
    assert(!(await listDocuments(api)).some(d => d.document_id === uploaded.document_id));
    assert((await listDocuments(api, { include_deleted: true })).some(d => d.document_id === uploaded.document_id));
    assert.equal((await deleteDocument(api, uploaded.document_id)).httpStatus, 200);
    assert.equal((await getDocument(api, uploaded.document_id)).cleanup_pending, false);

    assert.equal((await deleteSession(api, id)).already_deleted, false);
    assert.equal((await deleteSession(api, id)).already_deleted, true);
    await assert.rejects(listSessionMessages(api, id), error => error.status === 410);
    assert.deepEqual((await listSessionMessages(api, other.session_id)).items, []);
    assert.equal(calls.filter(([m, p]) => m === "POST" && p === "/lifecycle/sessions").length, 2);
    assert.equal(calls.filter(([m, p]) => m === "POST" && p === "/lifecycle/chat/stream").length, 3);
  } finally { chat.dispose(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
});

for (const terminalStatus of ["PARTIAL", "FAILED"]) test(terminalStatus === "PARTIAL"
  ? "whitespace-only PARTIAL SSE vs persisted FAILED warns and retains exact content without replay or canonical navigation"
  : "matching whitespace-only FAILED SSE/history verifies exact content and permits canonical recovery without replay", async () => {
  const id = n => `${String(n).padStart(8, "0")}-1111-4111-8111-111111111111`;
  const content = " \n\t ", session = id(1), requestId = id(2), userId = id(3), assistantId = id(4);
  let posts = 0, reads = 0;
  const frames = [
    ["start", { sequence: 1, mode: "PERSISTENT", session_id: session, request_id: requestId, user_message_id: userId, assistant_message_id: assistantId }],
    ["metadata", { sequence: 2, sources: [], model: null }],
    ["delta", { sequence: 3, content }],
    ["error", { sequence: 4, status: terminalStatus, usage: null, error: { code: "RAG_STREAM_ERROR", message: "Fixture error", retryable: true } }],
  ];
  const stream = createChatStreamClient({ baseUrl: "http://mock.invalid", fetch: async () => {
    posts++;
    return new Response(frames.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join(""), { headers: { "Content-Type": "text/event-stream" } });
  } });
  const controller = new ChatController({ createSession: async () => ({ session_id: session }), stream: stream.stream,
    loadHistory: async () => {
      reads++;
      const base = { origin: "history", model: null, sources: [], citations: [], usage: null, error: null, requestId };
      return [{ ...base, key: "u", messageId: userId, role: "user", content: "question", status: "COMPLETED" },
        { ...base, key: "a", messageId: assistantId, role: "assistant", content, status: "FAILED", error: { code: "RAG_STREAM_ERROR" } }];
    },
  });
  await controller.submit("question");
  const state = controller.getSnapshot();
  assert.equal(state.messages.at(-1).status, terminalStatus);
  assert.equal(state.messages.at(-1).content, content);
  assert.equal(state.isGenerating, false); assert.equal(state.historyVerified, terminalStatus === "FAILED");
  if (terminalStatus === "PARTIAL") {
    assert(state.persistenceError); assert.equal(canonicalChatPath(null, state), null);
  } else {
    assert.equal(state.persistenceError, null); assert.equal(canonicalChatPath(null, state), `/chat/${session}`);
  }
  assert.equal(posts, 1); assert.equal(reads, 1);
  controller.dispose();
});
