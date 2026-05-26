"""Convert interview transcript text files into evaluator-ready JSON.

Expected input format:
  INTERVIEWER:
  ...content...
  CANDIDATE:
  ...content...

Output format:
[
  {
    "id": 1,
    "label": "...",
    "turn_type": "behavioral" | "non_behavioral",
    "rubric_type": "behavioral" | "non_behavioral",
    "classification_source": "ollama" | "heuristic",
    "classification_reasoning": "...",
    "question": "...",
    "response": "...",
    "follow_ups": [
      {
        "question": "...",
        "response": "...",
        "probe_type": "clarifying" | "deepening",
        "classification_source": "ollama" | "heuristic"
      }
    ],
    "expected": {}
  }
]
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib import error, request


SPEAKER_RE = re.compile(r"^\s*(INTERVIEWER|CANDIDATE)\s*:\s*(.*)$")
BEHAVIORAL_PATTERNS = [
    re.compile(r"\btell me about a time\b", re.IGNORECASE),
    re.compile(r"\bgive me an example\b", re.IGNORECASE),
    re.compile(r"\bdescribe a situation\b", re.IGNORECASE),
    re.compile(r"\bwalk me through a time\b", re.IGNORECASE),
    re.compile(r"\bwhen have you\b", re.IGNORECASE),
    re.compile(r"\bwhat's a time\b", re.IGNORECASE),
]
NON_QUESTION_PATTERNS = [
    re.compile(r"\bhow('?s| is) your day\b", re.IGNORECASE),
    re.compile(r"\bnice to meet you\b", re.IGNORECASE),
    re.compile(r"\bcan you hear me\b", re.IGNORECASE),
    re.compile(r"\bcan you see my screen\b", re.IGNORECASE),
    re.compile(r"\bany trouble with (the )?(video|audio|link)\b", re.IGNORECASE),
    re.compile(r"\bthanks for joining\b", re.IGNORECASE),
    re.compile(r"\bshall we get started\b", re.IGNORECASE),
]
FOLLOW_UP_PATTERNS = [
    re.compile(r"^\s*can you\b", re.IGNORECASE),
    re.compile(r"^\s*could you\b", re.IGNORECASE),
    re.compile(r"^\s*would you\b", re.IGNORECASE),
    re.compile(r"^\s*you mentioned\b", re.IGNORECASE),
    re.compile(r"^\s*on [a-z0-9_-]+", re.IGNORECASE),
    re.compile(r"^\s*when you said\b", re.IGNORECASE),
    re.compile(r"^\s*tell me more\b", re.IGNORECASE),
    re.compile(r"^\s*go deeper\b", re.IGNORECASE),
    re.compile(r"^\s*what happened next\b", re.IGNORECASE),
    re.compile(r"^\s*what broke\b", re.IGNORECASE),
    re.compile(r"^\s*what was your role\b", re.IGNORECASE),
    re.compile(r"^\s*how exactly\b", re.IGNORECASE),
    re.compile(r"^\s*be more specific\b", re.IGNORECASE),
    re.compile(r"^\s*walk me through\b", re.IGNORECASE),
]
CLARIFYING_PATTERNS = [
    re.compile(r"\bclarify\b", re.IGNORECASE),
    re.compile(r"\bmore specific\b", re.IGNORECASE),
    re.compile(r"\bwhat exactly\b", re.IGNORECASE),
    re.compile(r"\bcan you expand\b", re.IGNORECASE),
    re.compile(r"\bhelp me understand\b", re.IGNORECASE),
    re.compile(r"\bwhat do you mean\b", re.IGNORECASE),
]
DEEPENING_PATTERNS = [
    re.compile(r"\bwhat broke\b", re.IGNORECASE),
    re.compile(r"\bwhat happened next\b", re.IGNORECASE),
    re.compile(r"\bwhy\b", re.IGNORECASE),
    re.compile(r"\btrade-?off\b", re.IGNORECASE),
    re.compile(r"\bedge case\b", re.IGNORECASE),
    re.compile(r"\bon [a-z0-9_-]+", re.IGNORECASE),
    re.compile(r"\byou mentioned\b", re.IGNORECASE),
]


def _extract_turns(raw_text: str) -> list[dict[str, Any]]:
    lines = raw_text.splitlines()
    turns: list[dict[str, Any]] = []
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


def _ollama_generate_json(prompt: str, model: str, host: str) -> Any | None:
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "max_tokens": 8192},
        }
    ).encode("utf-8")
    req = request.Request(
        f"{host.rstrip('/')}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=600) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (error.URLError, TimeoutError, json.JSONDecodeError):
        return None

    raw_response = payload.get("response", "").strip()
    if not raw_response:
        return None
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError:
        # Fallback: recover first JSON object/array if model wrapped it in text.
        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", raw_response)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None


def _normalize_single_call_cases(payload: Any) -> list[dict[str, Any]] | None:
    if isinstance(payload, dict):
        for key in ("cases", "test_cases", "items", "data", "result"):
            maybe = payload.get(key)
            if isinstance(maybe, list):
                payload = maybe
                break

    if not isinstance(payload, list):
        return None

    normalized: list[dict[str, Any]] = []
    allowed_turn_types = {"behavioral", "non_behavioral"}
    allowed_probe_types = {"clarifying", "deepening"}

    next_id = 1
    for case in payload:
        if not isinstance(case, dict):
            continue

        question = str(
            case.get("question", case.get("main_question", case.get("interviewer_question", "")))
        ).strip()
        response = str(
            case.get("response", case.get("main_response", case.get("candidate_response", "")))
        ).strip()
        turn_type = str(
            case.get("turn_type", case.get("type", case.get("classification", "")))
        ).strip().lower()
        reasoning = str(
            case.get(
                "classification_reasoning",
                case.get("reasoning", case.get("reason", "")),
            )
        ).strip()
        if turn_type in {"non_question", "nonscorable", "non_scorable"}:
            continue
        if turn_type not in allowed_turn_types or not question:
            continue

        follow_ups_in = case.get("follow_ups", case.get("probes", case.get("followups", [])))
        follow_ups_out: list[dict[str, Any]] = []
        if isinstance(follow_ups_in, list):
            for fu in follow_ups_in:
                if not isinstance(fu, dict):
                    continue
                fu_question = str(
                    fu.get("question", fu.get("follow_up_question", fu.get("interviewer_question", "")))
                ).strip()
                if not fu_question:
                    continue
                probe_type = str(fu.get("probe_type", "")).strip().lower()
                if probe_type not in allowed_probe_types:
                    probe_type = "clarifying"
                follow_ups_out.append(
                    {
                        "question": fu_question,
                        "response": str(fu.get("response", "")).strip(),
                        "probe_type": probe_type,
                        "classification_source": "ollama",
                    }
                )

        normalized.append(
            {
                "id": next_id,
                "label": f"Auto case {next_id}",
                "turn_type": turn_type,
                "rubric_type": turn_type,
                "classification_source": "ollama",
                "classification_reasoning": reasoning or "Single-pass transcript classification by Ollama.",
                "question": question,
                "response": response,
                "follow_ups": follow_ups_out,
                "expected": {},
            }
        )
        next_id += 1

    return normalized if normalized else None


def _single_ollama_transcript_parse(
    raw_text: str,
    ollama_model: str,
    ollama_host: str,
) -> list[dict[str, Any]] | None:
    prompt = f"""Convert the transcript into evaluator test cases.

