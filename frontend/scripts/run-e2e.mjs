import { mkdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

// Keep generated test fixtures (e.g. vehicles.xlsx) in a stable directory outside
// Playwright's outputDir cleanup. Only redirect TMP/TEMP/TMPDIR on Windows: on Linux
// (e.g. GitHub Actions ubuntu-latest), long workspace paths exceed the 108-byte AF_UNIX
// sun_path limit for Chromium's SingletonSocket inside TMPDIR.
const temporary = fileURLToPath(new URL("../.playwright-tmp/", import.meta.url));
mkdirSync(temporary, { recursive: true });
const env =
  process.platform === "win32"
    ? { ...process.env, TMP: temporary, TEMP: temporary, TMPDIR: temporary }
    : { ...process.env };
const result = spawnSync(
  process.execPath,
  [fileURLToPath(new URL("../node_modules/playwright/cli.js", import.meta.url)), "test", ...process.argv.slice(2)],
  {
    cwd: fileURLToPath(new URL("../", import.meta.url)),
    stdio: "inherit",
    windowsHide: true,
    env,
  },
);
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
