(function() {
  const RUBRIC_URL = "../../docs/behavioral_rubric.md";
  const PROMPT_START = "<!-- RUBRIC_PROMPT_START -->";
  const PROMPT_END = "<!-- RUBRIC_PROMPT_END -->";
  const FALLBACK_RUBRIC = `Use one rubric for every interview question. Do not force all answers into STAR.

Is this a scorable turn?
- NO -> skip
- YES -> continue

Rate these dimensions using only: very poor, poor, average, good, excellent.

clarity:
- Directness, structure, coherence, and lack of distracting filler.
- A fluent but empty answer can be clear but still rate low elsewhere.

relevance:
- How well the answer addresses the question asked.
- Penalize generic, reframed, or partially related answers.

specificity:
- Concrete evidence, context, role, details, examples, tradeoffs, metrics, or outcomes.
- Penalize vague claims, missing personal role, missing scope, missing outcome, and unsupported assertions.

self_awareness:
- Ownership, judgment, reflection, growth, limitations, and awareness of impact.
- For technical/factual questions, rate judgment and ownership of reasoning.

Then apply follow-up logic:
- No follow-up probe -> rating stands as-is
- Clarifying probe:
  - Candidate fills the gap -> neutral or improve specificity
  - Candidate partially fills the gap -> keep or slightly lower specificity/self-awareness
  - Candidate stays vague -> lower specificity and possibly relevance
- Deepening probe:
  - Candidate adds credible new detail -> may improve specificity/self-awareness
  - Candidate repeats the original answer -> lower specificity
  - Candidate deflects, contradicts, or cannot substantiate -> credibility risk

Credibility risk:
- Raise a flag when a strong-sounding answer collapses under follow-up.
- Indicators: repetition without new detail, sudden vagueness, deflection, contradiction, pivoting examples, or revealing the candidate did not own the claimed work.
- Cap specificity at poor unless the candidate later substantiates the claim.
- Cap self_awareness at poor if the candidate deflects or avoids ownership.
- Cap overall at average for mild credibility risk and poor for clear contradiction, deflection, or inability to substantiate a central claim.

Calibration:
- Rate only what is explicitly present.
- Keep the final overall rating descriptive.
- Use scorable=false only for truly unscorable turns.
- Do not inflate ratings because an answer is fluent.
- A clear but generic answer should rate low on relevance and specificity.`;
  let unifiedRubric = FALLBACK_RUBRIC;
  let loaded = false;

  function extractRubricPromptSource(markdown) {
    const text = String(markdown || "").trim();
    if (!text) return "";
    const start = text.indexOf(PROMPT_START);
    const end = text.indexOf(PROMPT_END);
    if (start !== -1 && end !== -1 && end > start) {
      return text.slice(start + PROMPT_START.length, end).trim();
    }
    return text;
  }

  function buildEvaluationPrompt() {
    return `You are an expert interview evaluator.

Use the rubric below as the source of truth:

${unifiedRubric}

Return only this JSON, no extra text:
{
  "scorable": { "value": <true|false>, "reasoning": "<one sentence>" },
  "path": "unified" | "skip",
  "clarity": { "rating": "very poor" | "poor" | "average" | "good" | "excellent", "reasoning": "<one sentence>" },
  "relevance": { "rating": "very poor" | "poor" | "average" | "good" | "excellent", "reasoning": "<one sentence>" },
  "specificity": { "rating": "very poor" | "poor" | "average" | "good" | "excellent", "reasoning": "<one sentence>" },
  "self_awareness": { "rating": "very poor" | "poor" | "average" | "good" | "excellent", "reasoning": "<one sentence>" },
  "follow_up": {
    "present": <true|false>,
    "probe_type": "clarifying" | "deepening" | null,
    "impact": "neutral" | "downgrade_specificity" | "positive_signal" | "credibility_risk" | null,
    "reasoning": "<one sentence>"
  },
  "flags": [],
  "overall": { "rating": "very poor" | "poor" | "average" | "good" | "excellent" | null, "reasoning": "<one sentence summary>" }
}`;
  }

  function buildUserMessage(input) {
    let txt = `Question: ${input.question}\nCandidate response:\n${input.response}`;
    if (input.follow_up) txt += `\nFollow-up question: ${input.follow_up}`;
    if (input.follow_up_response) txt += `\nCandidate follow-up response: ${input.follow_up_response}`;
    return `Evaluate this interview case with the unified rubric.\n\n${txt}`;
  }

  function hasLoaded() {
    return loaded;
  }

  async function loadRubrics(statusEl, onReady) {
    try {
      if (statusEl) statusEl.textContent = "Loading unified rubric...";
      const res = await fetch(`${RUBRIC_URL}?v=${Date.now()}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`${RUBRIC_URL} HTTP ${res.status}`);
      const text = await res.text();
      const promptSource = extractRubricPromptSource(text);
      if (!promptSource) throw new Error(`${RUBRIC_URL} has no usable rubric text`);
      unifiedRubric = promptSource;
      loaded = true;
      if (statusEl) statusEl.textContent = "Unified rubric loaded from docs/behavioral_rubric.md prompt section.";
    } catch (err) {
      unifiedRubric = FALLBACK_RUBRIC;
      loaded = true;
      if (statusEl) {
        statusEl.textContent = `Using fallback unified rubric; could not load docs/behavioral_rubric.md (${err.message || err}).`;
      }
    }
    if (typeof onReady === "function") onReady();
  }

  window.Rubrics = {
    buildEvaluationPrompt,
    buildUserMessage,
    extractRubricPromptSource,
    hasLoaded,
    loadRubrics
  };
})();
