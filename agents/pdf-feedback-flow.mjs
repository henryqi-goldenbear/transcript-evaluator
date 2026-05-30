import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { basename, resolve } from "node:path";

function loadEnvFile() {
  try {
    const envText = readFileSync(resolve(".env"), "utf-8");
    for (const line of envText.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
      const [key, ...valueParts] = trimmed.split("=");
      if (!process.env[key]) process.env[key] = valueParts.join("=").trim().replace(/^['\"]|['\"]$/g, "");
    }
  } catch {}
}

loadEnvFile();

const REQUEST_TIMEOUT_MS = Number(process.env.PDF_BIAS_TOOL_TIMEOUT_MS || process.env.REVIEW_AGENT_TIMEOUT_MS || 45000);
const PDF_BIAS_EXCERPT_CHARS = Number(process.env.PDF_BIAS_EXCERPT_CHARS || 3500);
const DEFAULT_MCP_COMMAND = process.platform === "win32" ? "npx.cmd" : "npx";
const RAW_MCP_COMMAND = process.env.MCP_COMMAND || DEFAULT_MCP_COMMAND;
const MCP_COMMAND = process.platform === "win32" && RAW_MCP_COMMAND === "npx" ? "npx.cmd" : RAW_MCP_COMMAND;
const MCP_ARGS = JSON.parse(process.env.MCP_ARGS || '["-y","@brightdata/mcp"]');
const API_TOKEN = process.env.API_TOKEN || process.env.BRIGHTDATA_API_TOKEN || process.env.MCP_API_KEY || "";
const AI_TOOLS = (process.env.PDF_BIAS_TOOLS || "web_data_chatgpt_ai_insights")
  .split(",")
  .map(tool => tool.trim())
  .filter(Boolean);

function findDefaultPdf() {
  const explicit = process.argv[2];
  if (explicit) return resolve(explicit);
  const pdfs = readdirSync(process.cwd())
    .filter(name => /^evaluation_report_.*\.pdf$/i.test(name))
    .sort()
    .reverse();
  if (!pdfs.length) throw new Error("No evaluation_report_*.pdf found. Pass a PDF path as the first argument.");
  return resolve(pdfs[0]);
}

function decodePdfLiteral(value) {
  return value
    .replace(/\\n/g, "\n")
    .replace(/\\r/g, "\r")
    .replace(/\\t/g, "\t")
    .replace(/\\\(/g, "(")
    .replace(/\\\)/g, ")")
    .replace(/\\\\/g, "\\");
}

function extractPdfText(buffer) {
  const raw = buffer.toString("latin1");
  const pieces = [];
  const literalRe = /\((?:\\.|[^\\)])*\)\s*Tj/g;
  for (const match of raw.matchAll(literalRe)) {
    pieces.push(decodePdfLiteral(match[0].replace(/\)\s*Tj$/, "").slice(1)));
  }
  return pieces.join("\n").replace(/\s+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
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
    if (this.initialized) return;
    if (!API_TOKEN) throw new Error("Missing API_TOKEN for Bright Data MCP.");
    const childEnv = { ...process.env, API_TOKEN };
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
    this.proc.on("exit", (code, signal) => {
      this.initialized = false;
      for (const { reject } of this.pending.values()) reject(new Error(`MCP exited: code=${code} signal=${signal}`));
      this.pending.clear();
    });
    await this.request("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "transcript-evaluator-pdf-bias", version: "1.0.0" },
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
      const message = JSON.parse(rawLine);
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
    const id = this.nextId++;
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

  async callTool(name, args) {
    await this.ensureStarted();
    return this.request("tools/call", { name, arguments: args });
  }

  close() {
    this.proc?.kill();
  }
}

function extractToolText(result) {
  const content = result?.content || [];
  if (Array.isArray(content)) {
    return content.map(part => typeof part === "string" ? part : part?.text || "").filter(Boolean).join("\n");
  }
  return JSON.stringify(result);
}

function buildAgent2PdfMessage(pdfPath, buffer) {
  return {
    from: "agent_2",
    to: "agent_1",
    type: "pdf_bias_review_request",
    pdf: {
      path: pdfPath,
      filename: basename(pdfPath),
      bytes: buffer.length,
      sha256: createHash("sha256").update(buffer).digest("hex"),
    },
    instruction: "Use ChatGPT, Grok, and Perplexity AI insight tools to judge whether Agent 2's report appears biased. Ignore whether the PDF contains a dedicated Second Agent Review section; judge from the visible report text only.",
  };
}

function buildBiasPrompt(pdfText) {
  return `You are Agent 1 reviewing Agent 2's PDF report for evaluator bias. Ignore whether the PDF contains a dedicated "Second Agent Review" section. Based only on the visible report text below, decide whether the report appears biased.

Return concise JSON with keys: bias_risk (low|medium|high|inconclusive), bias_type, evidence, feedback_to_agent_2, suggested_fix.

PDF text excerpt:
${pdfText.slice(0, PDF_BIAS_EXCERPT_CHARS)}`;
}

const pdfPath = findDefaultPdf();
const pdfBuffer = readFileSync(pdfPath);
const pdfText = extractPdfText(pdfBuffer);
const agent2Message = buildAgent2PdfMessage(pdfPath, pdfBuffer);
const prompt = buildBiasPrompt(pdfText);
const client = new StdioMcpClient();
const toolResponses = [];

try {
  for (const tool of AI_TOOLS) {
    try {
      const result = await Promise.race([
        client.callTool(tool, { prompt }),
        new Promise((_, reject) => setTimeout(() => reject(new Error(`Timed out after ${REQUEST_TIMEOUT_MS}ms`)), REQUEST_TIMEOUT_MS)),
      ]);
      toolResponses.push({ tool, ok: true, output: extractToolText(result) });
    } catch (error) {
      toolResponses.push({ tool, ok: false, error: String(error?.message || error) });
    }
  }
} finally {
  client.close();
}

const successful = toolResponses.filter(row => row.ok);
const failed = toolResponses.filter(row => !row.ok);
const agent1Feedback = {
  from: "agent_1",
  to: "agent_2",
  type: "pdf_bias_feedback_ai_insights",
  received_pdf: agent2Message.pdf,
  feedback: {
    method: "Bright Data MCP AI insight tools",
    ignored_second_agent_review_section_requirement: true,
    tools_requested: AI_TOOLS,
    tools_succeeded: successful.map(row => row.tool),
    tools_failed: failed,
    extracted_character_count: pdfText.length,
    ai_tool_outputs: toolResponses,
    summary: successful.length
      ? "Agent 1 received AI-insight feedback about possible bias in Agent 2's PDF report."
      : "Agent 1 could not obtain AI-insight feedback from the configured MCP tools.",
  },
  next_message_to_agent_2: successful.length
    ? "Review the AI insight outputs, then revise the PDF report if they identify bias patterns or missing calibration evidence."
    : "Fix the MCP AI insight tool failures, then resend the PDF for bias review.",
};

console.log("AGENT_2_TO_AGENT_1_MESSAGE:");
console.log(JSON.stringify(agent2Message, null, 2));
console.log("\nAGENT_1_TO_AGENT_2_FEEDBACK:");
console.log(JSON.stringify(agent1Feedback, null, 2));


