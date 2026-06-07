(function() {
  function buildPdfFilename() {
    const d = new Date();
    const pad = n => String(n).padStart(2, "0");
    return `evaluation_report_${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}.pdf`;
  }

  function textOrNone(v) {
    const s = String(v || "").trim();
    return s || "None";
  }

  function getDimensionOrderForRubric(parsed) {
    if (parsed?.path === "behavioral") {
      return ["base", "personal_contribution", "real_example", "outcome"];
    }
    return ["base"];
  }

  async function generateBatchPdf(reportData) {
    if (!window.jspdf?.jsPDF) throw new Error("jsPDF failed to load.");
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF({ unit: "pt", format: "a4" });
    const left = 40;
    const top = 40;
    const pageW = doc.internal.pageSize.getWidth();
    const pageH = doc.internal.pageSize.getHeight();
    const contentW = pageW - left * 2;
    let y = top;

    const ensureSpace = (needed = 18) => {
      if (y + needed > pageH - 40) {
        doc.addPage();
        y = top;
      }
    };
    const addLine = (text, size = 10, gap = 14) => {
      ensureSpace(gap);
      doc.setFont("helvetica", "normal");
      doc.setFontSize(size);
      doc.text(String(text), left, y);
      y += gap;
    };
    const addWrapped = (label, value, size = 10) => {
      const wrapped = doc.splitTextToSize(`${label}${value}`, contentW);
      ensureSpace(wrapped.length * 13 + 2);
      doc.setFont("helvetica", "normal");
      doc.setFontSize(size);
      doc.text(wrapped, left, y);
      y += wrapped.length * 13 + 2;
    };
    const addSectionTitle = text => {
      ensureSpace(22);
      doc.setFont("helvetica", "bold");
      doc.setFontSize(12);
      doc.text(text, left, y);
      y += 16;
    };

    doc.setFont("helvetica", "bold");
    doc.setFontSize(16);
    doc.text("Transcript Evaluator - Batch Report", left, y);
    y += 20;

    addLine(`Run time: ${reportData.runTime}`);
    addLine(`Model: ${reportData.model}`);
    addLine(`Input file: ${reportData.inputFile}`);
    addLine(`Batch size: ${reportData.batchSize}`);
    addLine(`Total runtime: ${reportData.totalDuration}`);
    addLine(
      `Status: ${reportData.stopped ? "Stopped" : "Completed"} | Total: ${reportData.total} | Success: ${reportData.success} | Failed: ${reportData.failed} | Avg overall: ${reportData.avgOverall}`
    );
    y += 4;

    for (const item of reportData.successItems) {
      ensureSpace(30);
      doc.setDrawColor(90, 100, 120);
      doc.line(left, y, pageW - left, y);
      y += 14;

      addSectionTitle(`Case #${item.id ?? "?"}: ${textOrNone(item.label)}`);
      addLine(`Rubric: ${item.rubric_type}`, 10, 13);
      addLine(`Resolved path: ${item.parsed?.path || item.rubric_type}`, 10, 13);
      addLine(`Overall: ${item.overall === null ? "skip" : `${item.overall}/5`}`, 10, 13);
      addLine(`Case runtime: ${item.duration}`, 10, 13);
      addWrapped("Question: ", textOrNone(item.question));
      addWrapped("Response: ", textOrNone(item.response));
      if (item.follow_up) addWrapped("Follow-up question: ", item.follow_up);
      if (item.follow_up_response) addWrapped("Follow-up response: ", item.follow_up_response);

      addSectionTitle("Scorable");
      addWrapped("", `${item.parsed?.scorable?.value === false ? "No" : "Yes"} - ${textOrNone(item.parsed?.scorable?.reasoning)}`);

      addSectionTitle("Dimensions");
      const dims = getDimensionOrderForRubric(item.parsed);
      for (const dim of dims) {
        const row = item.parsed?.[dim];
        if (!row) continue;
        addWrapped(`${dim} (${row.score ?? "?"}/5): `, textOrNone(row.reasoning));
      }
      if (Array.isArray(item.parsed?.type_specific_dimensions) && item.parsed.type_specific_dimensions.length) {
        for (const row of item.parsed.type_specific_dimensions) {
          addWrapped(`${row.name || "type_specific"} (${row.score ?? "?"}/5): `, textOrNone(row.reasoning));
        }
      }

      addSectionTitle("Follow-up");
      addWrapped(
        "",
        `present=${item.parsed?.follow_up?.present ? "yes" : "no"} | probe=${item.parsed?.follow_up?.probe_type || "none"} | impact=${item.parsed?.follow_up?.impact || "none"} | ${textOrNone(item.parsed?.follow_up?.reasoning)}`
      );

      addSectionTitle("Overall Reasoning");
      addWrapped("", textOrNone(item.parsed?.overall?.reasoning));

      addSectionTitle("Flags");
      const flags = Array.isArray(item.parsed?.flags) && item.parsed.flags.length
        ? item.parsed.flags.join(" | ")
        : "None";
      addWrapped("", flags);
      y += 8;
    }

    if (reportData.failureItems.length) {
      ensureSpace(26);
      doc.setDrawColor(90, 100, 120);
      doc.line(left, y, pageW - left, y);
      y += 14;
      addSectionTitle("Failed Cases");
      for (const f of reportData.failureItems) {
        addWrapped(`Case ${f.caseRef}: `, textOrNone(f.error));
      }
    }

    doc.save(buildPdfFilename());
  }

  window.PdfReport = {
    generateBatchPdf
  };
})();
