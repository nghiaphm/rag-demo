import assert from "node:assert/strict";
import fs from "node:fs";
import { test } from "node:test";
import ts from "typescript";

const exports = {};
new Function("exports", ts.transpileModule(fs.readFileSync(new URL("../lib/documents/text-preview.ts", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText)(exports);
const { readTextPreview, TEXT_PREVIEW_MAX_BYTES: limit } = exports;

test("preview preserves Vietnamese, line breaks and literal untrusted markup", async () => {
  const text = "Phương tiện\r\n  Xe máy\n<script>alert('x')</script>\n";
  assert.deepEqual(await readTextPreview(new Blob([text])), { text, truncated: false });
});

test("preview supports UTF-8 BOM and both UTF-16 BOM byte orders", async () => {
  const text = "Phương tiện\nXe";
  assert.equal((await readTextPreview(new Blob([Buffer.from([0xef, 0xbb, 0xbf]), text]))).text, text);
  const little = Buffer.concat([Buffer.from([0xff, 0xfe]), Buffer.from(text, "utf16le")]);
  const big = Buffer.from(little); big.swap16();
  for (const bytes of [little, big]) assert.equal((await readTextPreview(new Blob([bytes]))).text, text);
});

test("large preview reads only the bounded prefix and drops an incomplete trailing UTF-8 character", async () => {
  const text = "a".repeat(limit - 1) + "ệ" + "tail";
  let slice;
  const blob = new Blob([text]);
  const file = { size: blob.size, slice(start, end) { slice = [start, end]; return blob.slice(start, end); } };
  const result = await readTextPreview(file);
  assert.deepEqual(slice, [0, limit]);
  assert.equal(result.truncated, true);
  assert.equal(result.text, "a".repeat(limit - 1));
});

test("unsupported encoding, binary data and device read errors are explicit", async () => {
  for (const bytes of [Buffer.from([0xff, 0xff]), Buffer.from([0x61, 0, 0x62, 0])]) {
    await assert.rejects(readTextPreview(new Blob([bytes])), /encoding/);
  }
  await assert.rejects(readTextPreview({ size: 5, slice() { return { arrayBuffer: async () => { throw new Error("private path"); } }; } }),
    error => error.message.includes("Không thể đọc file") && !error.message.includes("private path"));
});
