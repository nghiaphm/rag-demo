import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const chatFilename = fileURLToPath(new URL("../lib/api/chat.ts", import.meta.url));
const parserFilename = fileURLToPath(new URL("../lib/sse/parser.ts", import.meta.url));
const nativeRequire = createRequire(path.resolve(chatFilename));

function transpile(filename) {
  return ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
}

const parserExports = {};
new Function("exports", "require", transpile(parserFilename))(
  parserExports,
  nativeRequire
);
const chatExports = {};
new Function("exports", "require", transpile(chatFilename))(
  chatExports,
  specifier => specifier === "@/lib/sse/parser" ? parserExports : nativeRequire(specifier)
);
const { createChatStreamClient, ChatStreamClientError } = chatExports;

const baseUrl = "http://localhost:8000";
const encoder = new TextEncoder();
const uuid = {
  request: "11111111-1111-4111-8111-111111111111",
  session: "22222222-2222-4222-8222-222222222222",
  user: "33333333-3333-4333-8333-333333333333",
  assistant: "44444444-4444-4444-8444-444444444444",
  chunk: "55555555-5555-4555-8555-555555555555",
  document: "66666666-6666-4666-8666-666666666666",
  version: "77777777-7777-4777-8777-777777777777",
};
const source = {
  file_name: "fixture.md",
  source: null,
  document_id: uuid.document,
  version_id: uuid.version,
  chunk_id: uuid.chunk,
  chunk_index: 0,
  page: null,
};
const citation = {
  chunk_id: uuid.chunk,
  document_id: uuid.document,
  version_id: uuid.version,
  file_name: "fixture.md",
  page: null,
};
const frame = (event, data) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
const eventData = {
  start: { sequence: 1, request_id: uuid.request, session_id: uuid.session, user_message_id: uuid.user, assistant_message_id: uuid.assistant, mode: "PERSISTENT" },
  metadata: { sequence: 2, model: "fixture/model", sources: [source] },
  citation: { sequence: 3, citation },
  delta1: { sequence: 4, content: "Xin " },
  delta2: { sequence: 5, content: "chào\n bạn" },
  done: { sequence: 6, status: "COMPLETED", usage: { input_tokens: 3, output_tokens: 4, total_tokens: 7 } },
};
const successTranscript = frame("start", eventData.start)
  + frame("metadata", eventData.metadata)
  + frame("citation", eventData.citation)
  + frame("delta", eventData.delta1)
  + frame("delta", eventData.delta2)
  + frame("done", eventData.done);

function streamResponse(chunks, { status = 200, contentType = "text/event-stream; charset=utf-8" } = {}) {
  const body = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(typeof chunk === "string" ? encoder.encode(chunk) : chunk);
      controller.close();
    },
  });
  return new Response(body, { status, headers: { "Content-Type": contentType } });
}

function client(fetch) {
  return createChatStreamClient({ baseUrl, fetch });
}

function isStreamError(stage, kind, status = null) {
  return error => {
    assert(error instanceof ChatStreamClientError);
    assert.equal(error.stage, stage);
    assert.equal(error.kind, kind);
    assert.equal(error.status, status);
    return true;
  };
}

test("POSTs JSON and reconstructs validated events across one-byte network chunks", async () => {
  const bytes = encoder.encode(successTranscript);
  const observed = [];
  const result = await client(async (url, init) => {
    assert.equal(url, `${baseUrl}/chat/stream`);
    assert.equal(init.method, "POST");
    assert.equal(init.cache, "no-store");
    assert.equal(init.headers.Accept, "text/event-stream");
    assert.equal(init.headers["Content-Type"], "application/json");
    assert.equal(init.body, JSON.stringify({ question: "fixture", session_id: uuid.session }));
    return streamResponse(Array.from(bytes, byte => Uint8Array.of(byte)));
  }).stream(
    { question: "fixture", session_id: uuid.session },
    { onEvent: event => observed.push([event.event, event.data.sequence]) }
  );

  assert.deepEqual(observed, [["start", 1], ["metadata", 2], ["citation", 3], ["delta", 4], ["delta", 5], ["done", 6]]);
  assert.equal(result.start.data.request_id, uuid.request);
  assert.equal(result.start.data.session_id, uuid.session);
  assert.equal(result.start.data.user_message_id, uuid.user);
  assert.equal(result.start.data.assistant_message_id, uuid.assistant);
  assert.equal(result.answer, "Xin chào\n bạn");
  assert.equal(result.deltas.length, 2);
  assert.deepEqual(result.usage, eventData.done.usage);
});

