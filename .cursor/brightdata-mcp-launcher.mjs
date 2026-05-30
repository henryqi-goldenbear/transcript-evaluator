/**
 * Cursor MCP launcher: loads API_TOKEN from project .env and starts @brightdata/mcp.
 * https://docs.brightdata.com/ai/mcp-server/integrations/cursor
 */
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function loadEnvFile() {
  try {
    const envText = readFileSync(resolve(projectRoot, ".env"), "utf-8");
    for (const line of envText.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
      const [key, ...valueParts] = trimmed.split("=");
      if (!process.env[key]) {
        process.env[key] = valueParts.join("=").trim().replace(/^['"]|['"]$/g, "");
      }
    }
  } catch {
    // .env is optional if API_TOKEN is already in the environment.
  }
}

loadEnvFile();

const apiToken =
  process.env.API_TOKEN ||
  process.env.BRIGHTDATA_API_TOKEN ||
  process.env.MCP_API_KEY;

if (!apiToken) {
  console.error(
    "[brightdata-mcp-launcher] Missing API_TOKEN. Add it to .env or set BRIGHTDATA_API_TOKEN."
  );
  process.exit(1);
}

const npx = process.platform === "win32" ? "npx.cmd" : "npx";
const childEnv = {
  ...process.env,
  API_TOKEN: apiToken,
};

const webUnlockerZone =
  process.env.WEB_UNLOCKER_ZONE || process.env.BRIGHTDATA_WEB_UNLOCKER_ZONE;
if (webUnlockerZone) childEnv.WEB_UNLOCKER_ZONE = webUnlockerZone;

const child = spawn(npx, ["-y", "@brightdata/mcp"], {
  cwd: projectRoot,
  env: childEnv,
  stdio: "inherit",
  shell: process.platform === "win32",
  windowsHide: true,
});

child.on("error", err => {
  console.error(`[brightdata-mcp-launcher] Failed to start MCP: ${err.message}`);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) process.exit(1);
  process.exit(code ?? 0);
});
