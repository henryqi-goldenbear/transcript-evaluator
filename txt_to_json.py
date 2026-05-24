"""Convert interview transcript text files into test_cases-style JSON.

Expected input format:
  INTERVIEWER:
  ...content...
  CANDIDATE:
  ...content...

Output format matches test_cases.json:
[
  {
    "id": 1,
    "label": "...",
    "question": "...",
    "response": "...",
    "follow_ups": [
      {
        "question": "...",
        "response": "..."
      }
    ],
    "expected": {}
  }
]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


SPEAKER_RE = re.compile(r"^\s*(INTERVIEWER|CANDIDATE)\s*:\s*(.*)$")
FOLLOW_UP_PATTERNS = [
    re.compile(r"^\s*can you\b", re.IGNORECASE),
    re.compile(r"^\s*could you\b", re.IGNORECASE),
    re.compile(r"^\s*i'?d like\b", re.IGNORECASE),
    re.compile(r"^\s*you mentioned\b", re.IGNORECASE),
    re.compile(r"^\s*what would have broken\b", re.IGNORECASE),
    re.compile(r"^\s*i hear\b", re.IGNORECASE),
    re.compile(r"^\s*fair push\b", re.IGNORECASE),
    re.compile(r"^\s*anything else\b", re.IGNORECASE),
]


def _extract_turns(raw_text: str) -> list[dict]:
    lines = raw_text.splitlines()
    turns: list[dict] = []
    current_speaker: str | None = None
    current_message: list[str] = []

    def flush_current() -> None:
        nonlocal current_speaker, current_message
        if current_speaker is None:
            return
        message = "\n".join(current_message).strip()
        turns.append(
            {
                "index": len(turns) + 1,
                "speaker": current_speaker.lower(),
                "text": message,
            }
        )
        current_speaker = None
        current_message = []

    for line in lines:
        match = SPEAKER_RE.match(line)
        if match:
            flush_current()
            current_speaker = match.group(1)
            first_line = match.group(2).strip()
            current_message = [first_line] if first_line else []
            continue

        if current_speaker is not None:
            current_message.append(line)

    flush_current()
    return turns


def parse_transcript_to_test_cases(raw_text: str) -> list[dict]:
    turns = _extract_turns(raw_text)
    cases: list[dict] = []
    case_id = 1

    i = 0
    while i < len(turns):
        turn = turns[i]
        if turn["speaker"] != "interviewer":
            i += 1
            continue

        question = turn["text"].strip()
        if not question:
            i += 1
            continue

        response = ""
        if i + 1 < len(turns) and turns[i + 1]["speaker"] == "candidate":
            response = turns[i + 1]["text"].strip()

        if _is_follow_up_question(question) and cases:
            cases[-1]["follow_ups"].append({"question": question, "response": response})
        else:
            # Keep a concise auto label; users can refine later.
            label = f"Auto case {case_id}"
            cases.append(
                {
                    "id": case_id,
                    "label": label,
                    "question": question,
                    "response": response,
                    "follow_ups": [],
                    "expected": {},
                }
            )
            case_id += 1
        i += 2

    return cases


def _is_follow_up_question(question_text: str) -> bool:
    cleaned = question_text.strip()
    return any(pattern.search(cleaned) for pattern in FOLLOW_UP_PATTERNS)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert transcript text into test_cases-style JSON."
    )
    parser.add_argument("input", help="Path to transcript text file")
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation (default: 2)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if input_path.suffix.lower() != ".txt":
        raise ValueError(
            f"Input must be a .txt file. Got: {input_path.name}"
        )

    output_path = input_path.with_suffix(".json")

    raw_text = input_path.read_text(encoding="utf-8")
    parsed_cases = parse_transcript_to_test_cases(raw_text)
    output_path.write_text(
        json.dumps(parsed_cases, indent=args.indent), encoding="utf-8"
    )

    print(f"Wrote JSON to: {output_path}")
    print(f"Cases: {len(parsed_cases)}")


if __name__ == "__main__":
    main()
