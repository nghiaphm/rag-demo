import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import ts from "typescript";

// Load the actual TypeScript parser without adding a test runner or build artifact.
const filename = fileURLToPath(new URL("../lib/sse/parser.ts", import.meta.url));
const source = fs.readFileSync(filename, "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
});
const exports = {};
new Function("exports", "require", outputText)(exports, createRequire(path.resolve(filename)));
const { SSEParser, SSEParserError, parseSSE } = exports;
const frontend = path.resolve(path.dirname(filename), "../..");
const root = path.dirname(frontend);
const encoder = new TextEncoder();
const bytes = value => encoder.encode(value);
const uuid = {
  request: "11111111-1111-4111-8111-111111111111",
  session: "22222222-2222-4222-8222-222222222222",
  user: "33333333-3333-4333-8333-333333333333",
  assistant: "44444444-4444-4444-8444-444444444444",
  chunk: "55555555-5555-4555-8555-555555555555",
  document: "66666666-6666-4666-8666-666666666666",
  version: "77777777-7777-4777-8777-777777777777",
};
const frame = (event, data, ending = "\n") => `event: ${event}${ending}data: ${JSON.stringify(data)}${ending}${ending}`;
const fixtureData = {
  start: { sequence: 1, request_id: uuid.request, session_id: uuid.session, user_message_id: uuid.user, assistant_message_id: uuid.assistant, mode: "PERSISTENT" },
  metadata: { sequence: 2, model: "fixture/model", sources: [{ file_name: "tài liệu.md", document_id: uuid.document, version_id: uuid.version, chunk_id: uuid.chunk, chunk_index: 0, page: null }] },
  citation: { sequence: 3, citation: { chunk_id: uuid.chunk, document_id: uuid.document, version_id: uuid.version, file_name: "tài liệu.md", page: null } },
  delta: { sequence: 4, content: "Xin chào 🌏\n" },
  done: { sequence: 5, status: "COMPLETED", usage: { input_tokens: 2, output_tokens: 3, total_tokens: 5 } },
  error: { sequence: 5, status: "PARTIAL", error: { code: "RAG_STREAM_ERROR", message: "Không thể hoàn tất.", retryable: true }, usage: null },
};
const transcript = ["start", "metadata", "citation", "delta", "done"]
  .map(event => frame(event, fixtureData[event])).join("");
const known = records => records.map(record => {
  assert.equal(record.recognized, true);
  return record.event;
});
const isParserError = (kind, event = undefined) => error => {
  assert(error instanceof SSEParserError);
  assert.equal(error.kind, kind);
  if (event !== undefined) assert.equal(error.event, event);
  return true;
};

test("parses the backend LF transcript and preserves exact delta whitespace", () => {
  const events = known(parseSSE([bytes(transcript)]));
  assert.deepEqual(events.map(event => event.event), ["start", "metadata", "citation", "delta", "done"]);
  assert.equal(events[3].data.content, "Xin chào 🌏\n");
  assert.deepEqual(events[1].data.sources, fixtureData.metadata.sources);
});

test("parses deterministic frames emitted by backend encode_sse_event", () => {
  const python = process.env.PYTHON || (fs.existsSync(path.join(root, ".venv", "Scripts", "python.exe"))
    ? path.join(root, ".venv", "Scripts", "python.exe")
    : (fs.existsSync(path.join(root, ".venv", "bin", "python"))
        ? path.join(root, ".venv", "bin", "python")
        : "python"));
  const generated = spawnSync(python, ["-c", String.raw`
import socket, sys
sys.path.insert(0, 'backend')
def blocked(*args, **kwargs): raise RuntimeError('F1-03: network disabled')
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.create_connection = blocked
from app.api.schemas.chat_documents import ChatError, ChatResponseMode
from app.api.streaming.sse_schema import *
events = [
  SSEStartEvent(data=SSEStartData(sequence=1, request_id='11111111-1111-4111-8111-111111111111', session_id=None, user_message_id=None, assistant_message_id=None, mode=ChatResponseMode.STATELESS)),
  SSEMetadataEvent(data=SSEMetadataData(sequence=2, model=None, sources=[])),
  SSEDeltaEvent(data=SSEDeltaData(sequence=3, content='Xin chào 🌏')),
  SSEDoneEvent(data=SSEDoneData(sequence=4, usage=None)),
  SSEErrorEvent(data=SSEErrorData(sequence=4, status='PARTIAL', error=ChatError(code='FIXTURE', message='fixture', retryable=False), usage=None)),
]
sys.stdout.buffer.write(''.join(encode_sse_event(event) for event in events).encode('utf-8'))
`], { cwd: root, encoding: null });
  assert.equal(generated.status, 0, generated.stderr?.toString("utf8"));
  const events = known(parseSSE([new Uint8Array(generated.stdout)]));
  assert.deepEqual(events.map(event => event.event), ["start", "metadata", "delta", "done", "error"]);
  assert.equal(events[2].data.content, "Xin chào 🌏");
});

test("decodes UTF-8 correctly at every two-chunk byte split", () => {
  const encoded = bytes(frame("delta", fixtureData.delta));
  for (let index = 0; index <= encoded.length; index++) {
    const events = known(parseSSE([encoded.slice(0, index), encoded.slice(index)]));
    assert.equal(events.length, 1, `split ${index}`);
    assert.equal(events[0].data.content, fixtureData.delta.content, `split ${index}`);
  }
});

