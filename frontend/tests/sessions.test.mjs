import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

function loadTypescriptModule(relativePath) {
  const filename = fileURLToPath(new URL(relativePath, import.meta.url));
  const output = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const exports = {};
  new Function("exports", "require", output)(exports, specifier => {
    if (specifier.startsWith("@/")) return loadTypescriptModule(`../${specifier.slice(2)}.ts`);
    throw new Error(`Unexpected runtime import: ${specifier}`);
  });
  return exports;
}

const sessionApi = loadTypescriptModule("../lib/api/sessions.ts");
const { SessionsController, SessionLookupController } = loadTypescriptModule("../lib/sessions/controller.ts");
const { HistoryController, historyMessageToViewMessage } = loadTypescriptModule("../lib/sessions/history.ts");

const ids = {
  first: "11111111-1111-4111-8111-111111111111",
  second: "22222222-2222-4222-8222-222222222222",
  third: "33333333-3333-4333-8333-333333333333",
};

function session(sessionId, title) {
  return {
    session_id: sessionId,
    title,
    scope: { mode: "ALL_ACTIVE", document_ids: [] },
    user_id: null,
    created_at: "2026-10-14T00:00:00Z",
    updated_at: "2026-10-14T00:00:00Z",
  };
}

const first = session(ids.first, "Phiên đầu tiên");
const second = session(ids.second, "Phiên thứ hai");
const third = session(ids.third, "Cuộc trò chuyện mới");

function message(messageId, sessionId, sequence, role, content, status = "COMPLETED") {
  return {
    message_id: messageId,
    session_id: sessionId,
    sequence,
    role,
    content,
    status,
    citations: [],
    model: role === "ASSISTANT" ? "fixture/model" : null,
    usage: null,
    request_id: `request-${messageId}`,
    error_code: status === "PARTIAL" || status === "FAILED" ? "RAG_SAFE_ERROR" : null,
    created_at: "2026-10-14T00:00:00Z",
    updated_at: "2026-10-14T00:00:00Z",
    completed_at: status === "PENDING" || status === "STREAMING" ? null : "2026-10-14T00:00:01Z",
  };
}

test("session REST client lists, creates and gets exact backend routes", async () => {
  const calls = [];
  const api = {
    async request(path, options) {
      calls.push([path, options]);
      if (path === "/sessions?offset=0&limit=50") {
        return { status: 200, data: { items: [first, second], offset: 0, limit: 50, total: 2 }, headers: new Headers() };
      }
      if (path === "/sessions") {
        return { status: 201, data: third, headers: new Headers() };
      }
      if (path === `/sessions/${ids.first}`) {
        return { status: 200, data: first, headers: new Headers() };
      }
      assert.fail(`unexpected path ${path}`);
    },
  };

  const page = await sessionApi.listSessions(api);
  const created = await sessionApi.createSession(api);
  const opened = await sessionApi.getSession(api, ids.first);

  assert.deepEqual(page.items, [first, second]);
  assert.deepEqual(created, third);
  assert.deepEqual(opened, first);
  assert.deepEqual(calls.map(([path, options]) => [path, options.method]), [
    ["/sessions?offset=0&limit=50", "GET"],
    ["/sessions", "POST"],
    [`/sessions/${ids.first}`, "GET"],
  ]);
  assert.deepEqual(calls[1][1].json, {});
});

test("session REST client rejects invalid IDs and malformed list responses", async () => {
  let calls = 0;
  const api = {
    async request() {
      calls += 1;
      return { status: 200, data: { items: [], offset: 0, limit: 0, total: 0 }, headers: new Headers() };
    },
  };
  await assert.rejects(sessionApi.getSession(api, "typed-by-user"), /không hợp lệ/);
  assert.equal(calls, 0);
  await assert.rejects(sessionApi.listSessions(api), /không khớp API contract/);
  assert.equal(calls, 1);
});

