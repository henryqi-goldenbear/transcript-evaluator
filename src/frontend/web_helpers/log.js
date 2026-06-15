(function() {
  let pipelineLogTail = Promise.resolve();

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatMs(ms) {
    const n = Math.max(0, Number(ms) || 0);
    if (n < 1000) return `${n}ms`;
    return `${(n / 1000).toFixed(2)}s`;
  }

  function formatTimeOnly(tsMs) {
    const d = new Date(tsMs);
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    const ss = String(d.getSeconds()).padStart(2, "0");
    return `${hh}:${mm}:${ss}`;
  }

  function baseNameWithoutExtension(path) {
    const clean = String(path || "").split(/[?#]/)[0].replace(/\\/g, "/");
    const name = clean.split("/").pop() || "";
    return name.replace(/\.[^.]*$/, "");
  }

  function getInputFile() {
    return new URLSearchParams(window.location.search).get("input") || "";
  }

  function getInterviewName() {
    return baseNameWithoutExtension(getInputFile());
  }

  function getInputTextFile() {
    const params = new URLSearchParams(window.location.search);
    const inputText = params.get("input_text");
    if (inputText) return inputText;
    const inputFile = getInputFile();
    if (!inputFile) return "";
    return inputFile.replace(/\.json$/i, ".txt");
  }

  function getInputJsonFile(inputFile) {
    const params = new URLSearchParams(window.location.search);
    const inputJson = params.get("input_json");
    if (inputJson) return inputJson;
    return inputFile || getInputFile();
  }

  function getPipelineLogFile() {
    const params = new URLSearchParams(window.location.search);
    const explicitLogFile = params.get("log_file");
    if (explicitLogFile) return explicitLogFile;
    const inputStem = baseNameWithoutExtension(getInputFile());
    return inputStem ? `logs/agent1/${inputStem}/${inputStem}_eval.log` : "";
  }

  function getResultLogFile() {
    const params = new URLSearchParams(window.location.search);
    const explicitLogFile = params.get("result_log_file");
    if (explicitLogFile) return explicitLogFile;
    const inputStem = baseNameWithoutExtension(getInputFile());
    return inputStem ? `logs/agent1/${inputStem}/${inputStem}.log` : "";
  }

  function writePipelineFile(logFile, text, writeMode = "a") {
    if (!logFile || (writeMode !== "w" && !text)) return;
    pipelineLogTail = pipelineLogTail.then(() => fetch("/pipeline-log", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ log_file: logFile, text, write_mode: writeMode }),
      keepalive: true
    })).catch(() => {
      // The on-page log remains the source of truth if the pipeline endpoint is unavailable.
    });
    return pipelineLogTail;
  }

  function appendPipelineLog(text) {
    return writePipelineFile(getPipelineLogFile(), text);
  }

  function appendResultLog(text) {
    return writePipelineFile(getResultLogFile(), text);
  }

  function resetPipelineLogs() {
    writePipelineFile(getPipelineLogFile(), "", "w");
    return writePipelineFile(getResultLogFile(), "", "w");
  }

  function appendBatchLog(logEl, text) {
    if (logEl) logEl.textContent += text;
    appendPipelineLog(text);
  }

  function appendPipelineResult(result) {
    return appendResultLog(`[result] ${JSON.stringify(result)}\n`);
  }

  function saveAgent1Result(result) {
    if (result?.status !== "ok") return Promise.resolve(null);
    return fetch("/interview-db/agent1-result", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...result,
        interview_name: result.interview_name || getInterviewName(),
        log_file: result.log_file || getPipelineLogFile(),
      }),
      keepalive: true
    }).catch(() => null);
  }

  function flushPipelineLog() {
    return pipelineLogTail;
  }

  async function sendToAgent2(inputFile) {
    const logFile = getPipelineLogFile();
    const inputTextFile = getInputTextFile(inputFile);
    const inputJsonFile = getInputJsonFile(inputFile);
    if (!logFile || !inputTextFile) return null;
    await flushPipelineLog();
    const res = await fetch("/agent2/handoff", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        log_file: logFile,
        input_file: inputTextFile,
        input_json_file: inputJsonFile
      }),
      keepalive: true
    });
    if (!res.ok) {
      throw new Error(`Agent 2 handoff HTTP ${res.status}`);
    }
    return res.json();
  }

  window.LogUtils = {
    appendBatchLog,
    appendPipelineLog,
    appendPipelineResult,
    escapeHtml,
    formatMs,
    formatTimeOnly,
    flushPipelineLog,
    getInterviewName,
    getPipelineLogFile,
    getResultLogFile,
    saveAgent1Result,
    resetPipelineLogs,
    sendToAgent2
  };
})();