Return JSON only as an array of objects with this exact schema:
[
  {{
    "question": "main interviewer question",
    "response": "candidate response paired to main question",
    "turn_type": "behavioral" | "non_behavioral",
    "classification_reasoning": "one sentence",
    "follow_ups": [
      {{
        "question": "follow-up interviewer question",
        "response": "candidate response to this follow-up",
        "probe_type": "clarifying" | "deepening"
      }}
    ]
  }}
]

Rules:
- Ignore non-scorable interviewer turns (greetings, logistics, setup chatter).
- Keep only scorable main interviewer questions as top-level objects.
- Attach follow-up probes to the most recent main question.
- A main question should be classified as:
  - behavioral: asks for a specific past example/experience.
  - non_behavioral: scorable but does not require specific past example.
- Do not include markdown fences or extra keys.

Transcript:
{raw_text}
"""
    parsed = _ollama_generate_json(prompt, ollama_model, ollama_host)
    if parsed is None:
        return None
    return _normalize_single_call_cases(parsed)


def _heuristic_turn_classification(question_text: str) -> dict[str, str | bool]:
    cleaned = " ".join(question_text.strip().split())
    if not cleaned:
        return {
            "turn_type": "non_question",
            "is_scorable": False,
            "reasoning": "Empty interviewer turn.",
            "source": "heuristic",
        }
    if any(pattern.search(cleaned) for pattern in NON_QUESTION_PATTERNS):
        return {
            "turn_type": "non_question",
            "is_scorable": False,
            "reasoning": "Detected social or logistics-only interviewer turn.",
            "source": "heuristic",
        }
    if any(pattern.search(cleaned) for pattern in BEHAVIORAL_PATTERNS):
        return {
            "turn_type": "behavioral",
            "is_scorable": True,
            "reasoning": "Question explicitly asks for a past concrete example.",
            "source": "heuristic",
        }
    return {
        "turn_type": "non_behavioral",
        "is_scorable": True,
        "reasoning": "Question appears substantive but does not explicitly require a past specific example.",
        "source": "heuristic",
    }


def _classify_turn(
    question_text: str,
    ollama_model: str | None,
    ollama_host: str,
) -> dict[str, str | bool]:
    if not ollama_model:
        return _heuristic_turn_classification(question_text)

    prompt = f"""Classify this interviewer turn for transcript scoring.

