import assert from "node:assert/strict";
import fs from "node:fs";
import { test } from "node:test";
import ts from "typescript";
import { fileURLToPath } from "node:url";

// Execute production controller -> REST/SSE clients -> parser -> mock HTTP
// -> persisted history -> controller. All requests stay inside this fixture.
const modules = new Map();
function load(relative) {
  if (modules.has(relative)) return modules.get(relative);
  const filename = fileURLToPath(new URL(`../${relative}.ts`, import.meta.url));
  const output = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const exports = {};
  modules.set(relative, exports);
  new Function("exports", "require", output)(exports, specifier => {
    assert(specifier.startsWith("@/"), `Unexpected runtime import ${specifier}`);
    return load(specifier.slice(2));
  });
  return exports;
}
const { ChatController } = load("lib/chat/controller");
const { createApiClient } = load("lib/api/client");
const { createChatStreamClient } = load("lib/api/chat");
const { createSession, getSession, listSessionMessages } = load("lib/api/sessions");
const { loadMessageHistory, historyMessageToViewMessage } = load("lib/sessions/history");
const uuid = n => `${n.toString(16).padStart(8, "0")}-1111-4111-8111-111111111111`;
const sessionA = uuid(1);
const sessionB = uuid(2);
const frame = (event, data) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
const encoder = new TextEncoder();
const usage = { input_tokens: 3, output_tokens: 4, total_tokens: 7 };
const blankMessage = {
  model: null, sources: [], citations: [], usage: null, error: null,
};
function fixture({ mismatch = false, failRead = false } = {}) {
  const calls = [];
  const stored = [];
  let turns = 0;
  let lastLiveMessages;
  const fetch = async (url, init) => {
    const target = new URL(url);
    calls.push([init.method, target.pathname + target.search]);
    if (target.pathname === "/sessions" && init.method === "POST") {
      assert.equal(init.body, "{}");
      return Response.json(session(), { status: 201 });
    }
    if (target.pathname === `/sessions/${sessionA}`) return Response.json(session());
    if (target.pathname === `/sessions/${sessionA}/messages`) {
      if (failRead) return Response.json({}, { status: 503 });
      const offset = Number(target.searchParams.get("offset"));
      const limit = Number(target.searchParams.get("limit"));
      return Response.json({ items: stored.slice(offset, offset + limit), offset, limit, total: stored.length });
    }
    assert.equal(target.pathname, "/chat/stream");
    const payload = JSON.parse(init.body);
    assert.equal(payload.session_id, sessionA);
    assert.deepEqual(Object.keys(payload).sort(), ["question", "session_id"]);
    turns++;
    const requestId = uuid(100 + turns);
    const userId = uuid(200 + turns * 2);
    const assistantId = uuid(201 + turns * 2);
    const parts = [`Lượt ${turns}: `, "giữ  khoảng trắng\n", " kết thúc "];
    const answer = parts.join("");
    const base = {
      session_id: sessionA, citations: [], usage: null, model: null,
      request_id: requestId, error_code: null,
      created_at: "2026-10-14T00:00:00Z", updated_at: "2026-10-14T00:00:01Z",
      completed_at: "2026-10-14T00:00:01Z", status: "COMPLETED",
    };
    stored.push(
      { ...base, message_id: userId, sequence: turns * 2 - 1, role: "USER", content: payload.question },
      { ...base, message_id: assistantId, sequence: turns * 2, role: "ASSISTANT",
        content: mismatch ? "incorrect persisted text" : answer, model: "fixture/model", usage }
    );
    lastLiveMessages = [
      { ...blankMessage, key: "user", messageId: userId, requestId, role: "user", content: payload.question, status: "COMPLETED" },
      { ...blankMessage, key: "assistant", messageId: assistantId, requestId, role: "assistant", content: answer, status: "COMPLETED", model: "fixture/model", usage },
    ];
    const transcript = frame("start", { sequence: 1, request_id: requestId, session_id: sessionA,
      user_message_id: userId, assistant_message_id: assistantId, mode: "PERSISTENT" })
      + frame("metadata", { sequence: 2, model: "fixture/model", sources: [] })
      + parts.map((content, index) => frame("delta", { sequence: index + 3, content })).join("")
      + frame("done", { sequence: 6, status: "COMPLETED", usage });
    const bytes = encoder.encode(transcript);
    return new Response(new ReadableStream({ start(controller) {
      // Deliberately split UTF-8 and frames; never use reader chunks as events.
      for (let i = 0; i < bytes.length; i += 7) controller.enqueue(bytes.slice(i, i + 7));
      controller.close();
    } }), { headers: { "Content-Type": "text/event-stream" } });
  };
  function session() {
    return { session_id: sessionA, title: "Mock", scope: { mode: "ALL_ACTIVE", document_ids: [] },
      user_id: null, created_at: "2026-10-14T00:00:00Z", updated_at: "2026-10-14T00:00:00Z" };
  }
  const api = createApiClient({ baseUrl: "http://mock.invalid", fetch });
  const stream = createChatStreamClient({ baseUrl: "http://mock.invalid", fetch });
  const read = async (id, signal) => (await loadMessageHistory(id, {
    list: (sessionId, query, pageSignal) => listSessionMessages(api, sessionId, query, pageSignal),
  }, signal, 2)).map(historyMessageToViewMessage);
  const services = { createSession: signal => createSession(api, {}, signal), stream: stream.stream, loadHistory: read };
  return { api, services, read, calls, stored, lastLive: () => lastLiveMessages };
}

