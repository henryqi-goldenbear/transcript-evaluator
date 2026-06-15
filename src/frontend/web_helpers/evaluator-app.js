(function() {
  let stopBatch = false;
  let batchAbortController = null;
  const RATING_VALUES = {
    "very poor": 1,
    poor: 2,
    average: 3,
    good: 4,
    excellent: 5
  };
  const VALUE_RATINGS = ["very poor", "poor", "average", "good", "excellent"];

  function normalizeRating(value) {
    if (typeof value === "number" && Number.isFinite(value)) {
      return VALUE_RATINGS[Math.max(1, Math.min(5, Math.round(value))) - 1];
    }
    const rating = String(value || "").trim().toLowerCase().replace(/[_-]+/g, " ");
    if (RATING_VALUES[rating]) return rating;
    return "";
  }

  function ratingValue(row) {
    const rating = normalizeRating(row?.rating ?? row?.score);
    if (rating) return RATING_VALUES[rating];
    if (typeof row?.score === "number") return row.score;
    return null;
  }

  function ratingLabel(row) {
    return normalizeRating(row?.rating ?? row?.score) || "n/a";
  }

  function valueToRating(value) {
    if (!Number.isFinite(value)) return "";
    return VALUE_RATINGS[Math.max(1, Math.min(5, Math.round(value))) - 1];
  }

  function computeOverall(parsed) {
    if (parsed?.scorable?.value === false || parsed?.path === "skip") {
      return null;
    }
    const explicitOverall = ratingValue(parsed?.overall);
    if (explicitOverall !== null) {
      return explicitOverall;
    }
    const ratingValues = [];
    for (const key of ["clarity", "relevance", "specificity", "self_awareness"]) {
      const value = ratingValue(parsed?.[key]);
      if (value !== null) ratingValues.push(value);
    }
    if (!ratingValues.length) return null;
    return +(ratingValues.reduce((sum, n) => sum + n, 0) / ratingValues.length).toFixed(1);
  }

  function computeOverallDisplay(parsed, computedOverall) {
    if (computedOverall === null) return "skip";
    return ratingLabel(parsed?.overall) !== "n/a"
      ? ratingLabel(parsed.overall)
      : valueToRating(computedOverall);
  }

  function checkReady() {
    document.getElementById("run-entire-btn").disabled = !Rubrics.hasLoaded();
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

  function projectRootUrl(path) {
    const value = String(path || "").trim();
    if (!value || /^(?:[a-z]+:)?\/\//i.test(value) || value.startsWith("/")) {
      return value;
    }
    return `../../${value.replace(/^\.?\//, "")}`;
  }

  function formatScoreValue(scoreObj) {
    return ratingLabel(scoreObj);
  }

  function scoreLine(name, scoreObj) {
    if (!scoreObj || typeof scoreObj !== "object") return `     - ${name}: n/a`;
    const score = formatScoreValue(scoreObj);
    const reasoning = scoreObj.reasoning ? ` | ${scoreObj.reasoning}` : "";
    return `     - ${name}: ${score}${reasoning}`;
  }

  function buildScoreBreakdown(parsed) {
    const lines = [];
    lines.push(`     breakdown: scorable=${parsed?.scorable?.value ?? "unknown"} | path=${parsed?.path || "unknown"}`);
    if (parsed?.scorable?.reasoning) {
      lines.push(`     - scorable_reasoning: ${parsed.scorable.reasoning}`);
    }
    lines.push(scoreLine("clarity", parsed?.clarity));
    lines.push(scoreLine("relevance", parsed?.relevance));
    lines.push(scoreLine("specificity", parsed?.specificity));
    lines.push(scoreLine("self_awareness", parsed?.self_awareness));
    if (parsed?.follow_up) {
      const follow = parsed.follow_up;
      const details = [
        `present=${follow.present ?? "unknown"}`,
        `probe=${follow.probe_type ?? "none"}`,
        `impact=${follow.impact ?? "none"}`
      ].join(" | ");
      const reasoning = follow.reasoning ? ` | ${follow.reasoning}` : "";
      lines.push(`     - follow_up: ${details}${reasoning}`);
    }
    if (Array.isArray(parsed?.flags) && parsed.flags.length) {
      lines.push(`     - flags: ${parsed.flags.join(", ")}`);
    }
    lines.push(scoreLine("overall", parsed?.overall));
    return `${lines.join("\n")}\n`;
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
    await LogUtils.resetPipelineLogs();
    LogUtils.appendPipelineLog(`[pipeline] Evaluator run started at ${LogUtils.formatTimeOnly(Date.now())}\n`);

    let cases;
    try {
      batchStatusEl.innerHTML = `<span class="spinner"></span> Loading ${LogUtils.escapeHtml(requestedFile)}...`;
      const res = await fetch(projectRootUrl(requestedFile));
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
          LogUtils.appendBatchLog(logEl, "[stop] Batch run stopped by user.\n");
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
              const { parsed, modelUsed } = await MistralClient.evaluateCase(
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
              const overallDisplay = computeOverallDisplay(parsed, overall);
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
                startedAt: LogUtils.formatTimeOnly(startedMs),
                endedAt: LogUtils.formatTimeOnly(endedMs)
              });
              LogUtils.appendBatchLog(logEl, `[ok] #${tc.id} ${tc.label} | ${tc.rubric_type} | model=${modelUsed} | overall=${overallDisplay}\n`);
              LogUtils.appendBatchLog(logEl, buildScoreBreakdown(parsed));
              LogUtils.appendBatchLog(logEl, `     start=${LogUtils.formatTimeOnly(startedMs)} | end=${LogUtils.formatTimeOnly(endedMs)} | duration=${LogUtils.formatMs(durationMs)}\n`);
              LogUtils.appendPipelineResult({
                status: "ok",
                id: tc.id,
                label: tc.label,
                interview_name: LogUtils.getInterviewName?.(),
                rubric_type: tc.rubric_type,
                model: modelUsed,
                overall,
                overallDisplay,
                durationMs,
                startedAt: LogUtils.formatTimeOnly(startedMs),
                endedAt: LogUtils.formatTimeOnly(endedMs),
                parsed
              });
              LogUtils.saveAgent1Result({
                status: "ok",
                id: tc.id,
                label: tc.label,
                interview_name: LogUtils.getInterviewName?.(),
                rubric_type: tc.rubric_type,
                model: modelUsed,
                overall,
                overallDisplay,
                durationMs,
                startedAt: LogUtils.formatTimeOnly(startedMs),
                endedAt: LogUtils.formatTimeOnly(endedMs),
                parsed
              });
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
              LogUtils.appendBatchLog(logEl, `[err] case failed: ${msg}\n`);
              LogUtils.appendPipelineResult({
                status: "error",
                id: tc.id ?? "?",
                label: tc.label,
                rubric_type: tc.rubric_type,
                error: msg
              });
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
          LogUtils.appendBatchLog(logEl, "[stop] Batch run stopped by user.\n");
          stopped = true;
          return;
        }
      }

      const scoredResults = results.filter(r => typeof r.overall === "number");
      const avg = scoredResults.length
        ? (scoredResults.reduce((s, r) => s + r.overall, 0) / scoredResults.length).toFixed(2)
        : "0.00";
      const avgRating = scoredResults.length ? valueToRating(Number(avg)) : "n/a";
      const totalDuration = LogUtils.formatMs(Date.now() - processStartMs);
      batchStatusEl.textContent =
        `Done. Total: ${total}, Success: ${results.length}, Failed: ${failures}, Avg overall: ${avgRating}, Total time: ${totalDuration}`;
    } catch (err) {
      if (stopBatch) {
        batchStatusEl.textContent = `Stopped. Processed: ${results.length + failures}/${total}, Success: ${results.length}, Failed: ${failures}`;
        LogUtils.appendBatchLog(logEl, "[stop] Batch run stopped by user.\n");
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
        const avgRating = scoredResults.length ? valueToRating(Number(avg)) : "n/a";
        const totalDuration = LogUtils.formatMs(Date.now() - processStartMs);
        if (canExportPdf) {
          await PdfReport.generateBatchPdf({
            runTime: LogUtils.formatTimeOnly(runStartedAt.getTime()),
            model,
            inputFile: requestedFile,
            batchSize,
            total,
            success: results.length,
            failed: failures,
            avgOverall: avgRating,
            avgOverallValue: avg,
            totalDuration,
            stopped,
            successItems: results,
            failureItems
          });
          LogUtils.appendBatchLog(logEl, "[pdf] Evaluation report PDF downloaded.\n");
          batchStatusEl.textContent = summaryAtEntry || "Done";
        } else {
          LogUtils.appendBatchLog(logEl, "[pdf] Skipped PDF export (run not fully successful).\n");
        }
        if (failures > 0 && !stopped) {
          Analytics.addEvent(traceRun, {
            eventType: "debug_report_export",
            failures
          });
          Analytics.exportDebugReport(traceRun);
          LogUtils.appendBatchLog(logEl, "[dbg] Exported debug_trace JSON for failures.\n");
        }
      } catch (pdfErr) {
        const msg = String(pdfErr?.message || pdfErr || "Unknown PDF error");
        LogUtils.appendBatchLog(logEl, `[pdf-err] Failed to generate PDF: ${msg}\n`);
        batchStatusEl.innerHTML = `<span class="error-text">PDF generation failed: ${LogUtils.escapeHtml(msg)}</span>`;
      }

      LogUtils.appendPipelineResult({
        status: stopped ? "stopped" : "done",
        inputFile: requestedFile,
        model,
        batchSize,
        total,
        success: results.length,
        failed: failures,
        completedAll: results.length + failures === total,
        finishedAt: LogUtils.formatTimeOnly(Date.now())
      });

      if (completedAll && !stopped) {
        try {
          const agent2 = await LogUtils.sendToAgent2(requestedFile);
          if (agent2?.status) {
            LogUtils.appendBatchLog(logEl, `[agent2] ${agent2.status}: ${agent2.message || "handoff complete"}\n`);
          }
        } catch (agentErr) {
          const msg = String(agentErr?.message || agentErr || "Unknown Agent 2 error");
          LogUtils.appendBatchLog(logEl, `[agent2-err] ${msg}\n`);
        }
      } else {
        LogUtils.appendBatchLog(logEl, "[agent2] Skipped handoff because Agent 1 did not complete all cases.\n");
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