Return JSON only:
{{
  "turn_type": "behavioral" | "non_behavioral" | "non_question",
  "is_scorable": true | false,
  "reasoning": "one sentence"
}}

Definitions:
- behavioral: requires a specific past example or concrete prior experience
- non_behavioral: scorable interview question that does not require a specific past example
- non_question: social, logistics, greeting, setup, or otherwise not scorable

Interviewer turn:
{question_text}
"""
    parsed = _ollama_generate_json(prompt, ollama_model, ollama_host)
    if not parsed:
        return _heuristic_turn_classification(question_text)

    turn_type = str(parsed.get("turn_type", "")).strip().lower()
    if turn_type not in {"behavioral", "non_behavioral", "non_question"}:
        return _heuristic_turn_classification(question_text)
    return {
        "turn_type": turn_type,
        "is_scorable": bool(parsed.get("is_scorable", turn_type != "non_question")),
        "reasoning": str(parsed.get("reasoning", "Ollama classification.")),
        "source": "ollama",
    }


def _heuristic_is_follow_up(question_text: str) -> bool:
    cleaned = question_text.strip()
    return any(pattern.search(cleaned) for pattern in FOLLOW_UP_PATTERNS)


def _is_follow_up_question(
    question_text: str,
    previous_case: dict[str, Any] | None,
    ollama_model: str | None,
    ollama_host: str,
) -> bool:
    if previous_case is None:
        return False
    if not ollama_model:
        return _heuristic_is_follow_up(question_text)

    prompt = f"""Decide whether this interviewer turn is a follow-up probe on the immediately previous interview case.

Return JSON only:
{{
  "is_follow_up": true | false,
  "reasoning": "one sentence"
}}

Previous main question:
{previous_case.get("question", "")}

Previous candidate response:
{previous_case.get("response", "")}

Current interviewer turn:
{question_text}
"""
    parsed = _ollama_generate_json(prompt, ollama_model, ollama_host)
    if not parsed:
        return _heuristic_is_follow_up(question_text)
    return bool(parsed.get("is_follow_up", False))


def _heuristic_probe_type(question_text: str) -> str:
    cleaned = question_text.strip()
    if any(pattern.search(cleaned) for pattern in CLARIFYING_PATTERNS):
        return "clarifying"
    if any(pattern.search(cleaned) for pattern in DEEPENING_PATTERNS):
        return "deepening"
    return "deepening" if _heuristic_is_follow_up(cleaned) else "clarifying"


def _classify_probe_type(
    question_text: str,
    ollama_model: str | None,
    ollama_host: str,
) -> tuple[str, str]:
    if not ollama_model:
        return _heuristic_probe_type(question_text), "heuristic"

    prompt = f"""Classify this interview follow-up probe.

Return JSON only:
{{
  "probe_type": "clarifying" | "deepening",
  "reasoning": "one sentence"
}}

