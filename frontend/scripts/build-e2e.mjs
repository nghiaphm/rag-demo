// A deterministic public mock base baked into this production build only.
// No .env edits. Browser fixtures abort any request outside the UI/mock origins.
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const result = spawnSync(process.execPath, [fileURLToPath(new URL("../node_modules/next/dist/bin/next", import.meta.url)), "build"], {
  cwd: fileURLToPath(new URL("../", import.meta.url)), stdio: "inherit", windowsHide: true,
  env: { ...process.env, NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:4011/lifecycle" },
});
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
