import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import ts from "typescript";

// Load the actual TypeScript implementation without adding a runner or writing artifacts.
const filename = fileURLToPath(new URL("../lib/api/client.ts", import.meta.url));
const source = fs.readFileSync(filename, "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
});
const exports = {};
new Function("exports", "require", outputText)(exports, createRequire(path.resolve(filename)));
const { createApiClient, ApiClientError } = exports;
const baseUrl = "http://localhost:8000";
const jsonResponse = (data, status = 200) => new Response(JSON.stringify(data), {
  status, headers: { "Content-Type": "application/json" },
});
const fakeClient = handler => createApiClient({ baseUrl, fetch: handler });
const isError = (kind, status = null) => error => {
  assert(error instanceof ApiClientError);
  assert.equal(error.kind, kind);
  assert.equal(error.status, status);
  return true;
};
const pendingFetch = async (_url, { signal }) => new Promise((_resolve, reject) => {
  signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
});

test("2xx JSON retains status, headers, defaults and request JSON", async () => {
  const client = fakeClient(async (url, init) => {
    assert.equal(url, `${baseUrl}/sessions`);
    assert.equal(init.method, "POST");
    assert.equal(init.cache, "no-store");
    assert.equal(init.headers.get("Content-Type"), "application/json");
    assert.equal(init.headers.get("Accept"), "application/json");
    assert.equal(init.headers.get("X-Test"), "kept");
    assert.equal(init.body, '{"title":"demo"}');
    return jsonResponse({ session_id: "fixture" }, 201);
  });
  const result = await client.request("/sessions", { method: "POST", json: { title: "demo" }, headers: { "X-Test": "kept" } });
  assert.equal(result.status, 201);
  assert.deepEqual(result.data, { session_id: "fixture" });
  assert.equal(result.headers.get("Content-Type"), "application/json");
});

test("202, empty 204 and JSON null remain distinct", async () => {
  assert.equal((await fakeClient(async () => jsonResponse({ cleanup_pending: true }, 202)).request("/documents/fixture")).status, 202);
  assert.equal((await fakeClient(async () => new Response(null, { status: 204 })).request("/fixture")).data, undefined);
  assert.equal((await fakeClient(async () => jsonResponse(null)).request("/fixture")).data, null);
});

test("multipart preserves FormData and lets fetch generate its boundary", async () => {
  const form = new FormData();
  form.append("file", new Blob(["fixture"]), "fixture.txt");
  await fakeClient(async (_url, init) => {
    assert.equal(init.body, form);
    assert.equal(init.headers.has("Content-Type"), false);
    return jsonResponse({ activated: true }, 201);
  }).request("/documents/upload", { method: "POST", body: form });
});

for (const status of [400, 404, 409, 410, 429, 500, 503]) {
  test(`HTTP ${status} preserves status, makes one attempt and omits raw detail`, async () => {
    let calls = 0;
    const client = fakeClient(async () => { calls++; return jsonResponse({ detail: "PRIVATE_SECRET<script>" }, status); });
    await assert.rejects(client.request("/fixture"), error => {
      isError("http", status)(error);
      assert(!JSON.stringify(error).includes("PRIVATE_SECRET"));
      assert(!error.message.includes("PRIVATE_SECRET"));
      return true;
    });
    assert.equal(calls, 1);
  });
}

test("422 validation input/ctx and arbitrary message are not retained", async () => {
  const payload = { detail: [{ loc: ["body", "question"], msg: "PRIVATE_SECRET", type: "value_error", input: "PRIVATE_SECRET", ctx: { error: "PRIVATE_SECRET" } }] };
  await assert.rejects(fakeClient(async () => jsonResponse(payload, 422)).request("/fixture"), error => {
    isError("http", 422)(error);
    assert(!JSON.stringify(error).includes("PRIVATE_SECRET"));
    return true;
  });
});