test("network chunks and deltas remain independent units", async () => {
  const split = Math.floor(successTranscript.length / 2);
  const result = await client(async () => streamResponse([
    successTranscript.slice(0, split),
    successTranscript.slice(split),
  ])).stream({ question: "fixture" });
  assert.equal(result.events.length, 6);
  assert.deepEqual(result.deltas.map(event => event.data.content), ["Xin ", "chào\n bạn"]);
  assert.equal(result.answer, "Xin chào\n bạn");
});

test("valid FAILED and PARTIAL SSE errors are terminal results", async () => {
  const statelessStart = { ...eventData.start, session_id: null, user_message_id: null, assistant_message_id: null, mode: "STATELESS" };
  const failed = frame("start", statelessStart) + frame("error", {
    sequence: 2, status: "FAILED", error: { code: "RAG_STREAM_EMPTY", message: "Không thể hoàn tất.", retryable: true }, usage: null,
  });
  const failedResult = await client(async () => streamResponse([failed])).stream({ question: "fixture" });
  assert.equal(failedResult.terminal.event, "error");
  assert.equal(failedResult.terminal.data.status, "FAILED");
  assert.equal(failedResult.answer, "");

  const partial = frame("start", statelessStart)
    + frame("metadata", { ...eventData.metadata, sources: [], sequence: 2 })
    + frame("delta", { sequence: 3, content: "partial " })
    + frame("error", { sequence: 4, status: "PARTIAL", error: { code: "RAG_STREAM_ERROR", message: "Không thể hoàn tất.", retryable: true }, usage: null });
  const partialResult = await client(async () => streamResponse([partial])).stream({ question: "fixture" });
  assert.equal(partialResult.terminal.event, "error");
  assert.equal(partialResult.answer, "partial ");
});

test("HTTP failure is before_response and keeps only safe status/code", async () => {
  const body = { answer: "PRIVATE_SECRET", error: { code: "RAG_PIPELINE_ERROR", message: "PRIVATE_SECRET", retryable: true } };
  await assert.rejects(
    client(async () => new Response(JSON.stringify(body), { status: 502, headers: { "Content-Type": "application/json" } })).stream({ question: "PRIVATE_SECRET" }),
    error => {
      isStreamError("before_response", "http", 502)(error);
      assert.equal(error.code, "RAG_PIPELINE_ERROR");
      assert.equal(error.retryable, true);
      assert(!JSON.stringify(error).includes("PRIVATE_SECRET"));
      return true;
    }
  );
  await assert.rejects(
    client(async () => new Response(null, { status: 204 })).stream({ question: "fixture" }),
    isStreamError("before_response", "http", 204)
  );
});

test("pre-response network failure and cancellation are distinct", async () => {
  await assert.rejects(
    client(async () => { throw new TypeError("PRIVATE_SECRET"); }).stream({ question: "fixture" }),
    isStreamError("before_response", "network")
  );
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(
    client(async () => assert.fail("fetch must not run")).stream({ question: "fixture" }, { signal: controller.signal }),
    isStreamError("before_response", "aborted")
  );
});

test("HTTP 200 without an SSE body is a stream-stage invalid response", async () => {
  await assert.rejects(
    client(async () => new Response("{}", { headers: { "Content-Type": "application/json" } })).stream({ question: "fixture" }),
    isStreamError("stream", "invalid_response", 200)
  );
  await assert.rejects(
    client(async () => ({ ok: true, status: 200, headers: new Headers({ "Content-Type": "text/event-stream" }), body: null })).stream({ question: "fixture" }),
    isStreamError("stream", "invalid_response", 200)
  );
});

