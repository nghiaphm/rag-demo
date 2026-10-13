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
    throw new Error(`Unexpected runtime import: ${specifier}`);
  });
  return exports;
}

const { ChatController } = loadTypescriptModule("../lib/chat/controller.ts");
const { createSession } = loadTypescriptModule("../lib/api/sessions.ts");

const id = {
  session: "22222222-2222-4222-8222-222222222222",
  request: "11111111-1111-4111-8111-111111111111",
  user: "33333333-3333-4333-8333-333333333333",
  assistant: "44444444-4444-4444-8444-444444444444",
};

function event(event, data) {
  return { event, data };
}

test("creates a persistent session, rejects duplicate submit and completes exact delta text", async () => {
  let releaseSession;
  const created = new Promise(resolve => { releaseSession = resolve; });
  const observedPayloads = [];
  const contentSnapshots = [];
  let createSignal;
  let streamSignal;
  const usage = { input_tokens: 3, output_tokens: 4, total_tokens: 7 };
  const controller = new ChatController({
    createSession(signal) {
      createSignal = signal;
      return created;
    },
    async stream(payload, options) {
      observedPayloads.push(payload);
      streamSignal = options.signal;
      const events = [
        event("start", { sequence: 1, request_id: id.request, session_id: id.session, user_message_id: id.user, assistant_message_id: id.assistant, mode: "PERSISTENT" }),
        event("metadata", { sequence: 2, model: "fixture/model", sources: [] }),
        event("delta", { sequence: 3, content: "Xin " }),
        event("delta", { sequence: 4, content: "chào\n bạn" }),
        event("done", { sequence: 5, status: "COMPLETED", usage }),
      ];
      for (const item of events) await options.onEvent(item);
      return { terminal: events.at(-1) };
    },
  });
  controller.subscribe(() => {
    contentSnapshots.push(controller.getSnapshot().messages.at(-1)?.content ?? "");
  });

  const first = controller.submit("  Câu hỏi fixture  ");
  assert.equal(controller.getSnapshot().isGenerating, true);
  assert.equal(await controller.submit("Không được gửi"), false);
  assert.equal(observedPayloads.length, 0);

  releaseSession({ session_id: id.session });
  assert.equal(await first, true);

  const state = controller.getSnapshot();
  assert.equal(state.sessionId, id.session);
  assert.equal(state.isGenerating, false);
  assert.deepEqual(observedPayloads, [{ question: "Câu hỏi fixture", session_id: id.session }]);
  assert.equal(state.messages[0].messageId, id.user);
  assert.equal(state.messages[0].requestId, id.request);
  assert.equal(state.messages[0].status, "COMPLETED");
  assert.equal(state.messages[1].messageId, id.assistant);
  assert.equal(state.messages[1].requestId, id.request);
  assert.equal(state.messages[1].content, "Xin chào\n bạn");
  assert.equal(state.messages[1].status, "COMPLETED");
  assert.deepEqual(state.messages[1].usage, usage);
  assert.equal(createSignal, streamSignal);
  assert.equal(streamSignal.aborted, false);
  assert.equal(controller.stop(), false);
  assert(contentSnapshots.includes("Xin "));
  assert(contentSnapshots.includes("Xin chào\n bạn"));
});

test("reuses a route session and keeps a PARTIAL terminal message", async () => {
  let createCalls = 0;
  const controller = new ChatController({
    async createSession() {
      createCalls += 1;
      return { session_id: id.session };
    },
    async stream(_payload, options) {
      await options.onEvent(event("start", { sequence: 1, request_id: id.request, session_id: id.session, user_message_id: id.user, assistant_message_id: id.assistant, mode: "PERSISTENT" }));
      await options.onEvent(event("metadata", { sequence: 2, model: null, sources: [] }));
      await options.onEvent(event("delta", { sequence: 3, content: "Giữ  khoảng trắng " }));
      await options.onEvent(event("error", { sequence: 4, status: "PARTIAL", error: { code: "SAFE", message: "Chưa hoàn tất", retryable: true }, usage: null }));
      return {};
    },
  }, id.session);

  assert.equal(await controller.submit("fixture"), true);
  const assistant = controller.getSnapshot().messages[1];
  assert.equal(createCalls, 0);
  assert.equal(assistant.content, "Giữ  khoảng trắng ");
  assert.equal(assistant.status, "PARTIAL");
  assert.equal(assistant.error.code, "SAFE");
});

test("maps pre-terminal failures to FAILED and unlocks the next submit", async () => {
  let calls = 0;
  const controller = new ChatController({
    createSession: async () => ({ session_id: id.session }),
    async stream() {
      calls += 1;
      throw new Error("private transport detail");
    },
  });

  assert.equal(await controller.submit("first"), true);
  assert.equal(controller.getSnapshot().messages[1].status, "FAILED");
  assert.equal(controller.getSnapshot().messages[1].error.code, "CLIENT_STREAM_ERROR");
  assert.equal(await controller.submit("second"), true);
  assert.equal(calls, 2);
});

