// Read-only local F7-03-05 acceptance. No lifespan, mutation, providers, or logs
// of session/document data. Fails instead of silently replacing missing checks.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const backend = "http://127.0.0.1:8000";
const request = (route, options = {}) => fetch(`${backend}${route}`, { ...options, redirect: "error", signal: AbortSignal.timeout(10000) });
const source = spawnSync(path.join(root, ".venv", "Scripts", "python.exe"), ["-c", String.raw`
import json, socket, sys
sys.path.insert(0, 'backend')
def blocked(*args, **kwargs):
    raise RuntimeError('Functional QA: external network disabled')
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.create_connection = blocked
from app.main import app
print(json.dumps(app.openapi()))
`], { cwd: root, encoding: "utf8", maxBuffer: 5 * 1024 * 1024 });
assert.equal(source.status, 0, "Offline OpenAPI export unavailable");
const response = await request("/openapi.json");
assert.equal(response.status, 200);
const runtime = await response.json(), expected = JSON.parse(source.stdout);
assert.deepEqual(runtime.paths, expected.paths, "Runtime paths differ from local FastAPI source");
assert.deepEqual(runtime.components.schemas, expected.components.schemas, "Runtime schemas differ from local FastAPI source");
console.log(`PASS runtime/source OpenAPI: ${Object.keys(runtime.paths).length} paths`);
for (const origin of ["http://localhost:3000", "http://127.0.0.1:3000"]) {
  for (const route of ["/sessions", "/documents"]) {
    const result = await request(route, { headers: { Origin: origin } });
    await result.body?.cancel();
    assert.equal(result.status, 200, `${origin} ${route} HTTP status`);
    assert.equal(result.headers.get("Access-Control-Allow-Origin"), origin);
    assert.match(result.headers.get("Vary") ?? "", /\bOrigin\b/i);
    console.log(`PASS Origin GET ${route}: 200, exact allow-origin`);
  }
  const preflight = await request("/chat/stream", { method: "OPTIONS", headers: { Origin: origin,
    "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type" } });
  await preflight.body?.cancel();
  assert.equal(preflight.status, 200);
  assert.equal(preflight.headers.get("Access-Control-Allow-Origin"), origin);
  assert.match(preflight.headers.get("Access-Control-Allow-Methods") ?? "", /\bPOST\b/);
  assert.match(preflight.headers.get("Access-Control-Allow-Headers") ?? "", /content-type/i);
  console.log("PASS actual OPTIONS /chat/stream: POST/content-type allowed");
}
const denied = await request("/chat/stream", { method: "OPTIONS", headers: {
  Origin: "http://localhost:3001", "Access-Control-Request-Method": "POST",
} });
await denied.body?.cancel();
assert.equal(denied.status, 400); assert.equal(denied.headers.get("Access-Control-Allow-Origin"), null);
console.log("PASS non-allowlisted origin preflight denied");
