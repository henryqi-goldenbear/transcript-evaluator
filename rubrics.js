(function() {
  const UNIFIED_RUBRIC = `Evaluate each entry using this decision flow:

Is this a scorable turn?
- NO -> skip
- YES -> continue

Behavioral path:
- Score these dimensions from 1-5: base, personal_contribution, real_example, outcome

Non-behavioral path:
- Score base from 1-5
- Score any needed type-specific dimensions from 1-5

Then apply follow-up logic:
- No follow-up probe -> score stands as-is
- Clarifying probe:
  - Candidate recovered -> neutral, note it
  - Candidate did not recover -> downgrade specificity and/or outcome
- Deepening probe:
  - Candidate added new detail -> positive signal, note it
  - Candidate did not go deeper -> credibility risk flag

Calibration:
- Score only what is explicitly present.
- Keep the final overall score on a 1-5 scale.
- Use scorable=false only for truly unscorable turns.
- If the question looks behavioral, prefer the behavioral path; otherwise prefer the non-behavioral path.
- When type-specific dimensions are used, name them clearly and keep them concise.`;

  function buildEvaluationPrompt() {
    return `You are an expert interview evaluator.

Use the rubric below as the source of truth:

${UNIFIED_RUBRIC}

Return only this JSON, no extra text:
{
  "scorable": { "value": <true|false>, "reasoning": "<one sentence>" },
  "path": "behavioral" | "non_behavioral" | "skip",
  "base": { "score": <1-5>, "reasoning": "<one sentence>" },
  "personal_contribution": { "score": <1-5>, "reasoning": "<one sentence>" },
  "real_example": { "score": <1-5>, "reasoning": "<one sentence>" },
  "outcome": { "score": <1-5>, "reasoning": "<one sentence>" },
  "type_specific_dimensions": [
    { "name": "<short name>", "score": <1-5>, "reasoning": "<one sentence>" }
  ],
  "follow_up": {
    "present": <true|false>,
    "probe_type": "clarifying" | "deepening" | null,
    "impact": "neutral" | "downgrade_specificity_or_outcome" | "positive_signal" | "credibility_risk" | null,
    "reasoning": "<one sentence>"
  },
  "flags": [],
  "overall": { "score": <1-5 or null>, "reasoning": "<one sentence summary>" }
}`;
  }

  function buildUserMessage(input) {
    const label = input.rubric_type === "non_behavioral" ? "non-behavioral" : "behavioral";
    let txt = `Question: ${input.question}\nCandidate response:\n${input.response}`;
    if (input.follow_up) txt += `\nFollow-up question: ${input.follow_up}`;
    if (input.follow_up_response) txt += `\nCandidate follow-up response: ${input.follow_up_response}`;
    return `Evaluate this interview case.\nSuggested path hint: ${label}\n\n${txt}`;
  }

  function hasLoaded() {
    return true;
  }

  async function loadRubrics(statusEl, onReady) {
    if (statusEl) statusEl.textContent = "Unified rubric loaded.";
    if (typeof onReady === "function") onReady();
  }

  window.Rubrics = {
    buildEvaluationPrompt,
    buildUserMessage,
    hasLoaded,
    loadRubrics
  };
})();