test("reader failure and cancellation after HTTP 200 are stream-stage errors", async () => {
  const broken = new ReadableStream({ pull() { throw new Error("PRIVATE_SECRET"); } });
  await assert.rejects(
    client(async () => new Response(broken, { headers: { "Content-Type": "text/event-stream" } })).stream({ question: "fixture" }),
    isStreamError("stream", "transport", 200)
  );

  const controller = new AbortController();
  const promise = client(async (_url, { signal }) => {
    const pending = new ReadableStream({
      start(streamController) {
        signal.addEventListener("abort", () => {
          streamController.error(new DOMException("Aborted", "AbortError"));
        }, { once: true });
      },
    });
    return new Response(pending, { headers: { "Content-Type": "text/event-stream" } });
  })
    .stream({ question: "fixture" }, { signal: controller.signal });
  controller.abort();
  await assert.rejects(promise, isStreamError("stream", "aborted", 200));
});

test("rejects unknown, malformed and invalid-contract events after HTTP 200", async () => {
  const fixtures = [
    "event: extension\ndata: {}\n\n",
    "event: start\ndata: {broken}\n\n",
    frame("start", { ...eventData.start, request_id: "invalid" }),
  ];
  for (const transcript of fixtures) {
    await assert.rejects(
      client(async () => streamResponse([transcript])).stream({ question: "fixture" }),
      isStreamError("stream", "protocol", 200)
    );
  }
});

test("rejects sequence gaps, invalid order and events after terminal", async () => {
  const statelessStart = { ...eventData.start, session_id: null, user_message_id: null, assistant_message_id: null, mode: "STATELESS" };
  const fixtures = [
    frame("start", statelessStart) + frame("metadata", { ...eventData.metadata, sequence: 3 }),
    frame("start", statelessStart) + frame("delta", { sequence: 2, content: "early" }),
    frame("start", statelessStart) + frame("error", { sequence: 2, status: "FAILED", error: { code: "SAFE", message: "safe", retryable: false }, usage: null }) + frame("metadata", { ...eventData.metadata, sequence: 3 }),
  ];
  for (const transcript of fixtures) {
    await assert.rejects(
      client(async () => streamResponse([transcript])).stream({ question: "fixture" }),
      isStreamError("stream", "protocol", 200)
    );
  }
});

test("rejects missing terminal and invalid terminal semantics", async () => {
  const statelessStart = { ...eventData.start, session_id: null, user_message_id: null, assistant_message_id: null, mode: "STATELESS" };
  const incomplete = frame("start", statelessStart) + frame("metadata", { ...eventData.metadata, sources: [], sequence: 2 });
  await assert.rejects(
    client(async () => streamResponse([incomplete])).stream({ question: "fixture" }),
    isStreamError("stream", "incomplete", 200)
  );
  const doneWithoutDelta = incomplete + frame("done", { sequence: 3, status: "COMPLETED", usage: null });
  await assert.rejects(
    client(async () => streamResponse([doneWithoutDelta])).stream({ question: "fixture" }),
    isStreamError("stream", "protocol", 200)
  );
  const wrongError = incomplete + frame("error", { sequence: 3, status: "PARTIAL", error: { code: "SAFE", message: "safe", retryable: false }, usage: null });
  await assert.rejects(
    client(async () => streamResponse([wrongError])).stream({ question: "fixture" }),
    isStreamError("stream", "protocol", 200)
  );
});

test("rejects citations absent from metadata and duplicate citations", async () => {
  const otherCitation = { ...citation, chunk_id: "88888888-8888-4888-8888-888888888888" };
  const missing = frame("start", eventData.start)
    + frame("metadata", eventData.metadata)
    + frame("citation", { sequence: 3, citation: otherCitation });
  await assert.rejects(
    client(async () => streamResponse([missing])).stream({ question: "fixture" }),
    isStreamError("stream", "protocol", 200)
  );
  const duplicate = frame("start", eventData.start)
    + frame("metadata", eventData.metadata)
    + frame("citation", eventData.citation)
    + frame("citation", { sequence: 4, citation });
  await assert.rejects(
    client(async () => streamResponse([duplicate])).stream({ question: "fixture" }),
    isStreamError("stream", "protocol", 200)
  );
});

test("consumer failure is distinct and base URL is validated", async () => {
  await assert.rejects(
    client(async () => streamResponse([successTranscript])).stream(
      { question: "fixture" },
      { onEvent: () => { throw new Error("PRIVATE_SECRET"); } }
    ),
    isStreamError("stream", "consumer", 200)
  );
  assert.throws(() => createChatStreamClient({ baseUrl: "file:///tmp" }), TypeError);
  assert.throws(() => createChatStreamClient({ baseUrl: "https://user:secret@example.com" }), TypeError);
});
