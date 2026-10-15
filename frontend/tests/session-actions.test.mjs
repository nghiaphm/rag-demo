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
  new Function("exports", "require", ts.transpileModule(fs.readFileSync(fileURLToPath(new URL(`../${relative}.ts`, import.meta.url)), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText)(exports, name => load(name.slice(2)));
  return exports;
}
const api = load("lib/api/sessions");
const { SessionsController } = load("lib/sessions/controller");
const id = n => `${String(n).padStart(8, "0")}-1111-4111-8111-111111111111`;
const session = n => ({ session_id: id(n), title: `Session ${n}`, scope: { mode: "ALL_ACTIVE", document_ids: [] }, user_id: null,
  created_at: "2026-10-14T00:00:00Z", updated_at: "2026-10-14T00:00:00Z" });
const receipt = (n, overrides = {}) => ({ session_id: id(n), deleted_messages: 2, already_deleted: false,
  deleted_at: "2026-10-14T00:00:00Z", status: "DELETED", message_policy: "hard_deleted", tombstone_retained: true, ...overrides });
const page = items => ({ items, offset: 0, limit: 50, total: items.length });
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };

test("PATCH normalizes title, preserves Unicode code points and DELETE validates idempotent receipt", async () => {
  const calls = [];
  const client = { request: async (path, options) => {
    calls.push([path, options]);
    return { status: 200, data: options.method === "PATCH" ? { ...session(1), title: options.json.title } : receipt(1, { already_deleted: true, deleted_messages: 0 }) };
  } };
  assert.equal((await api.updateSessionTitle(client, id(1), "  New title  ")).title, "New title");
  assert.equal((await api.updateSessionTitle(client, id(1), "🙂".repeat(200))).title.length, 400);
  assert.equal((await api.deleteSession(client, id(1))).already_deleted, true);
  assert.equal(calls[0][0], `/sessions/${id(1)}`); assert.equal(calls[0][1].method, "PATCH");
  assert.deepEqual(calls[0][1].json, { title: "New title" }); assert.equal(calls[2][1].method, "DELETE");
  for (const title of ["", "  ", "x".repeat(201)]) await assert.rejects(api.updateSessionTitle(client, id(1), title));
  await assert.rejects(api.deleteSession(client, "invalid")); assert.equal(calls.length, 3);
});

test("session action clients reject wrong ownership, response status and policy", async () => {
  for (const data of [receipt(2), receipt(1, { message_policy: "retained" }), receipt(1, { tombstone_retained: false }), receipt(1, { deleted_at: "invalid" })]) {
    await assert.rejects(api.deleteSession({ request: async () => ({ status: 200, data }) }, id(1)));
  }
  await assert.rejects(api.updateSessionTitle({ request: async () => ({ status: 200, data: session(2) }) }, id(1), "New"));
  await assert.rejects(api.deleteSession({ request: async () => ({ status: 202, data: receipt(1) }) }, id(1)));
});

test("pagination reaches beyond50, rejects overlapping pages and preserves items on failure", async () => {
  const items = Array.from({ length: 60 }, (_, n) => session(n + 1));
  const queries = [];
  const controller = new SessionsController({ create: async () => session(99), list: async (_, query) => {
    queries.push(query); return { ...query, total: 60, items: items.slice(query.offset, query.offset + query.limit) };
  } });
  await controller.load(); await controller.loadMore();
  assert.equal(controller.getSnapshot().sessions.length, 60);
  assert.deepEqual(queries.map(q => q.offset), [0, 50]);
  await controller.loadMore(); assert.equal(queries.length, 2);
  const overlap = new SessionsController({ create: async () => session(99), list: async (_, query) => ({ ...query, total: 60, items: query.offset ? [session(1)] : items.slice(0, 50) }) });
  await overlap.load(); await overlap.loadMore();
  assert.equal(overlap.getSnapshot().status, "error"); assert.equal(overlap.getSnapshot().sessions.length, 50);
});

test("confirmed delete aborts stale list, publishes receipt only after success and refreshes authoritative list", async () => {
  const old = deferred(), mutation = deferred(); let lists = 0, deletes = 0;
  const controller = new SessionsController({ create: async () => session(3), list: async () => ++lists === 1 ? old.promise : page([session(2)]),
    remove: async () => { deletes++; return mutation.promise; } });
  const loading = controller.load();
  assert.equal(await controller.remove(id(1), false), null); assert.equal(deletes, 0);
  const removing = controller.remove(id(1), true);
  assert.equal(await controller.remove(id(1), true), null);
  assert.equal(controller.getSnapshot().isMutating, true);
  mutation.resolve(receipt(1)); assert.equal((await removing).session_id, id(1));
  old.resolve(page([session(1), session(2)])); await loading; await Promise.resolve();
  assert.deepEqual(controller.getSnapshot().sessions.map(s => s.session_id), [id(2)]);
  assert.equal(deletes, 1); assert.equal(controller.getSnapshot().isMutating, false);
});

test("409 and network mutation failures retain list and never replay; rename reconciles successful read", async () => {
  let calls = 0;
  const controller = new SessionsController({ create: async () => session(3), list: async () => page([session(1)]),
    remove: async () => { calls++; throw { status: 409 }; }, rename: async () => ({ ...session(1), title: "New" }) });
  await controller.load();
  assert.equal(await controller.remove(id(1), true), null);
  assert.equal(calls, 1); assert.match(controller.getSnapshot().mutationError, /xung đột/);
  assert.equal(controller.getSnapshot().sessions.length, 1);
  assert.equal((await controller.rename(id(1), "New")).title, "New");
  const unknown = new SessionsController({ create: async () => session(3), list: async () => page([]), remove: async () => { throw { kind: "network" }; } });
  await unknown.remove(id(1), true); assert.match(unknown.getSnapshot().mutationError, /Không tự gửi lại/);
});

test("unmount drops late mutations and releases pending status", async () => {
  const pending = deferred();
  const controller = new SessionsController({ create: async () => session(3), list: async () => page([session(1)]), remove: async () => pending.promise });
  await controller.load(); const request = controller.remove(id(1), true); controller.dispose();
  pending.resolve(receipt(1)); assert.equal(await request, null);
  assert.equal(controller.getSnapshot().isMutating, false);
  assert.equal(controller.getSnapshot().sessions.length, 1);
});

test("HTTP failures never remove a session or replay a protected action", async () => {
  for (const status of [404, 410, 422, 429, 503]) {
    let calls = 0;
    const controller = new SessionsController({ create: async () => session(3), list: async () => page([session(1)]),
      remove: async () => { calls++; throw { status }; } });
    await controller.load(); await controller.remove(id(1), true);
    assert.equal(calls, 1); assert.equal(controller.getSnapshot().sessions.length, 1);
    assert.equal(controller.getSnapshot().isMutating, false);
    assert.match(controller.getSnapshot().mutationError, /Không tự gửi lại/);
  }
});