Definitions:
- clarifying: interviewer is trying to recover specificity or missing details
- deepening: interviewer is pressing deeper on an already substantive answer

Follow-up question:
{question_text}
"""
    parsed = _ollama_generate_json(prompt, ollama_model, ollama_host)
    probe_type = str(parsed.get("probe_type", "")).strip().lower() if parsed else ""
    if probe_type not in {"clarifying", "deepening"}:
        return _heuristic_probe_type(question_text), "heuristic"
    return probe_type, "ollama"


def parse_transcript_to_test_cases(
    raw_text: str,
    ollama_model: str | None = None,
    ollama_host: str = "http://127.0.0.1:11434",
    print_each_entry: bool = False,
) -> list[dict[str, Any]]:
    turns = _extract_turns(raw_text)
    cases: list[dict[str, Any]] = []
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
        consumed_candidate = False
        if i + 1 < len(turns) and turns[i + 1]["speaker"] == "candidate":
            response = turns[i + 1]["text"].strip()
            consumed_candidate = True

        turn_info = _classify_turn(question, ollama_model, ollama_host)
        if not bool(turn_info["is_scorable"]):
            i += 2 if consumed_candidate else 1
            continue

        previous_case = cases[-1] if cases else None
        if _is_follow_up_question(question, previous_case, ollama_model, ollama_host):
            probe_type, probe_source = _classify_probe_type(
                question, ollama_model, ollama_host
            )
            follow_up = {
                "question": question,
                "response": response,
                "probe_type": probe_type,
                "classification_source": probe_source,
            }
            cases[-1]["follow_ups"].append(
                {
                    "question": follow_up["question"],
                    "response": follow_up["response"],
                    "probe_type": follow_up["probe_type"],
                    "classification_source": follow_up["classification_source"],
                }
            )
            if print_each_entry:
                print(
                    f'ENTRY {cases[-1]["id"]} follow_up '
                    f'({follow_up["classification_source"]}): '
                    f'{json.dumps(follow_up, ensure_ascii=False)}'
                )
        else:
            case_entry = {
                "id": case_id,
                "label": f"Auto case {case_id}",
                "turn_type": str(turn_info["turn_type"]),
                "rubric_type": str(turn_info["turn_type"]),
                "classification_source": str(turn_info["source"]),
                "classification_reasoning": str(turn_info["reasoning"]),
                "question": question,
                "response": response,
                "follow_ups": [],
                "expected": {},
            }
            cases.append(case_entry)
            if print_each_entry:
                print(
                    f'ENTRY {case_entry["id"]} '
                    f'({case_entry["classification_source"]}): '
                    f'{json.dumps(case_entry, ensure_ascii=False)}'
                )
            case_id += 1

        i += 2 if consumed_candidate else 1

    return cases


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert transcript text into evaluator-ready JSON."
    )
    parser.add_argument("input", help="Path to transcript text file")
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation (default: 2)",
    )
    parser.add_argument(
        "--ollama-model",
        default=os.environ.get("OLLAMA_MODEL"),
        help="Optional Ollama model name for turn/probe classification.",
    )
    parser.add_argument(
        "--ollama-host",
        default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        help="Ollama host URL (default: http://127.0.0.1:11434).",
    )
    parser.add_argument(
        "--print-each-entry",
        action="store_true",
        help="Print each completed case/follow-up as it is parsed.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if input_path.suffix.lower() != ".txt":
        raise ValueError(f"Input must be a .txt file. Got: {input_path.name}")

    output_path = input_path.with_suffix(".json")
    raw_text = input_path.read_text(encoding="utf-8")
    parsed_cases = parse_transcript_to_test_cases(
        raw_text,
        ollama_model=args.ollama_model,
        ollama_host=args.ollama_host,
        print_each_entry=args.print_each_entry,
    )
    output_path.write_text(
        json.dumps(parsed_cases, indent=args.indent), encoding="utf-8"
    )

    classifier_mode = (
        f"ollama:{args.ollama_model}" if args.ollama_model else "heuristic-only"
    )
    print(f"Wrote JSON to: {output_path}")
    print(f"Cases: {len(parsed_cases)}")
    print(f"Classifier: {classifier_mode}")


if __name__ == "__main__":
    main()
