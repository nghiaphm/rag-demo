import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const require = createRequire(import.meta.url);
const cache = new Map();
function load(relative) {
  if (cache.has(relative)) return cache.get(relative);
  const base = fileURLToPath(new URL(`../${relative}`, import.meta.url));
  const filename = fs.existsSync(`${base}.tsx`) ? `${base}.tsx` : `${base}.ts`;
  const exports = {};
  cache.set(relative, exports);
  new Function("exports", "require", ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText)(exports, specifier => specifier.startsWith("@/") ? load(specifier.slice(2)) : require(specifier));
  return exports;
}
const { validateUploadFile, DOCUMENT_UPLOAD_EXTENSIONS } = load("lib/documents/upload-validation");
const { uploadDocument } = load("lib/api/documents");
const { createApiClient, ApiClientError } = load("lib/api/client");
const { UploadController } = load("lib/documents/upload-controller");
const { UploadFeedback } = load("components/documents/document-upload");
const id = n => `${n.toString(16).padStart(8, "0")}-1111-4111-8111-111111111111`;
const receipt = overrides => ({ document_id: id(1), version_id: id(2), job_id: id(3), file_name: "fixture.txt",
  num_chunks: 2, status: "INDEXED", activated: true, ...overrides });
const file = () => new File(["Fixture content"], "fixture.txt", { type: "text/plain" });
const render = state => renderToStaticMarkup(React.createElement(UploadFeedback, { state }));

test("file validation follows backend extensions and nonempty size without a made-up maximum or MIME check", () => {
  for (const extension of DOCUMENT_UPLOAD_EXTENSIONS) assert.equal(validateUploadFile({ name: `fixture${extension.toUpperCase()}`, size: 1 }), null);
  for (const selected of [null, { name: "fixture.txt", size: 0 }, { name: "fixture.exe", size: 100 },
    { name: "../fixture.txt", size: 1 }, { name: "C:\\fixture.txt", size: 1 }, { name: ".pdf", size: 1 }]) {
    assert(validateUploadFile(selected));
  }
  assert.equal(validateUploadFile({ name: "large.pdf", size: 2 ** 32 }), null);
  assert.equal(validateUploadFile(new File(["fixture"], "fixture.md", { type: "application/octet-stream" })), null);
});

test("multipart upload uses exact file field, POST, 201 and extended ingestion wait deadline", async () => {
  const selected = file();
  let observed;
  const result = await uploadDocument({ request: async (route, options) => { observed = [route, options];
    return { status: 201, data: receipt(), headers: new Headers() }; } }, selected);
  assert.equal(observed[0], "/documents/upload");
  assert.equal(observed[1].method, "POST");
  assert.equal(observed[1].timeoutMs, 300_000);
  assert(observed[1].body instanceof FormData);
  assert.deepEqual([...observed[1].body.keys()], ["file"]);
  assert.equal(observed[1].body.get("file").name, selected.name);
  assert.equal(await observed[1].body.get("file").text(), await selected.text());
  assert.equal(observed[1].json, undefined);
  assert.equal(observed[1].headers, undefined);
  assert.equal(result.status, "INDEXED");
});

test("real REST wrapper leaves multipart boundary to browser and performs one request only", async () => {
  let calls = 0;
  const api = createApiClient({ baseUrl: "http://mock.invalid", fetch: async (url, init) => {
    calls++;
    assert.equal(url, "http://mock.invalid/documents/upload");
    assert.equal(init.headers.get("Content-Type"), null);
    assert(init.body instanceof FormData);
    return Response.json(receipt(), { status: 201 });
  } });
  await uploadDocument(api, file());
  assert.equal(calls, 1);
});

test("invalid file never POSTs and malformed or non-201 success is not declared successful", async () => {
  await assert.rejects(uploadDocument({ request: () => assert.fail("invalid file must not POST") }, new File([], "empty.txt")), TypeError);
  for (const response of [{ status: 200, data: receipt() }, { status: 201, data: receipt({ activated: "true" }) },
    { status: 201, data: receipt({ status: "UNKNOWN" }) }, { status: 201, data: receipt({ num_chunks: -1 }) }]) {
    await assert.rejects(uploadDocument({ request: async () => response }, file()), TypeError);
  }
});

test("optional response status stays unknown, not an invented INDEXED default", async () => {
  const value = receipt();
  delete value.status;
  const result = await uploadDocument({ request: async () => ({ status: 201, data: value }) }, file());
  assert.equal(result.status, undefined);
  assert.match(render({ phase: "received", result, error: null }), /chưa cung cấp trạng thái/);
  assert(!render({ phase: "received", result, error: null }).includes("được index và kích hoạt"));
});

test("controller locks duplicate submit and file replacement until real response arrives", async () => {
  let release;
  let calls = 0;
  const controller = new UploadController({ upload: async () => { calls++; return new Promise(resolve => { release = resolve; }); } });
  controller.choose(file());
  const pending = controller.submit();
  assert.equal(controller.getSnapshot().phase, "submitting");
  assert.equal(controller.getSnapshot().result, null);
  assert.equal(await controller.submit(), null);
  controller.choose(new File(["new"], "other.md"));
  assert.equal(controller.getSnapshot().file.name, "fixture.txt");
  release(receipt());
  await pending;
  assert.equal(controller.getSnapshot().result.status, "INDEXED");
  assert.equal(await controller.submit(), null);
  assert.equal(calls, 1);
});