test("handles one-byte chunks without treating network chunks as events", () => {
  const chunks = [...bytes(transcript)].map(value => Uint8Array.of(value));
  const events = known(parseSSE(chunks));
  assert.equal(events.length, 5);
  assert.equal(events[4].data.sequence, 5);
});

test("handles CRLF split between chunks and mixed line endings", () => {
  const stream = frame("start", fixtureData.start, "\r\n") +
    `event: metadata\ndata: ${JSON.stringify(fixtureData.metadata)}\r\n\r\n`;
  const encoded = bytes(stream);
  const split = stream.indexOf("\r\n") + 1;
  const events = known(parseSSE([encoded.slice(0, split), encoded.slice(split)]));
  assert.deepEqual(events.map(event => event.event), ["start", "metadata"]);
});

test("emits multiple complete events from a single push", () => {
  const parser = new SSEParser();
  const events = known(parser.push(bytes(frame("delta", fixtureData.delta) + frame("done", fixtureData.done))));
  assert.deepEqual(events.map(event => event.event), ["delta", "done"]);
  assert.deepEqual(parser.finish(), []);
});

test("joins multiple data lines with LF before JSON parsing", () => {
  const stream = "event: delta\ndata: {\"sequence\":4,\ndata: \"content\":\"nhiều dòng\"}\n\n";
  const [event] = known(parseSSE([bytes(stream)]));
  assert.equal(event.data.content, "nhiều dòng");
});

test("supports comments, BOM, optional single space, and ignores id/retry/extensions", () => {
  const stream = `\uFEFF: heartbeat\nid: 42\nretry: 1000\nextension: ignored\nevent:delta\ndata:${JSON.stringify(fixtureData.delta)}\n\n`;
  const [event] = known(parseSSE([bytes(stream)]));
  assert.equal(event.event, "delta");
});

test("keeps unknown event JSON and default message events explicit", () => {
  const records = parseSSE([bytes("event: future\ndata: {\"version\":2}\n\ndata: [1,2]\n\n")]);
  assert.deepEqual(records, [
    { recognized: false, event: "future", data: { version: 2 } },
    { recognized: false, event: "message", data: [1, 2] },
  ]);
});

test("dispatches a valid final event at EOF without a blank delimiter", () => {
  const stream = `event: delta\ndata: ${JSON.stringify(fixtureData.delta)}`;
  const [event] = known(parseSSE([bytes(stream)]));
  assert.equal(event.event, "delta");
});

test("discards frames without data and lets the last event field win", () => {
  const stream = `event: start\n: no data\n\nevent: future\nevent: delta\ndata: ${JSON.stringify(fixtureData.delta)}\n\n`;
  const events = known(parseSSE([bytes(stream)]));
  assert.equal(events.length, 1);
  assert.equal(events[0].event, "delta");
});

test("accepts each known event payload, including FAILED error without deltas", () => {
  const failed = { ...fixtureData.error, sequence: 3, status: "FAILED" };
  const stream = ["start", "metadata", "citation", "delta", "done", "error"]
    .map(event => frame(event, event === "error" ? failed : fixtureData[event])).join("");
  assert.deepEqual(known(parseSSE([bytes(stream)])).map(event => event.event),
    ["start", "metadata", "citation", "delta", "done", "error"]);
});

test("validates events independently without enforcing transcript order", () => {
  const [event] = known(parseSSE([bytes(frame("done", { ...fixtureData.done, sequence: 9 }))]));
  assert.equal(event.event, "done");
  assert.equal(event.data.sequence, 9);
});

test("rejects malformed JSON without retaining raw payload", () => {
  const secret = "PRIVATE_SECRET";
  assert.throws(() => parseSSE([bytes(`event: delta\ndata: {broken:${secret}\n\n`)]), error => {
    isParserError("invalid_json", "delta")(error);
    assert(!error.message.includes(secret));
    assert(!JSON.stringify(error).includes(secret));
    return true;
  });
});

test("rejects invalid UTF-8 split across finish", () => {
  const parser = new SSEParser();
  assert.deepEqual(parser.push(Uint8Array.of(0x65, 0x76, 0x65, 0x6e, 0x74, 0x3a, 0x20, 0xc3)), []);
  assert.throws(() => parser.finish(), isParserError("invalid_utf8"));
});

test("rejects wrong known-event shapes, extra fields and model invariants", () => {
  const invalid = [
    ["delta", { sequence: 0, content: "x" }],
    ["delta", { sequence: 3, content: "x", extra: true }],
    ["done", { sequence: 3, status: "FAILED", usage: null }],
    ["done", { sequence: 3, status: "COMPLETED", usage: { input_tokens: 2, output_tokens: 3, total_tokens: 4 } }],
    ["start", { ...fixtureData.start, mode: "STATELESS" }],
    ["citation", { sequence: 3, citation: { ...fixtureData.citation.citation, page: -1 } }],
  ];
  for (const [event, data] of invalid) {
    assert.throws(() => parseSSE([bytes(frame(event, data))]), isParserError("invalid_contract", event));
  }
});

test("known event names require JSON even when data is empty", () => {
  assert.throws(() => parseSSE([bytes("event: delta\ndata:\n\n")]), isParserError("invalid_json", "delta"));
});

test("finish is idempotent and push after finish is rejected", () => {
  const parser = new SSEParser();
  assert.deepEqual(parser.finish(), []);
  assert.deepEqual(parser.finish(), []);
  assert.throws(() => parser.push(bytes(transcript)), isParserError("closed"));
});