test("Stop aborts one in-flight stream and preserves partial content without retry", async () => {
  let streamCalls = 0;
  let streamSignal;
  let markStarted;
  const started = new Promise(resolve => { markStarted = resolve; });
  const controller = new ChatController({
    createSession: async () => assert.fail("existing session must be reused"),
    async stream(_payload, options) {
      streamCalls += 1;
      streamSignal = options.signal;
      await options.onEvent(event("start", { sequence: 1, request_id: id.request, session_id: id.session, user_message_id: id.user, assistant_message_id: id.assistant, mode: "PERSISTENT" }));
      await options.onEvent(event("metadata", { sequence: 2, model: null, sources: [] }));
      await options.onEvent(event("delta", { sequence: 3, content: "Nội dung  dở " }));
      markStarted();
      await new Promise((_, reject) => {
        options.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
      });
    },
  }, id.session);

  const pending = controller.submit("stop fixture");
  await started;
  assert.equal(controller.stop(), true);
  assert.equal(controller.stop(), false);
  await pending;

  const state = controller.getSnapshot();
  const assistant = state.messages[1];
  assert.equal(streamSignal.aborted, true);
  assert.equal(streamCalls, 1);
  assert.equal(state.isGenerating, false);
  assert.equal(assistant.content, "Nội dung  dở ");
  assert.equal(assistant.status, "PARTIAL");
  assert.equal(assistant.error.code, "RAG_STREAM_CANCELLED");
  assert.equal(assistant.error.retryable, false);
});

test("dispose aborts session creation and leaves no infinite loading state", async () => {
  let createCalls = 0;
  let streamCalls = 0;
  const controller = new ChatController({
    createSession(signal) {
      createCalls += 1;
      return new Promise((_, reject) => {
        signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
      });
    },
    async stream() {
      streamCalls += 1;
      return {};
    },
  });

  const pending = controller.submit("navigation fixture");
  controller.dispose();
  controller.dispose();
  await pending;

  const state = controller.getSnapshot();
  assert.equal(createCalls, 1);
  assert.equal(streamCalls, 0);
  assert.equal(state.isGenerating, false);
  assert.equal(state.messages[1].status, "FAILED");
  assert.equal(state.messages[1].error.code, "RAG_STREAM_CANCELLED");
});

test("disconnect after delta becomes PARTIAL, unlocks UI and does not retry", async () => {
  let streamCalls = 0;
  const controller = new ChatController({
    createSession: async () => assert.fail("existing session must be reused"),
    async stream(_payload, options) {
      streamCalls += 1;
      await options.onEvent(event("start", { sequence: 1, request_id: id.request, session_id: id.session, user_message_id: id.user, assistant_message_id: id.assistant, mode: "PERSISTENT" }));
      await options.onEvent(event("metadata", { sequence: 2, model: null, sources: [] }));
      await options.onEvent(event("delta", { sequence: 3, content: "partial\n " }));
      throw new Error("private disconnect detail");
    },
  }, id.session);

  await controller.submit("disconnect fixture");
  const state = controller.getSnapshot();
  assert.equal(streamCalls, 1);
  assert.equal(state.isGenerating, false);
  assert.equal(state.messages[1].content, "partial\n ");
  assert.equal(state.messages[1].status, "PARTIAL");
  assert.equal(state.messages[1].error.code, "CLIENT_STREAM_ERROR");
});

test("a validated terminal event is not overwritten by a later transport failure", async () => {
  const usage = { input_tokens: 1, output_tokens: 2, total_tokens: 3 };
  const controller = new ChatController({
    createSession: async () => assert.fail("existing session must be reused"),
    async stream(_payload, options) {
      await options.onEvent(event("start", { sequence: 1, request_id: id.request, session_id: id.session, user_message_id: id.user, assistant_message_id: id.assistant, mode: "PERSISTENT" }));
      await options.onEvent(event("metadata", { sequence: 2, model: null, sources: [] }));
      await options.onEvent(event("delta", { sequence: 3, content: "complete" }));
      await options.onEvent(event("done", { sequence: 4, status: "COMPLETED", usage }));
      throw new Error("transport closed after terminal");
    },
  }, id.session);

  await controller.submit("terminal fixture");
  const state = controller.getSnapshot();
  assert.equal(state.isGenerating, false);
  assert.equal(state.messages[1].status, "COMPLETED");
  assert.equal(state.messages[1].error, null);
  assert.deepEqual(state.messages[1].usage, usage);
});

test("POST /sessions uses an empty JSON body and validates the 201 response", async () => {
  const session = {
    session_id: id.session,
    title: "New chat",
    scope: { mode: "ALL_ACTIVE", document_ids: [] },
    user_id: null,
    created_at: "2026-10-13T00:00:00Z",
    updated_at: "2026-10-13T00:00:00Z",
  };
  const calls = [];
  const api = {
    async request(path, options) {
      calls.push([path, options]);
      return { status: 201, data: session, headers: new Headers() };
    },
  };
  assert.deepEqual(await createSession(api), session);
  assert.equal(calls[0][0], "/sessions");
  assert.equal(calls[0][1].method, "POST");
  assert.deepEqual(calls[0][1].json, {});

  await assert.rejects(
    createSession({ request: async () => ({ status: 200, data: session, headers: new Headers() }) }),
    /không khớp API contract/
  );
  await assert.rejects(
    createSession({ request: async () => ({ status: 201, data: { ...session, session_id: "invented" }, headers: new Headers() }) }),
    /không khớp API contract/
  );
});
