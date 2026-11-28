// A deterministic public mock base baked into this production build only.
// No .env edits. Browser fixtures abort any request outside the UI/mock origins.
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const frontendDir = fileURLToPath(new URL("../", import.meta.url));
const result = spawnSync(
  process.execPath,
  [fileURLToPath(new URL("../node_modules/next/dist/bin/next", import.meta.url)), "build"],
  {
    cwd: frontendDir,
    stdio: "inherit",
    windowsHide: true,
    env: { ...process.env, NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:4011/lifecycle" },
  },
);
if (result.error) throw result.error;
if ((result.status ?? 1) !== 0) {
  process.exitCode = result.status ?? 1;
} else {
  // Next.js standalone server requires .next/static and public copied alongside server.js.
  const standaloneDir = fileURLToPath(new URL("../.next/standalone/", import.meta.url));
  const staticSrc = fileURLToPath(new URL("../.next/static/", import.meta.url));
  const staticDst = fileURLToPath(new URL("../.next/standalone/.next/static/", import.meta.url));
  const publicSrc = fileURLToPath(new URL("../public/", import.meta.url));
  const publicDst = fileURLToPath(new URL("../.next/standalone/public/", import.meta.url));

  if (existsSync(standaloneDir)) {
    if (existsSync(staticSrc)) {
      mkdirSync(staticDst, { recursive: true });
      cpSync(staticSrc, staticDst, { recursive: true, force: true });
    }
    if (existsSync(publicSrc)) {
      mkdirSync(publicDst, { recursive: true });
      cpSync(publicSrc, publicDst, { recursive: true, force: true });
    }
  }
  process.exitCode = 0;
}