test("UPLOADED/PROCESSING/FAILED receipts preserve actual status and do not claim activation success", async () => {
  for (const status of ["UPLOADED", "PROCESSING", "FAILED"]) {
    const controller = new UploadController({ upload: async () => receipt({ status, activated: false }) });
    controller.choose(file());
    await controller.submit();
    assert.equal(controller.getSnapshot().result.status, status);
    assert.equal(controller.getSnapshot().phase, "received");
    assert(!render(controller.getSnapshot()).includes("được index và kích hoạt"));
  }
});

test("HTTP failures keep safe error without fictional persisted FAILED status or automatic resubmit", async () => {
  let calls = 0;
  const controller = new UploadController({ upload: async () => { calls++; throw new ApiClientError("http", "private", 400); } });
  controller.choose(file());
  await controller.submit();
  assert.equal(controller.getSnapshot().phase, "error");
  assert.equal(controller.getSnapshot().result, null);
  assert(!controller.getSnapshot().error.includes("private"));
  assert.equal(await controller.submit(), null);
  assert.equal(calls, 1);
});

test("timeout/network/server/malformed-response failures are uncertain and require manual recovery", async () => {
  for (const error of [new ApiClientError("timeout", "private"), new ApiClientError("network", "private"),
    new ApiClientError("http", "private", 500), new TypeError("private malformed response")]) {
    const controller = new UploadController({ upload: async () => { throw error; } });
    controller.choose(file());
    await controller.submit();
    assert.equal(controller.getSnapshot().phase, "uncertain");
    assert.equal(controller.getSnapshot().result, null);
    assert.match(controller.getSnapshot().error, /làm mới danh sách/);
    assert.equal(await controller.submit(), null);
  }
});

test("navigation abort releases pending state without promising cancellation of backend ingestion", async () => {
  const controller = new UploadController({ upload: async (_file, signal) => new Promise((_, reject) => {
    signal.addEventListener("abort", () => reject(new ApiClientError("aborted", "private")), { once: true });
  }) });
  controller.choose(file());
  const pending = controller.submit();
  controller.dispose();
  await pending;
  assert.equal(controller.getSnapshot().phase, "uncertain");
  assert.equal(controller.getSnapshot().result, null);
});

test("stop waiting ignores a late successful response even if transport does not honor abort", async () => {
  let release;
  const controller = new UploadController({ upload: async () => new Promise(resolve => { release = resolve; }) });
  controller.choose(file());
  const pending = controller.submit();
  controller.dispose();
  assert.equal(controller.getSnapshot().phase, "uncertain");
  release(receipt());
  assert.equal(await pending, null);
  assert.equal(controller.getSnapshot().result, null);
  assert.equal(controller.getSnapshot().phase, "uncertain");
});

test("pending UI has no progress percentage or fabricated backend state; indexed activation is explicit", () => {
  const pending = render({ phase: "submitting", result: null, error: null });
  assert.match(pending, /Chưa có kết quả xác nhận/);
  assert(!pending.includes("progressbar"));
  assert(!pending.includes("%"));
  assert(!pending.includes("Đã tải lên"));
  assert.match(render({ phase: "received", result: receipt(), error: null }), /được index và kích hoạt/);
  assert(!render({ phase: "received", result: receipt({ activated: false }), error: null }).includes("được index và kích hoạt"));
});

test("offline backend filename contract matches frontend validation for supported/invalid fixtures", () => {
  const root = fileURLToPath(new URL("../../", import.meta.url));
  const python = process.env.PYTHON || (fs.existsSync(path.join(root, ".venv", "Scripts", "python.exe"))
    ? path.join(root, ".venv", "Scripts", "python.exe")
    : (fs.existsSync(path.join(root, ".venv", "bin", "python"))
        ? path.join(root, ".venv", "bin", "python")
        : "python"));
  const names = ["fixture.pdf", "fixture.MD", "fixture.markdown", "fixture.txt", "fixture.xlsx", "fixture.exe", ".pdf", "../fixture.txt"];
  const run = spawnSync(python, ["-c", String.raw`
import json, socket, sys
sys.path.insert(0, 'backend')
def blocked(*args, **kwargs):
    raise RuntimeError('F6-02: network disabled')
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.create_connection = blocked
from fastapi import UploadFile, HTTPException
from app.api.routes.documents import _validated_file_name
from app.rag.loaders.files import SUPPORTED_EXTENSIONS
values = []
for name in json.loads(sys.argv[1]):
    try:
        _validated_file_name(UploadFile(filename=name, file=None))
        values.append(True)
    except HTTPException:
        values.append(False)
print(json.dumps({'extensions': sorted(SUPPORTED_EXTENSIONS), 'valid': values}))
`, JSON.stringify(names)], { cwd: root, encoding: "utf8" });
  assert.equal(run.status, 0, run.stderr);
  const backend = JSON.parse(run.stdout);
  assert.deepEqual(backend.extensions, [...DOCUMENT_UPLOAD_EXTENSIONS].sort());
  assert.deepEqual(backend.valid, names.map(name => validateUploadFile({ name, size: 1 }) === null));
});
