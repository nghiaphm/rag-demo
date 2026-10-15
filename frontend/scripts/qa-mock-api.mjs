// Manual F7-02 QA only: loopback, in-memory fixtures, no backend/provider imports.
import { createServer } from "node:http";
import { randomUUID } from "node:crypto";
import fs from "node:fs";
import ts from "typescript";
import { pathToFileURL } from "node:url";
import { createDocumentLifecycle } from "./qa-document-lifecycle.mjs";

const exports = {};
new Function("exports", ts.transpileModule(fs.readFileSync(new URL("../fixtures/documents.ts", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText)(exports);
const timestamp = "2026-10-14T00:00:00Z";
const usage = { input_tokens: 10, output_tokens: 20, total_tokens: 30 };
const ids = ["aaaaaaaa-1111-4111-8111-111111111111", "bbbbbbbb-1111-4111-8111-111111111111"];
const makeSession = (session_id, title) => ({ session_id, title, scope: { mode: "ALL_ACTIVE", document_ids: [] },
  user_id: null, created_at: timestamp, updated_at: timestamp });
const source = { document_id: exports.documentFixtures[0].document_id,
  version_id: exports.documentFixtures[0].active_version_id, chunk_id: "cccccccc-1111-4111-8111-111111111111",
  file_name: "qa-" + "long-file-name-".repeat(12) + ".pdf", page: 0, chunk_index: 73 };
const citation = { document_id: source.document_id, version_id: source.version_id,
  chunk_id: source.chunk_id, file_name: source.file_name, page: source.page };
const markdown = "### Mock Markdown\n\n**Nguồn [1]**, lặp [1], ngoài phạm vi [99].\n\n> Trích dẫn trong quote [1]\n\n- Mục trong list [1]\n\n| Cột | Nội dung |\n| --- | --- |\n| [1] | " + "wide".repeat(80) + " |\n\n```js\n  const citation = '[1]';\n\tconst longLine = '" + "code".repeat(100) + "';\n```\n\n[Website](https://example.test)\n\n";
function message(session_id, sequence, role, content, request_id = randomUUID()) {
  return { message_id: randomUUID(), session_id, sequence, role, content, request_id, status: "COMPLETED",
    citations: role === "ASSISTANT" ? [citation] : [], model: role === "ASSISTANT" ? "qa/mock" : null,
    usage: role === "ASSISTANT" ? usage : null, error_code: null,
    created_at: timestamp, updated_at: timestamp, completed_at: timestamp };
}
const wait = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
const frame = (event, data) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

export function createQaMockServer({ delayMs = 600, deltaMs = 250 } = {}) {
  const documentLifecycle = createDocumentLifecycle(exports.documentFixtures, delayMs);
  const sessions = ids.map((id, index) => makeSession(id, `QA session ${index === 0 ? "A — long history" : "B — separate history"}`));
  const deleted = new Map();
  let manySeeded = false;
  const histories = new Map(ids.map((id, index) => [id, Array.from({ length: index ? 2 : 24 }, (_, n) =>
    message(id, n + 1, n % 2 ? "ASSISTANT" : "USER", n % 2 ? `${markdown}History ${index ? "B" : "A"} ${n}` : `QA question ${n}`))]));
  return createServer(async (request, response) => {
    const origin = request.headers.origin;
    if (origin && !/^http:\/\/(?:localhost|127\.0\.0\.1):\d+$/.test(origin)) {
      response.writeHead(403); response.end(); return;
    }
    if (origin) response.setHeader("Access-Control-Allow-Origin", origin);
    response.setHeader("Vary", "Origin");
    response.setHeader("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS");
    response.setHeader("Access-Control-Allow-Headers", "Content-Type");
    if (request.method === "OPTIONS") { response.writeHead(204); response.end(); return; }
    const json = (status, body) => { if (!response.destroyed) { response.writeHead(status, { "Content-Type": "application/json" }); response.end(JSON.stringify(body)); } };
    try {
      const url = new URL(request.url, "http://127.0.0.1");
      const scenario = /^\/(empty|error|slow|many|lifecycle)(?=\/|$)/.exec(url.pathname)?.[1];
      if (scenario === "many" && !manySeeded) {
        manySeeded = true;
        for (let n = 3; n <= 60; n++) {
          const session = makeSession(randomUUID(), `QA pagination ${n}`);
          sessions.push(session); histories.set(session.session_id, []);
        }
      }
      const path = scenario ? url.pathname.slice(scenario.length + 1) : url.pathname;
      const method = request.method;
      const chunks = [];
      let bytes = 0;
      for await (const chunk of request) {
        bytes += chunk.length;
        if (bytes > 2 * 1024 * 1024) { json(413, { detail: "QA fixture body limit" }); return; }
        chunks.push(chunk);
      }
      const body = Buffer.concat(chunks);
      await wait(scenario === "slow" ? delayMs * 4 : delayMs);
      if (scenario === "error") { json(503, { detail: "QA mock unavailable" }); return; }
      const page = items => {
        const offset = Number(url.searchParams.get("offset") ?? 0), limit = Number(url.searchParams.get("limit") ?? 50);
        return { items: items.slice(offset, offset + limit), offset, limit, total: items.length };
      };
      if (path === "/sessions" && method === "GET") { json(200, page(scenario === "empty" ? [] : sessions.filter(item => !deleted.has(item.session_id)))); return; }
      if (path === "/sessions" && method === "POST") {
        const session = makeSession(randomUUID(), "QA new chat"); sessions.unshift(session); histories.set(session.session_id, []);
        json(201, session); return;
      }
      const sessionRoute = /^\/sessions\/([^/]+)(\/messages)?$/.exec(path);
      if (sessionRoute && !sessionRoute[2] && ["PATCH", "DELETE"].includes(method)) {
        const session = sessions.find(item => item.session_id === sessionRoute[1]);
        if (!session) { json(404, { detail: "Not found" }); return; }
        if (method === "PATCH") {
          if (deleted.has(session.session_id)) { json(410, { detail: "Deleted" }); return; }
          const title = JSON.parse(body.toString()).title;
          if (typeof title !== "string" || !title.trim() || [...title].length > 200) { json(422, { detail: [] }); return; }
          session.title = title.trim(); session.updated_at = new Date().toISOString();
          sessions.sort((a, b) => b.updated_at.localeCompare(a.updated_at) || b.session_id.localeCompare(a.session_id));
          json(200, session); return;
        }
        const history = histories.get(session.session_id) ?? [];
        if (history.some(item => item.status === "STREAMING")) { json(409, { detail: "Active generation" }); return; }
        const already = deleted.has(session.session_id), deletedAt = deleted.get(session.session_id) ?? new Date().toISOString();
        deleted.set(session.session_id, deletedAt); histories.set(session.session_id, []);
        json(200, { session_id: session.session_id, status: "DELETED", deleted_messages: history.length,
          already_deleted: already, message_policy: "hard_deleted", tombstone_retained: true, deleted_at: deletedAt }); return;
      }
      if (sessionRoute && method === "GET") {
        if (deleted.has(sessionRoute[1])) { json(410, { detail: "Deleted" }); return; }
        const session = sessions.find(item => item.session_id === sessionRoute[1]);
        json(session ? 200 : 404, session ? sessionRoute[2] ? page(histories.get(session.session_id)) : session : { detail: "Not found" }); return;
      }
      if (scenario === "lifecycle" && await documentLifecycle({ path, method, url, headers: request.headers, body, json })) return;
      if (path === "/documents" && method === "GET") {
        const offset = Number(url.searchParams.get("offset") ?? 0), limit = Number(url.searchParams.get("limit") ?? 100);
        json(200, scenario === "empty" ? [] : exports.documentFixtures.slice(offset, offset + limit).map(document => {
          const info = { ...document }; delete info.versions; return info;
        })); return;
      }
      if (path.startsWith("/documents/") && method === "GET") {
        const document = exports.documentFixtures.find(item => item.document_id === path.split("/")[2]);
        json(document ? 200 : 404, document ?? { detail: "Not found" }); return;
      }
      if (path.startsWith("/documents/") && ["POST", "PUT", "DELETE"].includes(method)) {
        // Consume synthetic upload, persist nothing; exercise busy/error/confirmation UX only.
        await wait(delayMs * 4); json(503, { detail: "QA mutation failure — nothing persisted" }); return;
      }
      if (path === "/chat/stream" && method === "POST") {
        const payload = JSON.parse(body.toString());
        if (deleted.has(payload.session_id)) { json(410, { detail: "Deleted" }); return; }
        const stored = histories.get(payload.session_id);
        if (!stored) { json(404, { detail: "Not found" }); return; }
        if (typeof payload.question !== "string" || !payload.question.trim()) { json(422, { detail: [] }); return; }
        if (stored.some(item => item.status === "STREAMING")) { json(409, { detail: "Session generation conflict" }); return; }
        const requestId = randomUUID();
        const user = message(payload.session_id, stored.length + 1, "USER", payload.question, requestId);
        const assistant = message(payload.session_id, stored.length + 2, "ASSISTANT", "", requestId);
        assistant.status = "STREAMING"; assistant.completed_at = null;
        stored.push(user, assistant);
        response.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" });
        response.flushHeaders();
        let sequence = 1, terminal = false;
        response.once("close", () => {
          if (!terminal) { assistant.status = assistant.content ? "PARTIAL" : "FAILED"; assistant.error_code = "RAG_STREAM_CANCELLED"; assistant.completed_at = timestamp; }
        });
        response.write(frame("start", { sequence: sequence++, request_id: requestId, session_id: payload.session_id,
          user_message_id: user.message_id, assistant_message_id: assistant.message_id, mode: "PERSISTENT" }));
        response.write(frame("metadata", { sequence: sequence++, model: "qa/mock", sources: payload.question.includes("[no-metadata]") ? [] : [source] }));
        const parts = [markdown, ...Array.from({ length: 40 }, (_, n) => `Đoạn ${n + 1}: giữ  khoảng trắng\n\nNội dung fixture để cuộn và đọc [1].\n\n`)];
        for (const content of parts) {
          await wait(deltaMs);
          if (response.destroyed) return;
          assistant.content += content;
          response.write(frame("delta", { sequence: sequence++, content }));
          if (payload.question.includes("[disconnect]")) { response.end(); return; }
          if (payload.question.includes("[error]")) break;
        }
        terminal = true;
        assistant.completed_at = timestamp;
        if (payload.question.includes("[error]")) {
          assistant.status = "PARTIAL"; assistant.error_code = "RAG_STREAM_ERROR";
          response.end(frame("error", { sequence, status: "PARTIAL", error: { code: "RAG_STREAM_ERROR", message: "QA mock error", retryable: true }, usage }));
        } else {
          assistant.status = "COMPLETED";
          response.end(frame("done", { sequence, status: "COMPLETED", usage }));
        }
        return;
      }
      json(404, { detail: "QA route not implemented; no proxy fallback" });
    } catch { json(400, { detail: "Invalid QA request" }); }
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const server = createQaMockServer();
  server.listen(4011, "127.0.0.1", () => console.log("F7-02 MOCK ONLY: http://127.0.0.1:4011 — no backend/provider calls; Ctrl+C stops/reset fixtures."));
}