test("scripted three-turn mock E2E reuses session, distinct IDs and verifies paginated persistence after refresh", async () => {
  const mock = fixture();
  let controller = new ChatController(mock.services);
  for (let turn = 1; turn <= 3; turn++) {
    if (turn === 2) {
      controller.dispose();
      const session = await getSession(mock.api, sessionA);
      const history = await mock.read(session.session_id, new AbortController().signal);
      controller = new ChatController(mock.services, session.session_id, history);
    }
    assert.equal(await controller.submit(`Câu hỏi ${turn}`), true);
    const state = controller.getSnapshot();
    assert.equal(state.sessionId, sessionA);
    assert.equal(state.isGenerating, false);
    assert.equal(state.persistenceError, null);
    assert.equal(state.messages.length, turn * 2);
    assert.equal(state.messages.at(-1).content, `Lượt ${turn}: giữ  khoảng trắng\n kết thúc `);
    assert(state.messages.every(message => message.status === "COMPLETED"));
  }
  const state = controller.getSnapshot();
  assert.equal(new Set(state.messages.map(m => m.messageId)).size, 6);
  assert.equal(new Set(state.messages.filter(m => m.role === "assistant").map(m => m.requestId)).size, 3);
  assert.deepEqual(state.messages.map(m => m.messageId), mock.stored.map(m => m.message_id));
  for (let i = 0; i < 6; i += 2) assert.equal(state.messages[i].requestId, state.messages[i + 1].requestId);
  assert.equal(mock.calls.filter(([method, route]) => method === "POST" && route === "/sessions").length, 1);
  assert.equal(mock.calls.filter(([, route]) => route === "/chat/stream").length, 3);
  assert(mock.calls.some(([, route]) => route.endsWith("offset=4&limit=2")));
});

for (const failure of ["mismatch", "failRead"]) {
  test(`persisted ${failure} keeps streamed terminal text and shows safe verification error without retry`, async () => {
    const mock = fixture({ [failure]: true });
    const controller = new ChatController(mock.services, sessionA);
    await controller.submit("fixture");
    const state = controller.getSnapshot();
    assert.equal(state.messages.at(-1).status, "COMPLETED");
    assert.equal(state.messages.at(-1).content, mock.lastLive().at(-1).content);
    assert(state.persistenceError);
    assert.equal(state.isGenerating, false);
    assert.equal(mock.calls.filter(([, route]) => route === "/chat/stream").length, 1);
  });
}

test("switching sessions aborts old turn; queued old callbacks cannot change either conversation", async () => {
  let callback;
  let release;
  let signal;
  const old = new ChatController({
    createSession: async () => assert.fail("must reuse session"),
    async stream(_payload, options) {
      callback = options.onEvent;
      signal = options.signal;
      callback({ event: "start", data: { session_id: sessionA, mode: "PERSISTENT",
        request_id: uuid(10), user_message_id: uuid(11), assistant_message_id: uuid(12) } });
      callback({ event: "delta", data: { content: "A partial " } });
      await new Promise(resolve => { release = resolve; });
      throw new Error("disconnected");
    },
  }, sessionA);
  const pending = old.submit("A question");
  old.dispose();
  assert.equal(signal.aborted, true);
  const next = new ChatController({ createSession: async () => assert.fail(), stream: async () => assert.fail() }, sessionB);
  callback({ event: "delta", data: { content: "LEAK" } });
  callback({ event: "done", data: { status: "COMPLETED", usage: null } });
  release();
  await pending;
  assert.equal(old.getSnapshot().messages.at(-1).content, "A partial ");
  assert.equal(old.getSnapshot().messages.at(-1).status, "PARTIAL");
  assert.equal(next.getSnapshot().sessionId, sessionB);
  assert.deepEqual(next.getSnapshot().messages, []);
  assert.equal(old.getSnapshot().isGenerating, false);
});

