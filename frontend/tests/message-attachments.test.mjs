import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ts from "typescript";

const require = createRequire(import.meta.url), cache = new Map();
function load(relative) {
  if (cache.has(relative)) return cache.get(relative);
  const base = fileURLToPath(new URL(`../${relative}`, import.meta.url));
  const filename = fs.existsSync(base + ".tsx") ? base + ".tsx" : base + ".ts";
  const exports = {}; cache.set(relative, exports);
  new Function("exports", "require", ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText)(exports, name => {
    if (name === "react-markdown") return { default: ReactMarkdown };
    if (name === "remark-gfm") return { default: remarkGfm };
    return name.startsWith("@/") ? load(name.slice(2)) : require(name);
  });
  return exports;
}
const { ChatController } = load("lib/chat/controller");
const { historyMessageToViewMessage } = load("lib/sessions/history");
const { getDocumentPreview } = load("lib/api/documents");
const { validateUploadFile } = load("lib/documents/upload-validation");
const { ChatMessage } = load("components/chat/chat-message");
const id = n => `${String(n).padStart(8, "0")}-1111-4111-8111-111111111111`;
const attachment = { document_id: id(1), version_id: id(2), file_name: "phuongtien.txt" };

test("persistent chat sends only immutable references and retains server attachments after history reconciliation", async () => {
  let payload, controller;
  controller = new ChatController({
    createSession: async () => ({ session_id: id(3) }),
    stream: async (request, { onEvent }) => {
      payload = request;
      onEvent({ event: "start", data: { mode: "PERSISTENT", session_id: id(3), request_id: id(4), user_message_id: id(5), assistant_message_id: id(6), sequence: 1 } });
      assert.deepEqual(controller.getSnapshot().messages[0].attachments, [attachment]);
      onEvent({ event: "delta", data: { content: "Answer", sequence: 2 } });
      onEvent({ event: "done", data: { status: "COMPLETED", usage: null, sequence: 3 } });
      return {};
    },
    loadHistory: async () => controller.getSnapshot().messages.map(message => ({ ...message, key: `history:${message.messageId}`,
      ...(message.role === "user" ? { attachments: [{ ...attachment, file_name: "server-name.txt" }] } : {}) })),
  });
  await controller.submit("Question", [attachment]);
  assert.deepEqual(payload, { question: "Question", session_id: id(3), attachments: [{ document_id: id(1), version_id: id(2) }] });
  assert.equal(controller.getSnapshot().historyVerified, true);
  assert.equal(controller.getSnapshot().messages[0].attachments[0].file_name, "server-name.txt");
});

test("history mapping preserves attachment references; legacy user messages still render without chips", () => {
  const response = { message_id: id(5), session_id: id(3), role: "USER", content: "Old message", status: "COMPLETED", model: null, citations: [], usage: null, request_id: id(4) };
  const legacy = historyMessageToViewMessage(response);
  const render = message => renderToStaticMarkup(React.createElement(ChatMessage, { message, apiBaseUrl: "http://mock.invalid" }));
  assert(!render(legacy).includes("Xem tệp đính kèm"));
  const restored = historyMessageToViewMessage({ ...response, attachments: [attachment] });
  assert.deepEqual(restored.attachments, [attachment]);
  const markup = render(restored);
  assert(markup.includes("phuongtien.txt"));
  assert(markup.includes("Xem tệp đính kèm"));
  assert(!markup.includes("Gỡ phuongtien.txt"));
});

test("versioned preview uses exact GET identity and rejects mismatched or malformed responses", async () => {
  const response = { ...attachment, kind: "excel", text: null, truncated: false, sheets: [{ name: "Vehicles", columns: ["Name"], rows: [["Airplane"]], total_rows: 1, truncated: false }] };
  let call;
  const api = { request: async (path, options) => { call = { path, options }; return { status: 200, data: response }; } };
  const signal = new AbortController().signal;
  assert.deepEqual(await getDocumentPreview(api, id(1), id(2), signal), response);
  assert.equal(call.path, `/documents/${id(1)}/versions/${id(2)}/preview`);
  assert.equal(call.options.method, "GET"); assert.equal(call.options.signal, signal);
  for (const data of [{ ...response, version_id: id(9) }, { ...response, sheets: [{ ...response.sheets[0], rows: [[{}]] }] }]) {
    await assert.rejects(getDocumentPreview({ request: async () => ({ status: 200, data }) }, id(1), id(2)));
  }
});

test("XLSX validation matches server MIME/size limits and .xls remains explicitly unsupported", () => {
  const base = { name: "vehicles.xlsx", size: 128, type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" };
  for (const type of [base.type, "application/zip", "application/octet-stream", ""]) assert.equal(validateUploadFile({ ...base, type }), null);
  assert.match(validateUploadFile({ ...base, type: "text/plain" }), /MIME/);
  assert.match(validateUploadFile({ ...base, size: 10 * 1024 * 1024 + 1 }), /10 MiB/);
  assert(validateUploadFile({ ...base, name: "legacy.xls" }));
});
