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
  const file = fileURLToPath(new URL(`../${relative}.ts`, import.meta.url));
  const exports = {};
  cache.set(relative, exports);
  new Function("exports", "require", ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText)(exports, name => name.startsWith("@/") ? load(name.slice(2)) : require(name));
  return exports;
}
const { createApiClient } = load("lib/api/client");
const { createChatStreamClient } = load("lib/api/chat");
const { listSessions, createSession, getSession, listSessionMessages, updateSessionTitle, deleteSession } = load("lib/api/sessions");
const { listDocuments, getDocument } = load("lib/api/documents");

async function fixture(run, options = {}) {
  const server = createQaMockServer({ delayMs: 0, deltaMs: 0, ...options });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const url = `http://127.0.0.1:${server.address().port}`;
  try { await run(url); } finally {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
}

test("manual QA mock REST fixtures pass production DTO validation, pagination and session separation", () => fixture(async url => {
  const api = createApiClient({ baseUrl: url });
  const sessions = await listSessions(api);
  assert.equal(sessions.items.length, 2);
  const session = await getSession(api, sessions.items[0].session_id);
  const a = await listSessionMessages(api, session.session_id, { offset: 0, limit: 2 });
  const b = await listSessionMessages(api, sessions.items[1].session_id);
  assert.equal(a.total, 24);
  assert.equal(a.items.length, 2);
  assert.equal(b.total, 2);
  assert.notEqual(a.items[0].session_id, b.items[0].session_id);
  const documents = await listDocuments(api);
  const detail = await getDocument(api, documents[0].document_id);
  assert.equal(detail.versions.length, 2);
  assert.equal(detail.active_version_id, detail.versions[0].version_id);
}));

test("manual QA SSE completes with exact persisted content and production stream validation", () => fixture(async url => {
  const api = createApiClient({ baseUrl: url });
  const session = await createSession(api, {});
  const stream = createChatStreamClient({ baseUrl: url });
  const result = await stream.stream({ session_id: session.session_id, question: "QA success" });
  assert.equal(result.terminal.data.status, "COMPLETED");
  assert.match(result.metadata.data.sources[0].file_name, /long-file-name/);
  const saved = await listSessionMessages(api, session.session_id);
  assert.equal(saved.items.at(-1).content, result.answer);
  assert.equal(saved.items.at(-1).status, "COMPLETED");
  assert.match(result.answer, /giữ  khoảng trắng\n\n/);
  assert.equal(saved.items.at(-1).citations.length, 1);
}));

test("manual QA fixture exposes post-header error, disconnect and missing metadata without provider calls", () => fixture(async url => {
  const api = createApiClient({ baseUrl: url });
  const session = await createSession(api, {});
  const stream = createChatStreamClient({ baseUrl: url });
  const error = await stream.stream({ session_id: session.session_id, question: "[error]" });
  assert.equal(error.terminal.event, "error");
  assert.equal(error.terminal.data.status, "PARTIAL");
  await assert.rejects(stream.stream({ session_id: session.session_id, question: "[disconnect]" }));
  const missing = await stream.stream({ session_id: session.session_id, question: "[no-metadata]" });
  assert.deepEqual(missing.metadata.data.sources, []);
}));

test("manual QA mock CORS, empty/error profiles and fail-closed mutations stay local", () => fixture(async url => {
  const preflight = await fetch(url + "/chat/stream", { method: "OPTIONS", headers: { Origin: "http://localhost:3000" } });
  assert.equal(preflight.status, 204);
  assert.equal(preflight.headers.get("Access-Control-Allow-Origin"), "http://localhost:3000");
  assert.match(preflight.headers.get("Access-Control-Allow-Methods"), /PATCH/);
  assert.equal((await fetch(url + "/sessions", { headers: { Origin: "https://example.test" } })).status, 403);
  assert.deepEqual(await (await fetch(url + "/empty/documents")).json(), []);
  assert.equal((await fetch(url + "/error/documents")).status, 503);
  assert.equal((await fetch(url + "/documents/upload", { method: "POST", body: "synthetic" })).status, 503);
  assert.equal((await fetch(url + "/unknown")).status, 404);
}));

test("browser QA session actions use production clients with60 sessions, rename, idempotent delete and tombstone history", () => fixture(async url => {
  const api = createApiClient({ baseUrl: url + "/many" });
  const first = await listSessions(api, { offset: 0, limit: 50 });
  const next = await listSessions(api, { offset: 50, limit: 50 });
  assert.equal(first.total, 60); assert.equal(next.items.length, 10);
  const id = first.items[0].session_id;
  assert.equal((await updateSessionTitle(api, id, "Renamed")).title, "Renamed");
  assert.equal((await deleteSession(api, id)).deleted_messages, 24);
  assert.equal((await deleteSession(api, id)).already_deleted, true);
  await assert.rejects(getSession(api, id), error => error.status === 410);
  await assert.rejects(listSessionMessages(api, id), error => error.status === 410);
  assert.equal((await listSessions(api)).total, 59);
}));

test("mock streaming session rejects DELETE409 but permits PATCH and exposes no provider call", () => fixture(async url => {
  const api = createApiClient({ baseUrl: url });
  const session = await createSession(api, {});
  const response = await fetch(url + "/chat/stream", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: session.session_id, question: "QA streaming" }) });
  try {
    await assert.rejects(deleteSession(api, session.session_id), error => error.status === 409);
    assert.equal((await updateSessionTitle(api, session.session_id, "During stream")).title, "During stream");
  } finally { await response.body.cancel(); }
}, { deltaMs: 250 }));
