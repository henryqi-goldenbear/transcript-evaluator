import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function loadEnvFile() {
  try {
    const envText = readFileSync(resolve(".env"), "utf-8");
    for (const line of envText.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
      const [key, ...valueParts] = trimmed.split("=");
      if (!process.env[key]) {
        process.env[key] = valueParts.join("=").trim().replace(/^['\"]|['\"]$/g, "");
      }
    }
  } catch {
  }
}

loadEnvFile();

const PORT = Number(process.env.REVIEW_AGENT_PORT || 8787);
const REQUEST_TIMEOUT_MS = Number(process.env.REVIEW_AGENT_TIMEOUT_MS || 120000);
const MCP_URL = process.env.MCP_URL || process.env.REVIEW_AGENT_MCP_URL || "";
const DEFAULT_MCP_COMMAND = process.platform === "win32" ? "npx.cmd" : "npx";
const RAW_MCP_COMMAND = process.env.MCP_COMMAND || process.env.REVIEW_AGENT_MCP_COMMAND || DEFAULT_MCP_COMMAND;
const MCP_COMMAND = process.platform === "win32" && RAW_MCP_COMMAND === "npx" ? "npx.cmd" : RAW_MCP_COMMAND;
const MCP_ARGS = parseArgs(process.env.MCP_ARGS || process.env.REVIEW_AGENT_MCP_ARGS || '["-y","@brightdata/mcp"]');
const MCP_TOOL_NAME = process.env.MCP_TOOL_NAME || process.env.REVIEW_AGENT_MCP_TOOL || "review_interview_evaluation";
const MCP_MODE = process.env.MCP_MODE || process.env.REVIEW_AGENT_MCP_MODE || (MCP_URL ? "http" : "stdio");
const API_TOKEN = process.env.API_TOKEN || process.env.BRIGHTDATA_API_TOKEN || process.env.MCP_API_KEY || process.env.REVIEW_AGENT_MCP_API_KEY || "";

function parseArgs(value) {
  try {
    const parsed = JSON.parse(value);
    if (Array.isArray(parsed)) return parsed.map(String);
  } catch {
  }
  return String(value).split(/\s+/).filter(Boolean);
}

function sendJson(res, status, payload) {
  res.writeHead(status, {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Content-Type": "application/json; charset=utf-8",
  });
  res.end(JSON.stringify(payload));
}

function readBody(req) {
  return new Promise((resolveBody, reject) => {
    let body = "";
    req.on("data", chunk => {
      body += chunk;
      if (body.length > 1_000_000) {
        reject(new Error("Request body too large."));
        req.destroy();
      }
    });
    req.on("end", () => resolveBody(body));
    req.on("error", reject);
  });
}

function extractJson(text) {
  const cleaned = String(text || "").replace(/^\s*[*-]\s+/gm, "");
  const fenced = cleaned.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fenced) return fenced[1].trim();
  const start = cleaned.indexOf("{");
  if (start !== -1) {
    let depth = 0;
    for (let i = start; i < cleaned.length; i += 1) {
      const ch = cleaned[i];
      if (ch === "{") depth += 1;
      if (ch === "}") {
        depth -= 1;
        if (depth === 0) return cleaned.slice(start, i + 1);
      }
    }
  }
  return cleaned.trim();
}

function buildReviewPrompt() {
  return `You are a second interview-evaluation agent auditing another evaluator.

Check whether the primary evaluation follows the rubric and is supported by the candidate's answer.
Be strict about unsupported scores, but do not invent missing facts.

Return only this JSON, no extra text:
{
  "agreement": "agree" | "minor_disagreement" | "major_disagreement",
  "recommended_overall": <1-5 or null>,
  "score_delta": <number>,
  "issues": ["<short issue>", "..."],
  "reasoning": "<one concise paragraph>"
}`;
}

function buildReviewUserMessage(input) {
  const item = input.case || {};
  const label = item.rubric_type === "non_behavioral" ? "non-behavioral" : "behavioral";
  let caseText = `Suggested path hint: ${label}

Question: ${String(item.question || "")}
Candidate response:
${String(item.response || "")}`;
  if (item.follow_up) caseText += `\nFollow-up question: ${String(item.follow_up)}`;
  if (item.follow_up_response) {
    caseText += `\nCandidate follow-up response: ${String(item.follow_up_response)}`;
  }
  return `Audit the primary evaluator's JSON for this case.

${caseText}

Primary evaluator JSON:
${JSON.stringify(input.primaryEvaluation, null, 2)}`;
}

function normalizeReview(parsed, model) {
  return {
    model,
    agreement: parsed.agreement || "minor_disagreement",
    recommended_overall:
      typeof parsed.recommended_overall === "number" ? parsed.recommended_overall : null,
    score_delta: typeof parsed.score_delta === "number" ? parsed.score_delta : 0,
    issues: Array.isArray(parsed.issues) ? parsed.issues.map(String) : [],
    reasoning: String(parsed.reasoning || ""),
  };
}

function parseReviewPayload(payload, model) {
  if (payload && typeof payload === "object" && payload.agreement) {
    return normalizeReview(payload, model);
  }

  const structured = payload?.result?.structuredContent || payload?.structuredContent;
  if (structured && typeof structured === "object") {
    if (structured.agreement) return normalizeReview(structured, model);
    return {
      model,
      agreement: "minor_disagreement",
      recommended_overall: null,
      score_delta: 0,
      issues: ["MCP tool returned structured non-review data."],
      reasoning: JSON.stringify(structured),
    };
  }

  const content = payload?.result?.content || payload?.content;
  if (Array.isArray(content)) {
    const text = content
      .map(part => (typeof part === "string" ? part : part?.text || ""))
      .filter(Boolean)
      .join("\n");
    try {
      const parsed = JSON.parse(extractJson(text));
      if (parsed && typeof parsed === "object" && parsed.agreement) return normalizeReview(parsed, model);
      return {
        model,
        agreement: "minor_disagreement",
        recommended_overall: null,
        score_delta: 0,
        issues: ["MCP tool returned non-review JSON."],
        reasoning: JSON.stringify(parsed),
      };
    } catch {
      return {
        model,
        agreement: "minor_disagreement",
        recommended_overall: null,
        score_delta: 0,
        issues: ["MCP tool returned non-review text."],
        reasoning: text,
      };
    }
  }

  const text = payload?.result?.text || payload?.text || payload?.output || payload?.response;
  if (typeof text === "string") {
    try {
      const parsed = JSON.parse(extractJson(text));
      if (parsed && typeof parsed === "object" && parsed.agreement) return normalizeReview(parsed, model);
      return {
        model,
        agreement: "minor_disagreement",
        recommended_overall: null,
        score_delta: 0,
        issues: ["MCP tool returned non-review JSON."],
        reasoning: JSON.stringify(parsed),
      };
    } catch {
      return {
        model,
        agreement: "minor_disagreement",
        recommended_overall: null,
        score_delta: 0,
        issues: ["MCP tool returned non-review text."],
        reasoning: text,
      };
    }
  }

  return normalizeReview(JSON.parse(extractJson(JSON.stringify(payload))), model);
}

function mcpArguments(requestPayload) {
  const item = requestPayload.case || {};
  const evaluation = requestPayload.primaryEvaluation || {};

  if (MCP_TOOL_NAME === "search_engine") {
    return {
      query: [
        "interview evaluation rubric support check",
        `question: ${String(item.question || "").slice(0, 180)}`,
        `candidate response: ${String(item.response || "").slice(0, 220)}`,
        `primary score: ${evaluation?.overall?.score ?? "unknown"}`,
        `primary reasoning: ${String(evaluation?.overall?.reasoning || "").slice(0, 180)}`
      ].join(" | "),
      engine: "google"
    };
  }

  if (MCP_TOOL_NAME === "extract") {
    return {
      url: process.env.REVIEW_AGENT_EXTRACT_URL || "http://example.com",
      extraction_prompt: `${buildReviewPrompt()}\n\n${buildReviewUserMessage(requestPayload)}`
    };
  }

  return {
    systemPrompt: buildReviewPrompt(),
    userMessage: buildReviewUserMessage(requestPayload),
    case: requestPayload.case,
    primaryEvaluation: requestPayload.primaryEvaluation,
  };
}

class StdioMcpClient {
  constructor() {
    this.proc = null;
    this.nextId = 1;
    this.pending = new Map();
    this.buffer = "";
    this.initialized = false;
  }

  async ensureStarted() {
    if (this.proc && !this.proc.killed && this.initialized) return;
    if (!API_TOKEN) throw new Error("Missing API_TOKEN, BRIGHTDATA_API_TOKEN, or MCP_API_KEY for Bright Data MCP.");

    const childEnv = { ...process.env, API_TOKEN };
    const webUnlockerZone = process.env.WEB_UNLOCKER_ZONE || process.env.BRIGHTDATA_WEB_UNLOCKER_ZONE;
    if (webUnlockerZone) childEnv.WEB_UNLOCKER_ZONE = webUnlockerZone;

    this.proc = spawn(MCP_COMMAND, MCP_ARGS, {
      cwd: process.cwd(),
      env: childEnv,
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
      shell: process.platform === "win32",
    });
    this.proc.stdout.on("data", chunk => this.handleData(chunk));
    this.proc.stderr.on("data", chunk => {
      const text = chunk.toString().trim();
      if (text) console.error(`[mcp stderr] ${text}`);
    });
    this.proc.on("error", error => {
      this.initialized = false;
      for (const { reject } of this.pending.values()) {
        reject(error);
      }
      this.pending.clear();
    });
    this.proc.on("exit", (code, signal) => {
      this.initialized = false;
      for (const { reject } of this.pending.values()) {
        reject(new Error(`MCP process exited: code=${code} signal=${signal}`));
      }
      this.pending.clear();
    });

    await this.request("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "transcript-evaluator-review-agent", version: "1.0.0" },
    });
    this.notify("notifications/initialized", {});
    this.initialized = true;
  }

  handleData(chunk) {
    this.buffer += chunk.toString("utf8");
    while (true) {
      const newlineIndex = this.buffer.indexOf("\n");
      if (newlineIndex === -1) return;
      const rawLine = this.buffer.slice(0, newlineIndex).trim();
      this.buffer = this.buffer.slice(newlineIndex + 1);
      if (!rawLine) continue;

      let message;
      try {
        message = JSON.parse(rawLine);
      } catch (err) {
        console.error(`[mcp parse] ${err.message}: ${rawLine.slice(0, 200)}`);
        continue;
      }

      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject, timeout } = this.pending.get(message.id);
        clearTimeout(timeout);
        this.pending.delete(message.id);
        if (message.error) reject(new Error(message.error.message || JSON.stringify(message.error)));
        else resolve(message.result);
      }
    }
  }
  send(message) {
    this.proc.stdin.write(`${JSON.stringify(message)}\n`);
  }

  request(method, params) {
    const id = this.nextId;
    this.nextId += 1;
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`MCP request timed out: ${method}`));
      }, REQUEST_TIMEOUT_MS);
      this.pending.set(id, { resolve, reject, timeout });
      this.send({ jsonrpc: "2.0", id, method, params });
    });
  }

  notify(method, params) {
    this.send({ jsonrpc: "2.0", method, params });
  }

  async listTools() {
    await this.ensureStarted();
    return this.request("tools/list", {});
  }

  async callTool(name, args) {
    await this.ensureStarted();
    const toolsResult = await this.request("tools/list", {});
    const availableTools = Array.isArray(toolsResult?.tools) ? toolsResult.tools.map(tool => tool.name) : [];
    if (!availableTools.includes(name)) {
      throw new Error(`Unknown MCP tool "${name}". Available tools: ${availableTools.join(", ") || "none"}`);
    }
    return this.request("tools/call", { name, arguments: args });
  }
}

