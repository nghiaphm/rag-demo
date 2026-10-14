import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const root = fileURLToPath(new URL("../../", import.meta.url));
const source = fs.readFileSync(new URL("../lib/chat/source-mapper.ts", import.meta.url), "utf8");
const exports = {};
new Function("exports", ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText)(exports);
const { mapMessageSources, resolveCitationOrdinal } = exports;
const id = n => `${n.toString(16).padStart(8, "0")}-1111-4111-8111-111111111111`;
const candidate = (n, overrides = {}) => ({ document_id: id(10), version_id: id(20), chunk_id: id(n),
  file_name: "guide.pdf", page: 0, chunk_index: 98 - n, ...overrides });
const message = (content, sources, overrides = {}) => ({ key: "session-a:assistant-a", messageId: id(100),
  role: "assistant", content, sources, ...overrides });

test("sparse markers use metadata positions, not chunk_index or citation order", () => {
  const sources = [candidate(1, { chunk_index: 900 }), candidate(2, { chunk_index: 0 }), candidate(3, { chunk_index: 1 })];
  const mapped = mapMessageSources(message("Nguồn [3], rồi [1].", sources, { citations: [sources[2], sources[0]] }));
  assert.deepEqual(mapped.citations.map(s => [s.ordinal, s.chunk_id]), [[3, id(3)], [1, id(1)]]);
});

test("repeated markers preserve offsets but deduplicate source cards in first-mention order", () => {
  const content = "A [2] B [1] C [2] [01]";
  const mapped = mapMessageSources(message(content, [candidate(1), candidate(2)]));
  assert.deepEqual(mapped.references.map(r => r.ordinal), [2, 1, 2, 1]);
  assert.deepEqual(mapped.citations.map(s => s.ordinal), [2, 1]);
  for (const ref of mapped.references) assert.equal(content.slice(ref.start, ref.end), ref.marker);
});

test("zero, out-of-range and unsafe ordinals never resolve to a made-up source", () => {
  const mapped = mapMessageSources(message("[0] [2] [999999999999999999999999] [1]", [candidate(1)]));
  assert.deepEqual(mapped.references.map(r => r.status), ["unavailable", "unavailable", "unavailable", "resolved"]);
  assert.deepEqual(mapped.references.slice(0, 3).map(r => r.reason), ["invalid_ordinal", "out_of_range", "invalid_ordinal"]);
  assert.equal(mapped.citations.length, 1);
  for (const ordinal of [-1, 0, 1.5, NaN, Infinity]) assert.equal(resolveCitationOrdinal(message("", []), ordinal).status, "unavailable");
});

test("two assistant messages with the same ordinal resolve only their own metadata", () => {
  const a = mapMessageSources(message("[1]", [candidate(1)]));
  const b = mapMessageSources(message("[1]", [candidate(2, { document_id: id(11), version_id: id(21) })],
    { key: "session-b:assistant-b", messageId: id(101) }));
  assert.equal(a.citations[0].chunk_id, id(1));
  assert.equal(b.citations[0].chunk_id, id(2));
  assert.equal(b.messageKey, "session-b:assistant-b");
  assert.equal(b.messageId, id(101));
  const refreshedA = mapMessageSources(message("[1]", []));
  assert.equal(refreshedA.references[0].reason, "missing_metadata");
});

test("history citations without ordered sources cannot restore citation ordinals", () => {
  const mapped = mapMessageSources(message("[2] [1]", [], { citations: [candidate(9), candidate(8)] }));
  assert.equal(mapped.citations.length, 0);
  assert(mapped.references.every(r => r.reason === "missing_metadata"));
});

