# Agent 2 Structure Review

Iteration: 1
Satisfied: False
Summary: Split independent prioritization question.

## Issues
[]

## Operations
[
  {
    "op": "split_follow_up_to_case",
    "source_case_id": 1,
    "follow_up_question": "How do you prioritize work?",
    "turn_type": "non_behavioral",
    "reason": "Independent question."
  }
]

## Response
{"satisfied": false, "summary": "Split independent prioritization question.", "issues": [], "operations": [{"op": "split_follow_up_to_case", "source_case_id": 1, "follow_up_question": "How do you prioritize work?", "turn_type": "non_behavioral", "reason": "Independent question."}]}

## Prompt
You are Agent 2 acting as the structure reviewer for Agent 0.

Agent 0 is txt_to_json.py. It converts a raw interview transcript into evaluator-ready JSON.
Before Agent 1 scores anything, review Agent 0's structure and either approve it or return the
compact correction operations Agent 0 should apply.

Review rules:
- This is not the final QA report. Do not write a narrative audit.
- Your entire response must be one JSON object that can be parsed by json.loads.
- Compare the compact transcript outline against the evaluator JSON outline.
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
  "operations": [
    {
      "op": "split_follow_up_to_case" | "add_missing_case" | "remove_case" | "move_follow_up" | "change_probe_type",
      "reason": "why this operation is needed",
      "source_case_id": <number or null>,
      "target_case_id": <number or null>,
      "follow_up_question": "follow-up question text or empty string",
      "question": "main question text or empty string",
      "response": "candidate response text or empty string",
      "turn_type": "behavioral" | "non_behavioral" | "",
      "probe_type": "clarifying" | "deepening" | ""
    }
  ]
}

If satisfied is true, operations must be [].
If satisfied is false, operations must contain compact edits only. Do not return the full corrected JSON.
Prefer split_follow_up_to_case when Agent 0 attached an independent question as a follow-up.
Prefer add_missing_case when a transcript question is absent from the evaluator JSON.

Source: input data/mock_until_satisfied.txt
Review iteration: 1

--- Compact transcript and current structure ---
{
  "transcript_turns": [
    {
      "turn_index": 1,
      "speaker": "interviewer",
      "text": "Tell me about a time you failed."
    },
    {
      "turn_index": 2,
      "speaker": "candidate",
      "text": "I shipped a bad model."
    },
    {
      "turn_index": 3,
      "speaker": "interviewer",
      "text": "How do you prioritize work?"
    },
    {
      "turn_index": 4,
      "speaker": "candidate",
      "text": "Due date first."
    }
  ],
  "current_cases": [
    {
      "id": 1,
      "turn_type": "behavioral",
      "question": "Tell me about a time you failed.",
      "response": "I shipped a bad model.",
      "follow_ups": [
        {
          "question": "How do you prioritize work?",
          "response": "Due date first.",
          "probe_type": "deepening"
        }
      ]
    }
  ]
}
