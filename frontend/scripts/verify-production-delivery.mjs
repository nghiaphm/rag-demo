// HTTP delivery only, not browser hydration/keyboard/accessibility acceptance.
// Start and stop only the server owned by this script; don't touch dev servers.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { createServer } from "node:net";
import { fileURLToPath } from "node:url";

const frontend = fileURLToPath(new URL("../", import.meta.url));
const reservation = createServer();
reservation.listen(0, "127.0.0.1"); await once(reservation, "listening");
const port = reservation.address().port;
await new Promise(resolve => reservation.close(resolve));
const child = spawn(process.execPath, [fileURLToPath(new URL("../node_modules/next/dist/bin/next", import.meta.url)),
  "start", "--hostname", "127.0.0.1", "--port", String(port)], {
  cwd: frontend, windowsHide: true, stdio: ["ignore", "pipe", "pipe"],
});
let timer;
const exited = once(child, "exit");
try {
  await new Promise((resolve, reject) => {
    timer = setTimeout(() => reject(new Error("Owned production server readiness timeout")), 15000);
    child.once("error", reject);
    child.once("exit", () => reject(new Error("Owned production server exited before QA")));
    child.stdout.on("data", data => { if (String(data).includes("Ready")) resolve(); });
    child.stderr.on("data", () => {});
  });
  clearTimeout(timer);
  const base = `http://127.0.0.1:${port}`;
  for (const route of ["/chat", "/chat/aaaaaaaa-1111-4111-8111-111111111111", "/documents"]) {
    const response = await fetch(base + route, { signal: AbortSignal.timeout(10000) });
    assert.equal(response.status, 200);
    const html = await response.text();
    assert(html.includes('id="main-content"'));
    assert(!html.includes("CLIENT_HOOK_DYNAMIC"));
    assert(!html.includes("should be wrapped in a suspense boundary"));
    console.log(`PASS production HTTP ${route}: 200/main content`);
    if (route === "/chat") {
      const asset = /<script[^>]+src="([^"?#]+\.js)(?:\?[^" ]*)?"/.exec(html)?.[1];
      assert(asset?.startsWith("/_next/"));
      const script = await fetch(base + asset, { signal: AbortSignal.timeout(10000) });
      await script.body?.cancel();
      assert.equal(script.status, 200);
      assert.match(script.headers.get("Content-Type") ?? "", /javascript/);
      console.log("PASS production client script delivery");
    }
  }
} finally {
  clearTimeout(timer);
  if (child.exitCode === null && child.signalCode === null) child.kill();
  await exited;
  console.log("Owned production server stopped; developer servers untouched");
}
