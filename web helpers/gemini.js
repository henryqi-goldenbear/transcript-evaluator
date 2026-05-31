(function() {
  function extractJson(text) {
    const cleaned = text.replace(/^\s*[*-]\s+/gm, "");
    const fenced = cleaned.match(/```(?:json)?\s*([\s\S]*?)```/);
    if (fenced) return fenced[1].trim();
    const start = cleaned.indexOf("{");
    if (start !== -1) {
      let depth = 0;
      for (let i = start; i < cleaned.length; i++) {
        const ch = cleaned[i];
        if (ch === "{") depth++;
        if (ch === "}") {
          depth--;
          if (depth === 0) return cleaned.slice(start, i + 1);
        }
      }
    }
    return cleaned.trim();
  }

  function parseRetryMs(msg) {
    const m = msg.match(/retry in ([\d.]+)s/i);
    if (m) return Math.ceil(parseFloat(m[1]) * 1000) + 2500;
    return 65000;
  }

  async function sleepCountdown(ms, el, signal) {
    if (signal?.aborted) throw new Error("Batch stopped by user.");
    const end = Date.now() + ms;
    while (Date.now() < end) {
      if (signal?.aborted) throw new Error("Batch stopped by user.");
      const secs = Math.ceil((end - Date.now()) / 1000);
      el.textContent = `Rate limited - waiting ${secs}s...`;
      await new Promise(r => setTimeout(r, Math.min(1000, end - Date.now())));
    }
  }

  function strictJsonPrompt(basePrompt) {
    return `${basePrompt}

CRITICAL OUTPUT RULES:
- Return valid JSON only.
- Output must begin with "{" and end with "}".
- No markdown, no bullets, no prose, no code fences.`;
  }

  function tryParseModelJson(rawText) {
    const candidate = extractJson((rawText || "").trim());
    return JSON.parse(candidate);
  }

  async function callGemini(apiKey, model, systemPrompt, userMsg, signal, traceRun, traceCtx, attemptCtx) {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;
    const requestStarted = Date.now();
    Analytics.addEvent(traceRun, {
      eventType: "request_start",
      traceId: traceCtx?.traceId,
      caseId: traceCtx?.caseId,
      attempt: attemptCtx?.attempt,
      attemptId: attemptCtx?.attemptId,
      model,
      url
    });

    const isGemma = model.startsWith("gemma-");
    const generationConfig = { temperature: 0.15 };
    if (!isGemma) generationConfig.responseMimeType = "application/json";

    const body = isGemma
      ? {
          contents: [{
            role: "user",
            parts: [{ text: `${systemPrompt}\n\n---\n\n${userMsg}` }]
          }],
          generationConfig
        }
      : {
          system_instruction: { parts: [{ text: systemPrompt }] },
          contents: [{ role: "user", parts: [{ text: userMsg }] }],
          generationConfig
        };

    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal
    });

    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      let apiErrorPayload = "";
      try {
        const json = await res.json();
        msg = json?.error?.message || msg;
        apiErrorPayload = JSON.stringify(json);
      } catch (_) {}
      Analytics.addEvent(traceRun, {
        eventType: "request_error",
        traceId: traceCtx?.traceId,
        caseId: traceCtx?.caseId,
        attempt: attemptCtx?.attempt,
        attemptId: attemptCtx?.attemptId,
        model,
        httpStatus: res.status,
        durationMs: Date.now() - requestStarted,
        errorCode: "http_error",
        errorMessage: msg,
        payloadSnippet: Analytics.sanitizeSnippet(apiErrorPayload || msg)
      });
      throw new Error(msg);
    }

    const data = await res.json();
    const parts = data?.candidates?.[0]?.content?.parts ?? [];
    const visibleParts = parts.filter(
      p => !p?.thought && typeof p?.text === "string" && p.text.trim()
    );
    const text =
      visibleParts[visibleParts.length - 1]?.text ??
      parts[parts.length - 1]?.text;
    if (!text) throw new Error("Empty response from API.");
    Analytics.addEvent(traceRun, {
      eventType: "request_success",
      traceId: traceCtx?.traceId,
      caseId: traceCtx?.caseId,
      attempt: attemptCtx?.attempt,
      attemptId: attemptCtx?.attemptId,
      model,
      httpStatus: res.status,
      durationMs: Date.now() - requestStarted
    });
    return isGemma ? extractJson(text) : text;
  }

  async function callGeminiWithRetry(apiKey, model, prompt, userMsg, statusEl, signal, traceRun, traceCtx, debugMode, logEl) {
    for (let attempt = 0; attempt < 3; attempt++) {
      const attemptCtx = Analytics.nextAttempt(traceCtx);
      try {
        if (signal?.aborted) throw new Error("Batch stopped by user.");
        if (attempt > 0) statusEl.textContent = "Retrying...";
        else statusEl.innerHTML = '<span class="spinner"></span> Calling model...';
        Analytics.verboseLog(debugMode, logEl, `trace=${traceCtx.traceId} case=${traceCtx.caseId} attempt=${attemptCtx.attempt} request_start model=${model}`);
        return await callGemini(apiKey, model, prompt, userMsg, signal, traceRun, traceCtx, attemptCtx);
      } catch (err) {
        if (signal?.aborted || err?.name === "AbortError") {
          Analytics.addEvent(traceRun, {
            eventType: "request_aborted",
            traceId: traceCtx?.traceId,
            caseId: traceCtx?.caseId,
            attempt: attemptCtx?.attempt,
            attemptId: attemptCtx?.attemptId,
            model,
            errorCode: "aborted",
            errorMessage: "Batch stopped by user."
          });
          throw new Error("Batch stopped by user.");
        }
        const isRateLimit =
          err.message.includes("quota") ||
          err.message.includes("429") ||
          err.message.includes("RESOURCE_EXHAUSTED") ||
          err.message.toLowerCase().includes("retry in");
        const normalized = Analytics.classifyError(err);
        Analytics.addEvent(traceRun, {
          eventType: "attempt_error",
          traceId: traceCtx?.traceId,
          caseId: traceCtx?.caseId,
          attempt: attemptCtx?.attempt,
          attemptId: attemptCtx?.attemptId,
          model,
          errorCode: normalized.code,
          errorMessage: normalized.message,
          stack: normalized.stack
        });
        Analytics.verboseLog(
          debugMode,
          logEl,
          `trace=${traceCtx.traceId} case=${traceCtx.caseId} attempt=${attemptCtx.attempt} errorCode=${normalized.code} msg=${normalized.message}`
        );
        if (!isRateLimit || attempt >= 2) throw err;
        const retryMs = parseRetryMs(err.message);
        Analytics.addEvent(traceRun, {
          eventType: "retry_scheduled",
          traceId: traceCtx?.traceId,
          caseId: traceCtx?.caseId,
          attempt: attemptCtx?.attempt,
          attemptId: attemptCtx?.attemptId,
          model,
          retryInMs: retryMs
        });
        await sleepCountdown(retryMs, statusEl, signal);
      }
    }
  }

  async function evaluateCase(apiKey, model, prompt, userMsg, statusEl, signal, traceRun, traceCtx, debugMode, logEl) {
    let modelUsed = model;
    let raw;

    try {
      raw = await callGeminiWithRetry(apiKey, modelUsed, prompt, userMsg, statusEl, signal, traceRun, traceCtx, debugMode, logEl);
    } catch (err) {
      const normalized = Analytics.classifyError(err);
      Analytics.addFailure(traceRun, {
        traceId: traceCtx?.traceId,
        caseId: traceCtx?.caseId,
        errorCode: normalized.code,
        errorMessage: normalized.message,
        stack: normalized.stack
      });
      if (signal?.aborted || String(err.message || "").toLowerCase().includes("stopped")) {
        throw new Error("Batch stopped by user.");
      }
      throw err;
    }

    try {
      return { parsed: tryParseModelJson(raw), modelUsed };
    } catch (_) {
      Analytics.addEvent(traceRun, {
        eventType: "json_repair_retry",
        traceId: traceCtx?.traceId,
        caseId: traceCtx?.caseId,
        model: modelUsed,
        payloadSnippet: Analytics.sanitizeSnippet(raw)
      });
      statusEl.textContent = "Repairing format (JSON-only retry)...";
      const rawRetry = await callGeminiWithRetry(
        apiKey,
        modelUsed,
        strictJsonPrompt(prompt),
        userMsg,
        statusEl,
        signal,
        traceRun,
        traceCtx,
        debugMode,
        logEl
      );
      return { parsed: tryParseModelJson(rawRetry), modelUsed };
    }
  }

  window.GeminiClient = {
    evaluateCase
  };
})();
