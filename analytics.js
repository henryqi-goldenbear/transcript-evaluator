(() => {
  function nowIso() {
    return new Date().toISOString();
  }

  function id(prefix) {
    return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
  }

  function sanitizeSnippet(value, maxLen = 320) {
    const s = String(value || "").replace(/\s+/g, " ").trim();
    return s.length > maxLen ? `${s.slice(0, maxLen)}...` : s;
  }

  function classifyError(err) {
    const message = String(err?.message || err || "Unknown error");
    const lower = message.toLowerCase();
    let code = "unknown_error";
    if (err?.name === "AbortError" || lower.includes("stopped")) code = "aborted";
    else if (lower.includes("429") || lower.includes("quota") || lower.includes("resource_exhausted")) code = "rate_limit";
    else if (lower.includes("internal error")) code = "internal_error";
    else if (lower.startsWith("http ")) code = "http_error";
    else if (lower.includes("json")) code = "json_parse_error";
    return {
      code,
      message,
      stack: err?.stack || null
    };
  }

  function createRun(meta) {
    return {
      runId: id("run"),
      startedAt: nowIso(),
      meta: { ...meta },
      events: [],
      failures: []
    };
  }

  function createCaseTrace(tc, batchIndex) {
    return {
      traceId: id("trace"),
      caseId: tc?.id ?? "?",
      label: tc?.label ?? "",
      batchIndex,
      attempt: 0
    };
  }

  function nextAttempt(trace) {
    trace.attempt += 1;
    return {
      attempt: trace.attempt,
      attemptId: `${trace.traceId}_a${trace.attempt}`
    };
  }

  function addEvent(run, event) {
    if (!run) return;
    run.events.push({
      ts: nowIso(),
      ...event
    });
  }

  function addFailure(run, failure) {
    if (!run) return;
    run.failures.push({
      ts: nowIso(),
      ...failure
    });
  }

  function verboseLog(enabled, logEl, msg) {
    if (!enabled || !logEl) return;
    logEl.textContent += `[dbg] ${msg}\n`;
  }

  function exportDebugReport(run) {
    const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "").replace("T", "_");
    const name = `debug_trace_${stamp}.json`;
    const blob = new Blob([JSON.stringify(run, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  window.Analytics = {
    addEvent,
    addFailure,
    classifyError,
    createCaseTrace,
    createRun,
    exportDebugReport,
    nextAttempt,
    sanitizeSnippet,
    verboseLog
  };
})();

