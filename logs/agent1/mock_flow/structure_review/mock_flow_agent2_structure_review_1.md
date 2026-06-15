# Agent 2 Structure Review

Iteration: 1
Satisfied: False
Summary: Move the dependent probe under the first case.

## Issues
[
  {
    "severity": "high",
    "case_id": 2,
    "question": "What happened next?",
    "problem": "Dependent follow-up was treated as its own case.",
    "correction": "Attach it to case 1 as a deepening follow-up."
  }
]

## Response
{"satisfied": false, "summary": "Move the dependent probe under the first case.", "issues": [{"severity": "high", "case_id": 2, "question": "What happened next?", "problem": "Dependent follow-up was treated as its own case.", "correction": "Attach it to case 1 as a deepening follow-up."}], "desired_cases": [{"id": 1, "label": "Auto case 1", "turn_type": "behavioral", "rubric_type": "behavioral", "classification_source": "agent2-structure-review", "classification_reasoning": "Main behavioral question with a dependent probe.", "question": "Tell me about a time you led a project.", "response": "I led a migration.", "follow_ups": [{"question": "What happened next?", "response": "We added chaos tests.", "probe_type": "deepening", "classification_source": "agent2-structure-review"}], "expected": {}}]}

## Prompt
You are Agent 2 acting as the structure reviewer for Agent 0.

Agent 0 is txt_to_json.py. It converts a raw interview transcript into evaluator-ready JSON.
Before Agent 1 scores anything, review Agent 0's structure and either approve it or return the
exact corrected structure Agent 0 should use.

Review rules:
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

Source: input data/mock_flow.txt
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
    "question": "Tell me about a time you led a project.",
    "response": "I led a migration.",
    "follow_ups": [],
    "expected": {}
  },
  {
    "id": 2,
    "label": "Auto case 2",
    "turn_type": "non_behavioral",
    "rubric_type": "non_behavioral",
    "classification_source": "test",
    "classification_reasoning": "test",
    "question": "What happened next?",
    "response": "We added chaos tests.",
    "follow_ups": [],
    "expected": {}
  }
]

--- Original transcript ---
INTERVIEWER:
Tell me about a time you led a project.
CANDIDATE:
I led a migration.
INTERVIEWER:
What happened next?
CANDIDATE:
We added chaos tests.

