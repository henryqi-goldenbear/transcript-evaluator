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
        "classification_source": "heuristic"
      }
    ],
    "expected": {}
  }
]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
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
    re.compile(r"\bhere'?s how (i'?d|i would) like to use\b", re.IGNORECASE),
    re.compile(r"\bwe'?ll save\b.*\bfor your questions\b", re.IGNORECASE),
    re.compile(r"\bdoes that work\b", re.IGNORECASE),
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


def _heuristic_turn_classification(question_text: str) -> dict[str, str | bool]:
    cleaned = " ".join(question_text.strip().split())
    if not cleaned:
        return {
            "turn_type": "not_scorable",
            "is_scorable": False,
            "reasoning": "Empty interviewer turn.",
            "source": "heuristic",
        }
    if any(pattern.search(cleaned) for pattern in NON_QUESTION_PATTERNS):
        return {
            "turn_type": "not_scorable",
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
    heuristic_info = _heuristic_turn_classification(question_text)
    if not bool(heuristic_info["is_scorable"]) or not ollama_model:
        return heuristic_info

    prompt = f"""Classify this interviewer turn for transcript scoring.
            Return JSON only:
            {{
            "turn_type": "behavioral" | "non_behavioral" | "not_scorable",
            "is_scorable": true | false,
            "reasoning": "one sentence"
            }}

            Definitions:
            - behavioral: requires a specific past example or concrete prior experience
            - non_behavioral: scorable interview question that does not require a specific past example
            - not_scorable: social, logistics, greeting, setup, or otherwise not an interview scoring question

            Important:
            - Use not_scorable for greetings, video/audio/calendar logistics, rapport-building chatter, and setup prompts.
            - Do not classify non-scorable turns as non_behavioral.

            Interviewer turn:
            {question_text}
            """
    parsed = _ollama_generate_json(prompt, ollama_model, ollama_host)
    if not parsed:
        return _heuristic_turn_classification(question_text)

    turn_type = str(parsed.get("turn_type", "")).strip().lower()
    if turn_type in {"non_question", "nonscorable", "non_scorable", "not scorable", "not-scorable"}:
        turn_type = "not_scorable"
    if turn_type not in {"behavioral", "non_behavioral", "not_scorable"}:
        return _heuristic_turn_classification(question_text)
    raw_is_scorable = parsed.get("is_scorable", turn_type != "not_scorable")
    if isinstance(raw_is_scorable, str):
        is_scorable = raw_is_scorable.strip().lower() == "true"
    else:
        is_scorable = bool(raw_is_scorable)
    if turn_type == "not_scorable":
        is_scorable = False
    return {
        "turn_type": turn_type,
        "is_scorable": is_scorable,
        "reasoning": str(parsed.get("reasoning", "Ollama classification.")),
        "source": "ollama",
    }


def _heuristic_is_follow_up(question_text: str) -> bool:
    cleaned = question_text.strip()
    return any(pattern.search(cleaned) for pattern in FOLLOW_UP_PATTERNS)


def _is_follow_up_question(question_text: str, previous_case: dict[str, Any] | None) -> bool:
    if previous_case is None:
        return False
    return _heuristic_is_follow_up(question_text)


def _heuristic_probe_type(question_text: str) -> str:
    cleaned = question_text.strip()
    if any(pattern.search(cleaned) for pattern in CLARIFYING_PATTERNS):
        return "clarifying"
    if any(pattern.search(cleaned) for pattern in DEEPENING_PATTERNS):
        return "deepening"
    return "deepening" if _heuristic_is_follow_up(cleaned) else "clarifying"


def parse_transcript_to_test_cases(
    raw_text: str,
    ollama_model: str | None = None,
    ollama_host: str = "http://127.0.0.1:11434",
    print_each_entry: bool = False,
    entry_logger: Callable[[str], None] | None = None,
    workers: int = 8,
) -> list[dict[str, Any]]:
    turns = _extract_turns(raw_text)
    interviewer_items: list[dict[str, str]] = []
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

        interviewer_items.append(
            {
                "question": question,
                "response": response,
            }
        )
        i += 2 if consumed_candidate else 1

    turn_infos: list[dict[str, str | bool]] = []
    turn_timings: list[tuple[datetime, datetime]] = []
    worker_limit = max(1, workers)

    def _timed_classify(question_text: str) -> tuple[dict[str, str | bool], datetime, datetime]:
        started_at = datetime.now()
        info = _classify_turn(question_text, ollama_model, ollama_host)
        ended_at = datetime.now()
        return info, started_at, ended_at

    if interviewer_items:
        max_workers = min(worker_limit, len(interviewer_items))
        if entry_logger:
            entry_logger(
                f"per_turn_parallel_classification=started at {datetime.now().isoformat(timespec='seconds')} "
                f"workers={max_workers} requested_workers={worker_limit}"
            )
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    _timed_classify,
                    item["question"],
                )
                for item in interviewer_items
            ]
            for idx, future in enumerate(futures):
                try:
                    turn_info, started_at, ended_at = future.result()
                    turn_infos.append(turn_info)
                    turn_timings.append((started_at, ended_at))
                except Exception:
                    turn_infos.append(
                        _heuristic_turn_classification(interviewer_items[idx]["question"])
                    )
                    fallback_at = datetime.now()
                    turn_timings.append((fallback_at, fallback_at))
        if entry_logger:
            entry_logger(f"per_turn_parallel_classification=finished at {datetime.now().isoformat(timespec='seconds')}")

    cases: list[dict[str, Any]] = []
    case_id = 1

    for item, turn_info, timing in zip(interviewer_items, turn_infos, turn_timings):
        question = item["question"]
        response = item["response"]
        entry_started_at, entry_ended_at = timing
        duration_seconds = (entry_ended_at - entry_started_at).total_seconds()

        if not bool(turn_info["is_scorable"]):
            if entry_logger:
                entry_logger(
                    f'skipped turn_type={turn_info["turn_type"]} '
                    f'source={turn_info["source"]} '
                    f'start={entry_started_at.isoformat(timespec="seconds")} '
                    f'end={entry_ended_at.isoformat(timespec="seconds")} '
                    f'duration_seconds={duration_seconds:.3f}'
                )
            continue

        previous_case = cases[-1] if cases else None
        if _is_follow_up_question(question, previous_case):
            follow_up = {
                "question": question,
                "response": response,
                "probe_type": _heuristic_probe_type(question),
                "classification_source": "heuristic",
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
            if entry_logger:
                follow_up_ended_at = datetime.now()
                follow_up_duration_seconds = (
                    follow_up_ended_at - entry_started_at
                ).total_seconds()
                entry_logger(
                    f'follow_up case_id={cases[-1]["id"]} '
                    f'source={follow_up["classification_source"]} '
                    f'start={entry_started_at.isoformat(timespec="seconds")} '
                    f'end={follow_up_ended_at.isoformat(timespec="seconds")} '
                    f'duration_seconds={follow_up_duration_seconds:.3f}'
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
            if entry_logger:
                entry_logger(
                    f'case id={case_entry["id"]} '
                    f'source={case_entry["classification_source"]} '
                    f'start={entry_started_at.isoformat(timespec="seconds")} '
                    f'end={entry_ended_at.isoformat(timespec="seconds")} '
                    f'duration_seconds={duration_seconds:.3f}'
                )
            case_id += 1

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
        help="Optional Ollama model name for turn classification only.",
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
    parser.add_argument(
        "--entry-log-file",
        help="Optional path for per-entry timing logs. Defaults to <input>_entry_timing.log.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Maximum number of interviewer turns to classify in parallel (default: 8).",
    )
    args = parser.parse_args()

    if args.workers < 1:
        raise ValueError(f"--workers must be at least 1. Got: {args.workers}")

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if input_path.suffix.lower() != ".txt":
        raise ValueError(f"Input must be a .txt file. Got: {input_path.name}")

    output_path = input_path.with_suffix(".json")
    entry_log_path = (
        Path(args.entry_log_file)
        if args.entry_log_file
        else Path("log") / f"{input_path.stem}_entry_timing.log"
    )
    entry_log_path.parent.mkdir(parents=True, exist_ok=True)
    entry_log_path.write_text("", encoding="utf-8")

    def entry_logger(message: str) -> None:
        with entry_log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"{message}\n")

    raw_text = input_path.read_text(encoding="utf-8")
    parsed_cases = parse_transcript_to_test_cases(
        raw_text,
        ollama_model=args.ollama_model,
        ollama_host=args.ollama_host,
        print_each_entry=args.print_each_entry,
        entry_logger=entry_logger,
        workers=args.workers,
    )
    output_path.write_text(
        json.dumps(parsed_cases, indent=args.indent), encoding="utf-8"
    )

    classifier_mode = (
        f"ollama:{args.ollama_model}" if args.ollama_model else "heuristic-only"
    )
    print(f"Wrote JSON to: {output_path}")
    print(f"Wrote entry timing log to: {entry_log_path}")
    print(f"Cases: {len(parsed_cases)}")
    print(f"Classifier: {classifier_mode}")
    print(f"Workers: {args.workers}")


if __name__ == "__main__":
    main()
