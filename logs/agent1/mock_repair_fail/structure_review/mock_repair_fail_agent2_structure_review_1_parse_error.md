# Agent 2 Structure Review Parse Error

Iteration: 1
Error: Agent 2 structure review did not return a JSON object.

## Raw Response
This is prose.

## Repair Response
Still prose.

## Prompt
You are Agent 2 acting as the structure reviewer for Agent 0.

Agent 0 is txt_to_json.py. It converts a raw interview transcript into evaluator-ready JSON.
Before Agent 1 scores anything, review Agent 0's structure and either approve it or return the
exact corrected structure Agent 0 should use.

Review rules:
- This is not the final QA report. Do not write a narrative audit.
- Your entire response must be one JSON object that can be parsed by json.loads.
- Compare the original transcript against the evaluator JSON.
- Main interview questions should be separate cases.
- Dependent probes should be follow_ups on the correct parent case.
- Independent questions should not be attached as follow_ups.
- Greetings, logistics, interviewer explanations, transitions, closings, and candidate questions
  should be non-scorable and omitted.
- Each follow_up must include the candidate response that answers that follow-up.
- probe_type must be "clarifying" when the interviewer asks for missing facts, context, role,
  metrics, timeline, or specificity.
- probe_type must be "deepening" when the interviewer probes reasoning, tradeoffs, consequences,
  reflection, or what happened next.

Return valid JSON only. No markdown, no prose outside JSON.
Your first character must be "{" and your last character must be "}".

Use exactly this schema:
{
  "satisfied": true | false,
  "summary": "one short sentence",
  "issues": [
    {
      "severity": "high" | "medium" | "low",
      "case_id": <number or null>,
      "question": "question or nearby transcript text",
      "problem": "what is structurally wrong",
      "correction": "what Agent 0 should change"
    }
  ],
  "desired_cases": [
    {
      "id": <number>,
      "label": "Auto case <number>",
      "turn_type": "behavioral" | "non_behavioral",
      "rubric_type": "behavioral" | "non_behavioral",
      "classification_source": "agent2-structure-review",
      "classification_reasoning": "why this is a scored case",
      "question": "main interviewer question",
      "response": "candidate response to the main question",
      "follow_ups": [
        {
          "question": "follow-up interviewer question",
          "response": "candidate response to the follow-up",
          "probe_type": "clarifying" | "deepening",
          "classification_source": "agent2-structure-review"
        }
      ],
      "expected": {}
    }
  ]
}

If satisfied is true, desired_cases may repeat the input JSON unchanged.
If satisfied is false, desired_cases must contain the full corrected evaluator JSON, not a patch.
Keep ids sequential starting at 1.

Source: input data/mock_repair_fail.txt
Review iteration: 1

--- Agent 0 evaluator JSON ---
[
  {
    "id": 1,
    "label": "Auto case 1",
    "turn_type": "behavioral",
    "rubric_type": "behavioral",
    "classification_source": "test",
    "classification_reasoning": "test",
    "question": "Tell me about a time.",
    "response": "Answer.",
    "follow_ups": [],
    "expected": {}
  }
]

--- Original transcript ---
INTERVIEWER:
Tell me about a time.
CANDIDATE:
Answer.