test("ineligible metadata never shifts later source positions", () => {
  for (const overrides of [{ chunk_id: null }, { document_id: "invented" }, { version_id: undefined },
    { page: -1 }, { page: 0.5 }, { page: true }, { file_name: "   " }]) {
    const mapped = mapMessageSources(message("[1] [2]", [candidate(1, overrides), candidate(2)]));
    assert.equal(mapped.references[0].reason, "ineligible_source");
    assert.equal(mapped.citations[0].ordinal, 2);
    assert.equal(mapped.citations[0].chunk_id, id(2));
  }
});

test("duplicate candidate chunks keep ordinal resolution but deduplicate citations like backend", () => {
  const mapped = mapMessageSources(message("[2] [1]", [candidate(1), candidate(1)]));
  assert.deepEqual(mapped.references.map(r => r.source.ordinal), [2, 1]);
  assert.equal(mapped.citations.length, 1);
  assert.equal(mapped.citations[0].ordinal, 2);
});

test("PDF page remains zero-based; display number adds one only for a known PDF", () => {
  for (const page of [0, 3]) {
    const mapped = mapMessageSources(message("[1]", [candidate(1, { page, file_name: "  GUIDE.PDF  " })]));
    assert.equal(mapped.citations[0].page, page);
    assert.equal(mapped.citations[0].pdf_page_number, page + 1);
    assert.equal(mapped.citations[0].file_name, "GUIDE.PDF");
  }
  for (const overrides of [{ page: null }, { file_name: null }, { file_name: "notes.txt", page: undefined }, { file_name: "book.xlsx", page: 2 }]) {
    assert.equal(mapMessageSources(message("[1]", [candidate(1, overrides)])).citations[0].pdf_page_number, null);
  }
});

test("mapper creates no href/download/preview URL from server paths or model text", () => {
  const mapped = mapMessageSources(message("[1] citation_id=invented", [candidate(1, { source: "C:/private/guide.pdf" })]));
  assert.deepEqual(Object.keys(mapped.citations[0]).sort(), ["ordinal", "document_id", "version_id", "chunk_id", "file_name", "page", "pdf_page_number"].sort());
  assert(!JSON.stringify(mapped).includes("C:/private"));
  assert.deepEqual(mapMessageSources(message("UUID text without marker", [candidate(1)])).citations, []);
});

test("user messages never borrow assistant citation metadata", () => {
  const user = message("[1]", [candidate(1)], { role: "user" });
  assert.deepEqual(mapMessageSources(user).references, []);
  assert.equal(resolveCitationOrdinal(user, 1).reason, "not_assistant");
});

test("offline backend fixture verifies ordinal parity and actual PDF loader zero-based pages", () => {
  const result = spawnSync(path.join(root, ".venv", "Scripts", "python.exe"), ["-c", String.raw`
import json, socket, sys, tempfile
from pathlib import Path
sys.path.insert(0, 'backend')
def blocked(*args, **kwargs):
    raise RuntimeError('F5-01: network disabled')
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.create_connection = blocked
from app.citation_mapping import map_verified_citations
from app.rag.loader import load_document
from pypdf import PdfWriter
with tempfile.TemporaryDirectory() as folder:
    pdf = Path(folder) / 'fixture.pdf'
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_blank_page(width=72, height=72)
    writer.write(str(pdf))
    pages = [document.metadata['page'] for document in load_document(pdf)]
sources = json.loads(sys.argv[1])
answer = sys.argv[2]
print(json.dumps({'pages': pages, 'citations': map_verified_citations(answer, sources)}))
`, JSON.stringify([candidate(1), candidate(2), candidate(3)]), "[3] [1] [3] [0] [9]"], { cwd: root, encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const backend = JSON.parse(result.stdout);
  assert.deepEqual(backend.pages, [0, 1]);
  const mapped = mapMessageSources(message("[3] [1] [3] [0] [9]", [candidate(1), candidate(2), candidate(3)]));
  assert.deepEqual(mapped.citations.map(s => ({
    chunk_id: s.chunk_id, document_id: s.document_id, version_id: s.version_id,
    file_name: s.file_name, page: s.page,
  })), backend.citations);
});