test("502 ChatResponse error keeps safe code/retryability, not answer or server message", async () => {
  const payload = { status: "FAILED", answer: "PRIVATE_SECRET", error: { code: "RAG_PIPELINE_ERROR", message: "PRIVATE_SECRET", retryable: true } };
  await assert.rejects(fakeClient(async () => jsonResponse(payload, 502)).request("/chat", { method: "POST", json: { question: "fixture" } }), error => {
    isError("http", 502)(error);
    assert.equal(error.code, "RAG_PIPELINE_ERROR");
    assert.equal(error.retryable, true);
    assert(!JSON.stringify(error).includes("PRIVATE_SECRET"));
    return true;
  });
});

test("malformed/HTML/empty failure bodies still preserve HTTP status", async () => {
  for (const body of ["<html>PRIVATE_SECRET</html>", "{broken", ""]) {
    await assert.rejects(fakeClient(async () => new Response(body, { status: 502 })).request("/fixture"), isError("http", 502));
  }
});

test("invalid JSON success differs from HTTP error and network failure", async () => {
  await assert.rejects(fakeClient(async () => new Response("<html>oops</html>")).request("/fixture"), isError("invalid_response", 200));
  await assert.rejects(fakeClient(async () => { throw new TypeError("PRIVATE_SECRET"); }).request("/fixture"), error => {
    isError("network")(error);
    assert(!error.message.includes("PRIVATE_SECRET"));
    return true;
  });
});

test("body read failure retains received status", async () => {
  for (const status of [200, 503]) {
    await assert.rejects(fakeClient(async () => ({ status, ok: status === 200, text: async () => { throw new Error("broken transport"); } })).request("/fixture"), isError(status === 200 ? "network" : "http", status));
  }
});

test("already-aborted caller signal does not issue fetch", async () => {
  const controller = new AbortController();
  controller.abort("PRIVATE_SECRET");
  await assert.rejects(fakeClient(async () => assert.fail("fetch must not be called")).request("/fixture", { signal: controller.signal }), isError("aborted"));
});

test("caller cancellation and timeout are distinct", async () => {
  const controller = new AbortController();
  const promise = fakeClient(pendingFetch).request("/fixture", { signal: controller.signal });
  controller.abort();
  await assert.rejects(promise, isError("aborted"));
  await assert.rejects(fakeClient(pendingFetch).request("/fixture", { timeoutMs: 5 }), isError("timeout"));
});

test("timeout covers body reads and preserves received status", async () => {
  const client = fakeClient(async (_url, { signal }) => ({ status: 200, ok: true,
    text: async () => pendingFetch(null, { signal }),
  }));
  await assert.rejects(client.request("/fixture", { timeoutMs: 5 }), isError("timeout", 200));
});

test("abort listeners are removed on success and failure", async () => {
  for (const status of [200, 503]) {
    const controller = new AbortController();
    let added = 0, removed = 0;
    const signal = { aborted: false,
      addEventListener(...args) { added++; controller.signal.addEventListener(...args); },
      removeEventListener(...args) { removed++; controller.signal.removeEventListener(...args); },
    };
    const promise = fakeClient(async () => jsonResponse({}, status)).request("/fixture", { signal });
    if (status === 200) await promise;
    else await assert.rejects(promise, isError("http", status));
    assert.equal(added, 1); assert.equal(removed, 1);
  }
});

test("explicit base path/query are preserved and invalid configuration is rejected", async () => {
  await createApiClient({ baseUrl: `${baseUrl}/api/`, fetch: async url => {
    assert.equal(url, `${baseUrl}/api/sessions?offset=0&limit=50`);
    return jsonResponse({});
  } }).request("/sessions?offset=0&limit=50", { timeoutMs: 0 });
  assert.throws(() => createApiClient({ baseUrl: "file:///tmp" }), TypeError);
  assert.throws(() => createApiClient({ baseUrl, timeoutMs: -1 }), TypeError);
  await assert.rejects(fakeClient(async () => assert.fail()).request("https://other.example"), TypeError);
  await assert.rejects(fakeClient(async () => assert.fail()).request("/fixture", { json: {}, body: "ambiguous" }), TypeError);
});
