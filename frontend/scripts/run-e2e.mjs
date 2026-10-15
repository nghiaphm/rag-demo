import { mkdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

// Keep browser profiles/temp on the workspace volume, outside Playwright's
// outputDir cleanup. This is independent of Codex's in-app Browser runtime.
const temporary = fileURLToPath(new URL("../.playwright-tmp/", import.meta.url));
mkdirSync(temporary, { recursive: true });
const result = spawnSync(process.execPath, [fileURLToPath(new URL("../node_modules/playwright/cli.js", import.meta.url)), "test", ...process.argv.slice(2)], {
  cwd: fileURLToPath(new URL("../", import.meta.url)), stdio: "inherit", windowsHide: true,
  env: { ...process.env, TMP: temporary, TEMP: temporary, TMPDIR: temporary },
});
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