test("session controller loads backend order and creates exactly one new chat", async () => {
  let createCalls = 0;
  let releaseCreate;
  const pendingCreate = new Promise(resolve => { releaseCreate = resolve; });
  const controller = new SessionsController({
    list: async () => ({ items: [first, second], offset: 0, limit: 50, total: 2 }),
    create: async () => {
      createCalls += 1;
      return pendingCreate;
    },
  });

  await controller.load();
  assert.equal(controller.getSnapshot().status, "ready");
  assert.deepEqual(controller.getSnapshot().sessions.map(item => item.session_id), [ids.first, ids.second]);

  const creating = controller.createNew();
  assert.equal(controller.getSnapshot().isCreating, true);
  assert.equal(await controller.createNew(), null);
  releaseCreate(third);
  assert.deepEqual(await creating, third);

  const state = controller.getSnapshot();
  assert.equal(createCalls, 1);
  assert.equal(state.isCreating, false);
  assert.equal(state.total, 3);
  assert.deepEqual(state.sessions.map(item => item.session_id), [ids.third, ids.first, ids.second]);
});

test("session controller exposes safe list/create errors and clears loading", async () => {
  const controller = new SessionsController({
    list: async () => { throw new Error("private list detail"); },
    create: async () => { throw new Error("private create detail"); },
  });
  await controller.load();
  assert.equal(controller.getSnapshot().status, "error");
  assert.equal(controller.getSnapshot().error, "Không thể tải danh sách phiên trò chuyện.");
  assert.equal(await controller.createNew(), null);
  assert.equal(controller.getSnapshot().isCreating, false);
  assert.match(controller.getSnapshot().error, /Không thể tạo phiên trò chuyện mới/);
  assert.match(controller.getSnapshot().error, /Kiểm tra danh sách/);
});

test("opening a valid session resolves it through the mock API", async () => {
  let openedId = null;
  const controller = new SessionLookupController(ids.second, {
    isValidId: sessionApi.isSessionId,
    get: async sessionId => {
      openedId = sessionId;
      return second;
    },
  });
  await controller.load();
  assert.equal(openedId, ids.second);
  assert.equal(controller.getSnapshot().status, "ready");
  assert.deepEqual(controller.getSnapshot().session, second);
});

test("invalid, missing and deleted sessions have explicit lookup states", async () => {
  let invalidCalls = 0;
  const invalid = new SessionLookupController("not-a-uuid", {
    isValidId: sessionApi.isSessionId,
    get: async () => {
      invalidCalls += 1;
      return first;
    },
  });
  assert.equal(invalid.getSnapshot().status, "invalid");
  await invalid.load();
  assert.equal(invalidCalls, 0);

  for (const status of [404, 410]) {
    const missing = new SessionLookupController(ids.first, {
      isValidId: sessionApi.isSessionId,
      get: async () => { throw { status }; },
    });
    await missing.load();
    assert.equal(missing.getSnapshot().status, "missing");
    assert.equal(missing.getSnapshot().session, null);
  }
});

test("lookup network failure becomes recoverable error and never stays loading", async () => {
  let attempts = 0;
  const controller = new SessionLookupController(ids.first, {
    isValidId: sessionApi.isSessionId,
    get: async () => {
      attempts += 1;
      if (attempts === 1) throw new Error("private network detail");
      return first;
    },
  });
  await controller.load();
  assert.equal(controller.getSnapshot().status, "error");
  await controller.load();
  assert.equal(controller.getSnapshot().status, "ready");
  assert.equal(attempts, 2);
});

test("message REST client requests exact pagination and rejects cross-session data", async () => {
  const firstMessage = message("message-1", ids.first, 1, "USER", "Câu hỏi");
  const secondMessage = message("message-2", ids.first, 2, "ASSISTANT", "Câu trả lời");
  const calls = [];
  const api = {
    async request(path, options) {
      calls.push([path, options]);
      return {
        status: 200,
        data: { items: [firstMessage, secondMessage], offset: 0, limit: 2, total: 2 },
        headers: new Headers(),
      };
    },
  };

  const page = await sessionApi.listSessionMessages(api, ids.first, { offset: 0, limit: 2 });
  assert.deepEqual(page.items, [firstMessage, secondMessage]);
  assert.equal(calls[0][0], `/sessions/${ids.first}/messages?offset=0&limit=2`);
  assert.equal(calls[0][1].method, "GET");

  const mixedApi = {
    request: async () => ({
      status: 200,
      data: { items: [{ ...firstMessage, session_id: ids.second }], offset: 0, limit: 2, total: 1 },
      headers: new Headers(),
    }),
  };
  await assert.rejects(
    sessionApi.listSessionMessages(mixedApi, ids.first, { offset: 0, limit: 2 }),
    /không khớp session/
  );
});

