(function() {
  let stopBatch = false;
  let batchAbortController = null;

  function computeOverall(parsed) {
    if (parsed?.scorable?.value === false || parsed?.path === "skip") {
      return null;
    }
    if (typeof parsed?.overall?.score === "number") {
      return parsed.overall.score;
    }
    const scores = [];
    for (const key of ["base", "personal_contribution", "real_example", "outcome"]) {
      if (typeof parsed?.[key]?.score === "number") scores.push(parsed[key].score);
    }
    if (Array.isArray(parsed?.type_specific_dimensions)) {
      for (const row of parsed.type_specific_dimensions) {
        if (typeof row?.score === "number") scores.push(row.score);
      }
    }
    if (!scores.length) return null;
    return +(scores.reduce((sum, n) => sum + n, 0) / scores.length).toFixed(1);
  }

  function checkReady() {
    const key = (window.GEMINI_API_KEY || "").trim();
    document.getElementById("run-entire-btn").disabled = !(Rubrics.hasLoaded() && key.length > 10);
  }

  function clampBatchSize(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return 1;
    return Math.max(1, Math.min(7, Math.trunc(n)));
  }

  function looksBehavioralQuestion(q) {
    return /tell me about a time|describe a situation|give me an example/i.test(q || "");
  }

  function normalizeTranscriptCase(c) {
    const followUps = Array.isArray(c.follow_ups) ? c.follow_ups : [];
    const firstFollow = followUps[0] || {};
    const rubricType =
      c.rubric_type ||
      c.turn_type ||
      (looksBehavioralQuestion(c.question) ? "behavioral" : "non_behavioral");
    if (rubricType === "non_question") {
      return null;
    }
    return {
      rubric_type: rubricType,
      question: c.question || "",
      response: c.response || "",
      follow_up: firstFollow.question || undefined,
      follow_up_response: firstFollow.response || undefined,
      id: c.id,
      label: c.label || `Case ${c.id ?? "?"}`
    };
  }

  function updateBatchProgress(batchStatusEl, total, results, failures, batchSize, processedUpperBound) {
    const processed = results.length + failures;
    batchStatusEl.innerHTML =
      `<span class="spinner"></span> Running cases ${processedUpperBound} / ${total} (batch size ${batchSize}) | Processed: ${processed}, Success: ${results.length}, Failed: ${failures}`;
  }

  async function runEntireInterviewBatch() {
    stopBatch = false;
    batchAbortController = new AbortController();
    const batchSignal = batchAbortController.signal;
    const apiKey = (window.GEMINI_API_KEY || "").trim();
    if (!apiKey) {
      alert("Missing API key. Set window.GEMINI_API_KEY in config.js.");
      return;
    }

    const batchInput = document.getElementById("batch-size-input");
    const batchSize = clampBatchSize(batchInput.value);
    batchInput.value = String(batchSize);
    const batchFileInput = document.getElementById("batch-file-input");
    const requestedFile = (batchFileInput.value || "").trim() || "entire_interview.json";

    const model = document.getElementById("model-select").value;
    const debugMode = document.getElementById("debug-mode-input").checked;
    const batchStatusEl = document.getElementById("batch-status-row");
    const logEl = document.getElementById("batch-log");
    const runBtn = document.getElementById("run-entire-btn");
    const stopBtn = document.getElementById("stop-entire-btn");
    runBtn.disabled = true;
    stopBtn.disabled = false;
    logEl.textContent = "";

    let cases;
    try {
      batchStatusEl.innerHTML = `<span class="spinner"></span> Loading ${LogUtils.escapeHtml(requestedFile)}...`;
      const res = await fetch(`./${requestedFile}`);
      if (!res.ok) throw new Error(`${requestedFile} HTTP ${res.status}`);
      cases = await res.json();
      if (!Array.isArray(cases) || !cases.length) {
        throw new Error(`${requestedFile} must be a non-empty JSON array.`);
      }
    } catch (err) {
      batchStatusEl.innerHTML = `<span class="error-text">Load error: ${LogUtils.escapeHtml(String(err.message || err))}</span>`;
      runBtn.disabled = false;
      stopBtn.disabled = true;
      checkReady();
      return;
    }

    let failures = 0;
    const total = cases.length;
    const results = [];
    const failureItems = [];
    const runStartedAt = new Date();
    const processStartMs = Date.now();
    const traceRun = Analytics.createRun({
      model,
      batchSize,
      inputFile: requestedFile,
      debugMode
    });
    let stopped = false;

    try {
      for (let i = 0; i < total; i += batchSize) {
        if (stopBatch) {
          batchStatusEl.textContent = `Stopped. Processed: ${results.length + failures}/${total}, Success: ${results.length}, Failed: ${failures}`;
          logEl.textContent += "[stop] Batch run stopped by user.\n";
          stopped = true;
          return;
        }
        const slice = cases.slice(i, i + batchSize).map(normalizeTranscriptCase).filter(Boolean);
        if (!slice.length) {
          continue;
        }
        batchStatusEl.innerHTML = `<span class="spinner"></span> Running cases ${i + 1}-${Math.min(i + batchSize, total)} / ${total} (batch size ${batchSize})...`;

        await Promise.all(
          slice.map(async (tc, idx) => {
            const traceCtx = Analytics.createCaseTrace(tc, i + idx);
            try {
              if (stopBatch) throw new Error("Batch stopped by user.");
              Analytics.addEvent(traceRun, {
                eventType: "case_start",
                traceId: traceCtx.traceId,
                caseId: traceCtx.caseId,
                batchIndex: traceCtx.batchIndex,
                model,
                rubric: tc.rubric_type
              });
              const prompt = Rubrics.buildEvaluationPrompt();
              const userMsg = Rubrics.buildUserMessage(tc);
              const startedMs = Date.now();
              const { parsed } = await GeminiClient.evaluateCase(
                apiKey,
                model,
                prompt,
                userMsg,
                batchStatusEl,
                batchSignal,
                traceRun,
                traceCtx,
                debugMode,
                logEl
              );
              const endedMs = Date.now();
              const durationMs = endedMs - startedMs;
              Analytics.addEvent(traceRun, {
                eventType: "case_success",
                traceId: traceCtx.traceId,
                caseId: traceCtx.caseId,
                durationMs
              });
              const overall = computeOverall(parsed);
              const overallDisplay = overall === null ? "skip" : overall;
              results.push({
                id: tc.id,
                label: tc.label,
                rubric_type: tc.rubric_type,
                question: tc.question,
                response: tc.response,
                follow_up: tc.follow_up,
                follow_up_response: tc.follow_up_response,
                parsed,
                overall,
                overallDisplay,
                durationMs,
                duration: LogUtils.formatMs(durationMs),
                startedAtIso: LogUtils.formatIso(startedMs),
                endedAtIso: LogUtils.formatIso(endedMs)
              });
              logEl.textContent += `[ok] #${tc.id} ${tc.label} | ${tc.rubric_type} | overall=${overallDisplay}\n`;
              logEl.textContent += `     start=${LogUtils.formatTimeOnly(startedMs)} | end=${LogUtils.formatTimeOnly(endedMs)} | duration=${LogUtils.formatMs(durationMs)}\n`;
              Analytics.verboseLog(debugMode, logEl, `trace=${traceCtx.traceId} case=${tc.id} completed overall=${overallDisplay}`);
              updateBatchProgress(batchStatusEl, total, results, failures, batchSize, Math.min(i + batchSize, total));
              return { status: "fulfilled" };
            } catch (err) {
              const msg = String(err?.message || err || "Unknown error");
              if (stopBatch || msg.toLowerCase().includes("stopped")) {
                return { status: "stopped" };
              }
              failures += 1;
              failureItems.push({ caseRef: String(tc.id ?? "?"), error: msg });
              logEl.textContent += `[err] case failed: ${msg}\n`;
              Analytics.addFailure(traceRun, {
                traceId: traceCtx.traceId,
                caseId: tc.id ?? "?",
                errorCode: Analytics.classifyError(err).code,
                errorMessage: msg
              });
              updateBatchProgress(batchStatusEl, total, results, failures, batchSize, Math.min(i + batchSize, total));
              return { status: "rejected" };
            }
          })
        );

        if (stopBatch) {
          batchStatusEl.textContent = `Stopped. Processed: ${results.length + failures}/${total}, Success: ${results.length}, Failed: ${failures}`;
          logEl.textContent += "[stop] Batch run stopped by user.\n";
          stopped = true;
          return;
        }
      }

      const scoredResults = results.filter(r => typeof r.overall === "number");
      const avg = scoredResults.length
        ? (scoredResults.reduce((s, r) => s + r.overall, 0) / scoredResults.length).toFixed(2)
        : "0.00";
      const totalDuration = LogUtils.formatMs(Date.now() - processStartMs);
      batchStatusEl.textContent =
        `Done. Total: ${total}, Success: ${results.length}, Failed: ${failures}, Avg overall: ${avg}, Total time: ${totalDuration}`;
    } catch (err) {
      if (stopBatch) {
        batchStatusEl.textContent = `Stopped. Processed: ${results.length + failures}/${total}, Success: ${results.length}, Failed: ${failures}`;
        logEl.textContent += "[stop] Batch run stopped by user.\n";
        stopped = true;
      } else {
        batchStatusEl.innerHTML = `<span class="error-text">Batch error: ${LogUtils.escapeHtml(String(err.message || err))}</span>`;
      }
    } finally {
      const summaryAtEntry = batchStatusEl.textContent;
      const completedAll = results.length + failures === total;
      const canExportPdf = completedAll && !stopped && failures === 0;
      if (canExportPdf) batchStatusEl.innerHTML = '<span class="spinner"></span> Generating PDF...';
      try {
        const scoredResults = results.filter(r => typeof r.overall === "number");
        const avg = scoredResults.length
          ? (scoredResults.reduce((s, r) => s + r.overall, 0) / scoredResults.length).toFixed(2)
          : "0.00";
        const totalDuration = LogUtils.formatMs(Date.now() - processStartMs);
        if (canExportPdf) {
          await PdfReport.generateBatchPdf({
            runTimeIso: runStartedAt.toISOString(),
            model,
            inputFile: requestedFile,
            batchSize,
            total,
            success: results.length,
            failed: failures,
            avgOverall: avg,
            totalDuration,
            stopped,
            successItems: results,
            failureItems
          });
          logEl.textContent += "[pdf] Evaluation report PDF downloaded.\n";
          batchStatusEl.textContent = summaryAtEntry || "Done";
        } else {
          logEl.textContent += "[pdf] Skipped PDF export (run not fully successful).\n";
        }
        if (failures > 0 && !stopped) {
          Analytics.addEvent(traceRun, {
            eventType: "debug_report_export",
            failures
          });
          Analytics.exportDebugReport(traceRun);
          logEl.textContent += "[dbg] Exported debug_trace JSON for failures.\n";
        }
      } catch (pdfErr) {
        const msg = String(pdfErr?.message || pdfErr || "Unknown PDF error");
        logEl.textContent += `[pdf-err] Failed to generate PDF: ${msg}\n`;
        batchStatusEl.innerHTML = `<span class="error-text">PDF generation failed: ${LogUtils.escapeHtml(msg)}</span>`;
      }

      runBtn.disabled = false;
      stopBtn.disabled = true;
      batchAbortController = null;
      checkReady();
    }
  }

  function init() {
    document.getElementById("run-entire-btn").addEventListener("click", runEntireInterviewBatch);
    document.getElementById("stop-entire-btn").addEventListener("click", () => {
      stopBatch = true;
      if (batchAbortController) batchAbortController.abort();
    });
    document.getElementById("batch-size-input").addEventListener("input", e => {
      e.target.value = String(clampBatchSize(e.target.value));
    });
    Rubrics.loadRubrics(document.getElementById("batch-status-row"), checkReady);
  }

  window.EvaluatorApp = {
    init
  };
})();
