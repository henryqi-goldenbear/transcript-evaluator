import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

type ReviewRequest = {
  case: Record<string, unknown>;
  primaryEvaluation: Record<string, unknown>;
};

type ReviewResponse = {
  model: string;
  agreement: "agree" | "minor_disagreement" | "major_disagreement";
  recommended_overall: number | null;
  score_delta: number;
  issues: string[];
  reasoning: string;
};

const PORT = Number(process.env.REVIEW_AGENT_PORT || 8787);
const MODEL = process.env.REVIEW_AGENT_MODEL || "gemini-3.1-lite";
const REQUEST_TIMEOUT_MS = 120000;

function loadEnvFile() {
  try {
    const envText = readFileSync(resolve(".env"), "utf-8");
    for (const line of envText.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
      const [key, ...valueParts] = trimmed.split("=");
      if (!process.env[key]) process.env[key] = valueParts.join("=");
    }
  } catch {
    // .env is optional; environment variables may already be set.
  }
}

function sendJson(res: ServerResponse, status: number, payload: unknown) {
  res.writeHead(status, {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Content-Type": "application/json; charset=utf-8",
  });
  res.end(JSON.stringify(payload));
}

function readBody(req: IncomingMessage): Promise<string> {
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

function extractJson(text: string) {
  const cleaned = text.replace(/^\s*[*-]\s+/gm, "");
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

function buildReviewUserMessage(input: ReviewRequest) {
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

async function callGemini(apiKey: string, requestPayload: ReviewRequest): Promise<ReviewResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent?key=${apiKey}`;
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        system_instruction: { parts: [{ text: buildReviewPrompt() }] },
        contents: [{ role: "user", parts: [{ text: buildReviewUserMessage(requestPayload) }] }],
        generationConfig: {
          temperature: 0.1,
          responseMimeType: "application/json",
        },
      }),
      signal: controller.signal,
    });
    if (!res.ok) {
      let message = `Gemini HTTP ${res.status}`;
      try {
        const errorPayload = await res.json();
        message = errorPayload?.error?.message || message;
      } catch {}
      throw new Error(message);
    }
    const data = await res.json();
    const text = data?.candidates?.[0]?.content?.parts?.find(
      (part: { text?: string; thought?: boolean }) => !part.thought && part.text?.trim()
    )?.text;
    if (!text) throw new Error("Empty response from reviewer model.");
    const parsed = JSON.parse(extractJson(text));
    return {
      model: MODEL,
      agreement: parsed.agreement || "minor_disagreement",
      recommended_overall:
        typeof parsed.recommended_overall === "number" ? parsed.recommended_overall : null,
      score_delta: typeof parsed.score_delta === "number" ? parsed.score_delta : 0,
      issues: Array.isArray(parsed.issues) ? parsed.issues.map(String) : [],
      reasoning: String(parsed.reasoning || ""),
    };
  } finally {
    clearTimeout(timeoutId);
  }
}

loadEnvFile();

const server = createServer(async (req, res) => {
  if (req.method === "OPTIONS") {
    sendJson(res, 204, {});
    return;
  }
  if (req.method === "GET" && req.url === "/health") {
    sendJson(res, 200, { ok: true, model: MODEL, port: PORT });
    return;
  }
  if (req.method !== "POST" || req.url !== "/review") {
    sendJson(res, 404, { error: "Use POST /review or GET /health." });
    return;
  }

  try {
    const apiKey = process.env.GOOGLE_API_KEY;
    if (!apiKey) throw new Error("Missing GOOGLE_API_KEY for reviewer agent.");
    const payload = JSON.parse(await readBody(req)) as ReviewRequest;
    if (!payload.case || !payload.primaryEvaluation) {
      throw new Error("Expected JSON body with case and primaryEvaluation.");
    }
    sendJson(res, 200, await callGemini(apiKey, payload));
  } catch (err) {
    sendJson(res, 500, { error: String((err as Error)?.message || err) });
  }
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`Reviewer agent listening on http://127.0.0.1:${PORT}`);
  console.log(`Reviewer model: ${MODEL}`);
});