const stdioMcpClient = new StdioMcpClient();

function mcpAuthHeaders() {
  if (!API_TOKEN) return {};
  const header = process.env.MCP_AUTH_HEADER || "Authorization";
  const scheme = process.env.MCP_AUTH_SCHEME || "Bearer";
  return {
    [header]: scheme ? `${scheme} ${API_TOKEN}` : API_TOKEN,
    "X-API-Key": API_TOKEN,
  };
}

async function callHttpMcp(requestPayload) {
  if (!MCP_URL) throw new Error("Missing MCP_URL for HTTP MCP mode.");
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const body = {
    jsonrpc: "2.0",
    id: Date.now(),
    method: "tools/call",
    params: {
      name: MCP_TOOL_NAME,
      arguments: mcpArguments(requestPayload),
    },
  };

  try {
    const res = await fetch(MCP_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json, text/event-stream",
        ...mcpAuthHeaders(),
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    const raw = await res.text();
    if (!res.ok) throw new Error(`MCP HTTP ${res.status}: ${raw}`);
    const dataLine = raw.trim().split(/\n/).find(line => line.startsWith("data:"));
    const json = JSON.parse(dataLine ? dataLine.slice(5) : raw);
    if (json?.error) throw new Error(json.error.message || JSON.stringify(json.error));
    return parseReviewPayload(json, `mcp:${MCP_TOOL_NAME}`);
  } finally {
    clearTimeout(timeoutId);
  }
}

async function callMcp(requestPayload) {
  if (MCP_MODE === "http") return callHttpMcp(requestPayload);
  const result = await stdioMcpClient.callTool(MCP_TOOL_NAME, mcpArguments(requestPayload));
  return parseReviewPayload({ result }, `mcp:${MCP_TOOL_NAME}`);
}

const server = createServer(async (req, res) => {
  if (req.method === "OPTIONS") {
    sendJson(res, 204, {});
    return;
  }
  if (req.method === "GET" && req.url === "/health") {
    sendJson(res, 200, {
      ok: true,
      provider: "mcp",
      mode: MCP_MODE,
      command: MCP_MODE === "stdio" ? MCP_COMMAND : undefined,
      args: MCP_MODE === "stdio" ? MCP_ARGS : undefined,
      urlConfigured: Boolean(MCP_URL),
      tool: MCP_TOOL_NAME,
      tokenConfigured: Boolean(API_TOKEN),
      port: PORT,
    });
    return;
  }
  if (req.method === "GET" && req.url === "/tools") {
    try {
      sendJson(res, 200, MCP_MODE === "stdio" ? await stdioMcpClient.listTools() : { error: "/tools is only available for stdio MCP mode." });
    } catch (err) {
      sendJson(res, 500, { error: String(err?.message || err) });
    }
    return;
  }
  if (req.method !== "POST" || req.url !== "/review") {
    sendJson(res, 404, { error: "Use POST /review, GET /health, or GET /tools." });
    return;
  }

  try {
    const payload = JSON.parse(await readBody(req));
    if (!payload.case || !payload.primaryEvaluation) {
      throw new Error("Expected JSON body with case and primaryEvaluation.");
    }
    sendJson(res, 200, await callMcp(payload));
  } catch (err) {
    sendJson(res, 500, { error: String(err?.message || err) });
  }
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`Reviewer agent listening on http://127.0.0.1:${PORT}`);
  console.log(`Reviewer provider: mcp`);
  console.log(`MCP mode: ${MCP_MODE}`);
  console.log(`MCP tool: ${MCP_TOOL_NAME}`);
});