test("history controller follows offsets and restores stable backend history", async () => {
  const history = [
    message("message-1", ids.first, 1, "USER", "Một"),
    message("message-2", ids.first, 2, "ASSISTANT", "Hai"),
    message("message-3", ids.first, 3, "USER", "Ba"),
    message("message-4", ids.first, 4, "ASSISTANT", "Bốn"),
    message("message-5", ids.first, 5, "USER", "Năm"),
  ];
  const offsets = [];
  const controller = new HistoryController(ids.first, {
    async list(sessionId, query) {
      assert.equal(sessionId, ids.first);
      offsets.push(query.offset);
      return {
        items: history.slice(query.offset, query.offset + query.limit),
        offset: query.offset,
        limit: query.limit,
        total: history.length,
      };
    },
  }, 2);

  await controller.load();
  const state = controller.getSnapshot();
  assert.deepEqual(offsets, [0, 2, 4]);
  assert.equal(state.status, "ready");
  assert.equal(state.total, 5);
  assert.deepEqual(state.messages.map(item => item.sequence), [1, 2, 3, 4, 5]);
});

test("two history controllers never mix sessions", async () => {
  const histories = new Map([
    [ids.first, [message("first-1", ids.first, 1, "USER", "Session one")]],
    [ids.second, [message("second-1", ids.second, 1, "USER", "Session two")]],
  ]);
  const services = {
    async list(sessionId, query) {
      const items = histories.get(sessionId) ?? [];
      return { items, offset: query.offset, limit: query.limit, total: items.length };
    },
  };
  const left = new HistoryController(ids.first, services, 2);
  const right = new HistoryController(ids.second, services, 2);

  await Promise.all([left.load(), right.load()]);
  assert.deepEqual(left.getSnapshot().messages.map(item => item.content), ["Session one"]);
  assert.deepEqual(right.getSnapshot().messages.map(item => item.content), ["Session two"]);
  assert(left.getSnapshot().messages.every(item => item.session_id === ids.first));
  assert(right.getSnapshot().messages.every(item => item.session_id === ids.second));
});

test("history rejects a mixed page and never exposes partial data", async () => {
  const controller = new HistoryController(ids.first, {
    async list(_sessionId, query) {
      return {
        items: [message("wrong-1", ids.second, 1, "USER", "Wrong session")],
        offset: query.offset,
        limit: query.limit,
        total: 1,
      };
    },
  }, 2);
  await controller.load();
  assert.equal(controller.getSnapshot().status, "error");
  assert.deepEqual(controller.getSnapshot().messages, []);
  assert.equal(controller.getSnapshot().total, 0);
});

test("history refresh replaces state from API without local persistence", async () => {
  let history = [message("refresh-1", ids.first, 1, "USER", "Trước refresh")];
  const controller = new HistoryController(ids.first, {
    async list(_sessionId, query) {
      return {
        items: history.slice(query.offset, query.offset + query.limit),
        offset: query.offset,
        limit: query.limit,
        total: history.length,
      };
    },
  }, 10);

  await controller.load();
  assert.deepEqual(controller.getSnapshot().messages.map(item => item.content), ["Trước refresh"]);
  history = [
    message("refresh-1", ids.first, 1, "USER", "Từ backend sau refresh"),
    message("refresh-2", ids.first, 2, "ASSISTANT", "Đã phục hồi"),
  ];
  await controller.load();
  assert.deepEqual(
    controller.getSnapshot().messages.map(item => item.content),
    ["Từ backend sau refresh", "Đã phục hồi"]
  );
});

test("history messages map to chat DTO state without inventing sources", () => {
  const partial = message("partial-1", ids.first, 2, "ASSISTANT", "Một phần", "PARTIAL");
  partial.citations = [{
    chunk_id: "chunk",
    document_id: "document",
    version_id: "version",
    file_name: "fixture.md",
    page: 0,
  }];
  const view = historyMessageToViewMessage(partial);
  assert.equal(view.key, `${ids.first}:partial-1`);
  assert.equal(view.role, "assistant");
  assert.equal(view.status, "PARTIAL");
  assert.equal(view.content, "Một phần");
  assert.deepEqual(view.sources, []);
  assert.deepEqual(view.citations, partial.citations);
  assert.equal(view.error.code, "RAG_SAFE_ERROR");
  assert.equal(view.error.retryable, false);
});