test("old-turn callbacks cannot leak into a later turn on the same controller", async () => {
  const callbacks = [];
  const controller = new ChatController({
    createSession: async () => assert.fail(),
    async stream(_payload, options) {
      callbacks.push(options.onEvent);
      if (callbacks.length === 1) throw new Error("disconnect");
      callbacks[0]({ event: "delta", data: { content: "LEAK" } });
      options.onEvent({ event: "start", data: { session_id: sessionA, mode: "PERSISTENT",
        request_id: uuid(20), user_message_id: uuid(21), assistant_message_id: uuid(22) } });
      options.onEvent({ event: "delta", data: { content: "correct" } });
      options.onEvent({ event: "done", data: { status: "COMPLETED", usage: null } });
      return {};
    },
  }, sessionA);
  await controller.submit("first");
  await controller.submit("second");
  assert.equal(controller.getSnapshot().messages.at(-1).content, "correct");
});

test("repeated backend request ID is rejected before it can overwrite history", async () => {
  const initial = { ...blankMessage, key: "saved", messageId: uuid(30), requestId: uuid(31),
    role: "assistant", content: "saved", status: "COMPLETED" };
  const controller = new ChatController({
    createSession: async () => assert.fail(),
    async stream(_payload, options) {
      options.onEvent({ event: "start", data: { session_id: sessionA, mode: "PERSISTENT",
        request_id: uuid(31), user_message_id: uuid(32), assistant_message_id: uuid(33) } });
    },
  }, sessionA, [initial]);
  await controller.submit("fixture");
  assert.equal(controller.getSnapshot().messages[0].content, "saved");
  assert.equal(controller.getSnapshot().messages.at(-1).status, "FAILED");
});

test("persisted turn guards IDs, role, terminal status and usage independently", async () => {
  for (const mutate of [
    message => ({ ...message, messageId: uuid(999) }),
    message => ({ ...message, requestId: uuid(998) }),
    message => ({ ...message, role: "user" }),
    message => ({ ...message, status: "STREAMING" }),
    message => ({ ...message, usage: { ...usage, output_tokens: 9, total_tokens: 12 } }),
  ]) {
    const mock = fixture();
    const services = { ...mock.services, loadHistory: async (...args) => {
      const history = await mock.read(...args);
      return history.map((message, index) => index === 1 ? mutate(message) : message);
    } };
    const controller = new ChatController(services, sessionA);
    await controller.submit("fixture");
    assert(controller.getSnapshot().persistenceError);
    assert.equal(controller.getSnapshot().messages.at(-1).status, "COMPLETED");
    assert.equal(controller.getSnapshot().isGenerating, false);
  }
});

test("backend-recomputed history citations reconcile without requiring SSE citations", async () => {
  const mock = fixture();
  const citation = { chunk_id: uuid(71), document_id: uuid(72), version_id: uuid(73), file_name: "fixture.md", page: null };
  const controller = new ChatController({ ...mock.services, loadHistory: async (...args) => {
    mock.stored.at(-1).citations = [citation];
    return mock.read(...args);
  } }, sessionA);
  await controller.submit("fixture");
  assert.equal(controller.getSnapshot().persistenceError, null);
  assert.deepEqual(controller.getSnapshot().messages.at(-1).citations, [citation]);
  assert.deepEqual(controller.getSnapshot().messages.at(-1).sources, []);
});

test("navigation during history verification aborts the read and ignores its late response", async () => {
  const mock = fixture();
  let release;
  let markRead;
  let signal;
  const reading = new Promise(resolve => { markRead = resolve; });
  const controller = new ChatController({ ...mock.services, loadHistory: async (_id, readSignal) => {
    signal = readSignal;
    markRead();
    return new Promise(resolve => { release = resolve; });
  } }, sessionA);
  const pending = controller.submit("fixture");
  await reading;
  assert.equal(controller.getSnapshot().isGenerating, true);
  assert.equal(await controller.submit("duplicate"), false);
  controller.dispose();
  assert.equal(signal.aborted, true);
  release([]);
  await pending;
  assert.equal(controller.getSnapshot().isGenerating, false);
  assert.equal(controller.getSnapshot().persistenceError, null);
  assert.equal(controller.getSnapshot().messages.at(-1).content, mock.lastLive().at(-1).content);
});
