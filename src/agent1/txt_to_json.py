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
    "classification_source": "ministral:<model>" | "ollama" | "heuristic",
    "classification_reasoning": "...",
    "question": "...",
    "response": "...",
    "follow_ups": [
      {
        "question": "...",
        "response": "...",
        "probe_type": "clarifying" | "deepening",
        "classification_source": "ministral:<model>" | "ollama" | "heuristic"
      }
    ],
    "expected": {}
  }
]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import socket
import subprocess
import sys
import time
import unicodedata
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse
from urllib import error, request
from src.bridge.agent2_connection import Agent2Bridge, resolve_pipeline_log_path, write_json_response
from src.agent2.agent2 import (
    MAX_TEXT_CHARS,
    build_structure_review_prompt,
    call_mistral_agent,
    extract_text,
    shorten,
)
from src.shared.patterns import (
    BEHAVIORAL_PATTERNS,
    CLARIFYING_PATTERNS,
    DEEPENING_PATTERNS,
    FOLLOW_UP_PATTERNS,
    NON_QUESTION_PATTERNS,
    SPEAKER_RE,
)
from src.shared.interview_db import DEFAULT_DB_PATH, save_agent1_result, save_interview_cases


LOGGER = logging.getLogger(__name__)
EVALUATOR_PORT = 3000
AGENT2_BRIDGE = Agent2Bridge()
DEFAULT_MISTRAL_MODEL = "mistral-small-latest"
DEFAULT_MISTRAL_API_BASE = "https://api.mistral.ai/v1"
DEFAULT_CLASSIFIER_PROVIDER = "ministral"
DEFAULT_CLASSIFIER_MODEL = "ministral-3b-latest"
DETERMINISTIC_TEMPERATURE = 0
EVALUATOR_ASSET_VERSION = "mistral-small-4"
SEGMENT_NEW_CASE = "new_case"
SEGMENT_FOLLOW_UP = "follow_up"
SEGMENT_NON_SCORABLE = "non_scorable"
DEFAULT_STRUCTURE_REVIEW_ITERATIONS = -1
MAX_STRUCTURE_REVIEW_NO_PROGRESS = 3


MAIN_QUESTION_PATTERNS = [
    re.compile(r"\btell me about yourself\b", re.IGNORECASE),
    re.compile(r"\bwalk me through\b.*\b(resume|background|career|experience|role)\b", re.IGNORECASE),
    re.compile(r"\b(resume|background|career path)\b", re.IGNORECASE),
    re.compile(r"\bwhy\b.*\b(this|our)\b.*\b(role|company|team|job)\b", re.IGNORECASE),
    re.compile(r"\bwhy\s+[A-Z][A-Za-z0-9_-]+\b"),
    re.compile(r"\bwhat drew you\b", re.IGNORECASE),
    re.compile(r"\bwhat interests you\b", re.IGNORECASE),
    re.compile(r"\bwhy are you interested\b", re.IGNORECASE),
    re.compile(r"\bhow (have you used|do you use)\b.*\bproduction\b", re.IGNORECASE),
    re.compile(r"\bhow do you (work|partner|collaborate)\b", re.IGNORECASE),
    re.compile(r"\b(product managers|design|security|cross-functional|stakeholders)\b", re.IGNORECASE),
    re.compile(r"\bstructure services\b", re.IGNORECASE),
    re.compile(r"\bwhat is your greatest weakness\b", re.IGNORECASE),
    re.compile(r"\bwhat (are|is) your (strengths|weaknesses)\b", re.IGNORECASE),
    re.compile(r"\bhow do you handle competing priorities\b", re.IGNORECASE),
    re.compile(r"\bwhat broke first\b", re.IGNORECASE),
    re.compile(r"\bsame system or separate\b", re.IGNORECASE),
    re.compile(r"\bany gap\b", re.IGNORECASE),
]

DEPENDENT_FOLLOW_UP_PATTERNS = [
    re.compile(r"^\s*(you mentioned|you said|when you said)\b", re.IGNORECASE),
    re.compile(r"^\s*(can|could) you (be more specific|expand|clarify|go deeper|tell me more)\b", re.IGNORECASE),
    re.compile(r"^\s*(what did you mean|what do you mean)\b", re.IGNORECASE),
    re.compile(r"^\s*what (would have|could have|might have|broke|happened next)\b", re.IGNORECASE),
    re.compile(r"^\s*what made\b", re.IGNORECASE),
    re.compile(r"^\s*what was your role\b", re.IGNORECASE),
    re.compile(r"^\s*i hear\b.*\b(can you|give me|example)\b", re.IGNORECASE),
    re.compile(r"^\s*i'?d like\b.*\b(context|specific|more)\b", re.IGNORECASE),
]

NON_SCORABLE_PATTERNS = [
    re.compile(r"\bhow('?s| is) your day\b", re.IGNORECASE),
    re.compile(r"\bnice to meet you\b", re.IGNORECASE),
    re.compile(r"\bcan you hear me\b", re.IGNORECASE),
    re.compile(r"\bcan you see my screen\b", re.IGNORECASE),
    re.compile(r"\bany trouble with (the )?(video|audio|link|calendar invite)\b", re.IGNORECASE),
    re.compile(r"\bthanks for joining\b", re.IGNORECASE),
    re.compile(r"\bshall we get started\b", re.IGNORECASE),
    re.compile(r"\bhere'?s how\b.*\b(use|spend).*\b(minutes|time)\b", re.IGNORECASE),
    re.compile(r"\bdoes that work\b", re.IGNORECASE),
    re.compile(r"\bwe'?ll follow up\b", re.IGNORECASE),
    re.compile(r"\bthanks for the\b.*\b(today|walkthrough|conversation)\b", re.IGNORECASE),
    re.compile(r"\bhave a good\b", re.IGNORECASE),
]

CANDIDATE_QA_START_PATTERNS = [
    re.compile(r"\bwhat do you want to know from us\b", re.IGNORECASE),
    re.compile(r"\bwhat questions do you have\b", re.IGNORECASE),
    re.compile(r"\bdo you have any questions\b", re.IGNORECASE),
    re.compile(r"\bquestions for (me|us)\b", re.IGNORECASE),
]


def local_time_mark() -> str:
    return datetime.now().strftime("%H:%M:%S")


def extract_json_fragment(raw_response: str) -> Any | None:
    raw = raw_response.strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass

    for opener, closer in (("{", "}"), ("[", "]")):
        start = raw.find(opener)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(raw)):
            char = raw[index]
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == opener:
                depth += 1
            elif char == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[start : index + 1])
                    except json.JSONDecodeError:
                        break
    return None


def normalize_agent2_case(case: dict[str, Any], case_id: int) -> dict[str, Any]:
    turn_type = str(case.get("turn_type") or case.get("rubric_type") or "non_behavioral").strip()
    if turn_type not in {"behavioral", "non_behavioral"}:
        turn_type = "non_behavioral"
    follow_ups = []
    for follow in case.get("follow_ups") or []:
        if not isinstance(follow, dict):
            continue
        question = str(follow.get("question", "")).strip()
        response = str(follow.get("response", "")).strip()
        if not question:
            continue
        probe_type = str(follow.get("probe_type", "")).strip().lower()
        if probe_type not in {"clarifying", "deepening"}:
            probe_type = _heuristic_probe_type(question)
        follow_ups.append(
            {
                "question": question,
                "response": response,
                "probe_type": probe_type,
                "classification_source": "agent2-structure-review",
            }
        )

    return {
        "id": case_id,
        "label": str(case.get("label") or f"Auto case {case_id}"),
        "turn_type": turn_type,
        "rubric_type": turn_type,
        "classification_source": "agent2-structure-review",
        "classification_reasoning": str(
            case.get("classification_reasoning")
            or "Agent 2 approved this case during structure review."
        ),
        "question": str(case.get("question", "")).strip(),
        "response": str(case.get("response", "")).strip(),
        "follow_ups": follow_ups,
        "expected": case.get("expected") if isinstance(case.get("expected"), dict) else {},
    }


def normalize_agent2_cases(raw_cases: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_cases, list):
        raise ValueError("Agent 2 desired_cases must be a list.")
    cases = []
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            continue
        if not str(raw_case.get("question", "")).strip():
            continue
        cases.append(normalize_agent2_case(raw_case, len(cases) + 1))
    if not cases:
        raise ValueError("Agent 2 desired_cases did not include any scorable cases.")
    return cases


def normalize_agent2_operations(raw_operations: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_operations, list):
        return []
    allowed_ops = {
        "split_follow_up_to_case",
        "add_missing_case",
        "remove_case",
        "move_follow_up",
        "change_probe_type",
    }
    operations = []
    for raw_op in raw_operations:
        if not isinstance(raw_op, dict):
            continue
        op_name = str(raw_op.get("op", "")).strip().lower()
        if op_name not in allowed_ops:
            continue
        operation = dict(raw_op)
        operation["op"] = op_name
        operations.append(operation)
    return operations


def parse_agent2_structure_response(raw_text: str) -> dict[str, Any]:
    parsed = extract_json_fragment(raw_text)
    if not isinstance(parsed, dict):
        raise ValueError("Agent 2 structure review did not return a JSON object.")
    parsed["satisfied"] = bool(parsed.get("satisfied"))
    parsed["issues"] = parsed.get("issues") if isinstance(parsed.get("issues"), list) else []
    if isinstance(parsed.get("desired_cases"), list) and parsed["desired_cases"]:
        parsed["desired_cases"] = normalize_agent2_cases(parsed.get("desired_cases"))
    else:
        parsed["desired_cases"] = []
    parsed["operations"] = normalize_agent2_operations(parsed.get("operations"))
    return parsed


def build_structure_json_repair_prompt(raw_response: str) -> str:
    return f"""Convert the text below into the exact Agent 2 structure-review JSON schema.

Return JSON only. No markdown, no prose outside JSON.
Your first character must be "{{" and your last character must be "}}".

If the text says the structure is acceptable, set "satisfied": true.
If the text describes structural problems, set "satisfied": false, include those problems in
"issues", and include compact "operations" when the needed edits are clear.

Schema:
{{
  "satisfied": true | false,
  "summary": "one short sentence",
  "issues": [
    {{
      "severity": "high" | "medium" | "low",
      "case_id": <number or null>,
      "question": "question or nearby transcript text",
      "problem": "what is structurally wrong",
      "correction": "what Agent 0 should change"
    }}
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
  ],
  "desired_cases": []
}}

Text to convert:
{shorten(raw_response, MAX_TEXT_CHARS)}
"""


def write_structure_review_log(
    input_path: Path,
    iteration: int,
    prompt: str,
    response_text: str,
    review: dict[str, Any],
) -> Path:
    log_dir = agent2_structure_review_dir_for_input(input_path)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{input_path.stem}_agent2_structure_review_{iteration}.md"
    log_path.write_text(
        "\n".join(
            [
                "# Agent 2 Structure Review",
                "",
                f"Iteration: {iteration}",
                f"Satisfied: {review.get('satisfied')}",
                f"Summary: {review.get('summary', '')}",
                "",
                "## Issues",
                json.dumps(review.get("issues", []), indent=2),
                "",
                "## Operations",
                json.dumps(review.get("operations", []), indent=2),
                "",
                "## Response",
                response_text,
                "",
                "## Prompt",
                prompt,
            ]
        ),
        encoding="utf-8",
    )
    return log_path


def write_structure_review_prompt_log(input_path: Path, iteration: int, prompt: str) -> Path:
    log_dir = agent2_structure_review_dir_for_input(input_path)
    log_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = log_dir / f"{input_path.stem}_agent2_structure_review_{iteration}_prompt.md"
    prompt_path.write_text(
        "\n".join(
            [
                "# Agent 2 Structure Review Prompt",
                "",
                f"Iteration: {iteration}",
                "",
                "## Prompt",
                prompt,
            ]
        ),
        encoding="utf-8",
    )
    return prompt_path


def truncate_for_structure(value: str, limit: int = 260) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def compact_structure_context(raw_text: str, cases: list[dict[str, Any]]) -> dict[str, Any]:
    turns = _extract_turns(raw_text)
    compact_turns = [
        {
            "turn_index": turn["index"],
            "speaker": turn["speaker"],
            "text": truncate_for_structure(str(turn.get("text", ""))),
        }
        for turn in turns
    ]
    compact_cases = []
    for case in cases:
        compact_cases.append(
            {
                "id": case.get("id"),
                "turn_type": case.get("turn_type"),
                "question": truncate_for_structure(str(case.get("question", ""))),
                "response": truncate_for_structure(str(case.get("response", "")), 180),
                "follow_ups": [
                    {
                        "question": truncate_for_structure(str(follow.get("question", ""))),
                        "response": truncate_for_structure(str(follow.get("response", "")), 180),
                        "probe_type": follow.get("probe_type"),
                    }
                    for follow in case.get("follow_ups", []) or []
                ],
            }
        )
    return {
        "transcript_turns": compact_turns,
        "current_cases": compact_cases,
    }


def normalize_for_match(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").lower())
    normalized = normalized.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def text_matches(needle: str, haystack: str) -> bool:
    clean_needle = normalize_for_match(needle)
    clean_haystack = normalize_for_match(haystack)
    if not clean_needle or not clean_haystack:
        return False
    return clean_needle in clean_haystack or clean_haystack in clean_needle


def find_case_index(cases: list[dict[str, Any]], case_id: Any) -> int | None:
    try:
        target_id = int(case_id)
    except (TypeError, ValueError):
        return None
    for index, case in enumerate(cases):
        if int(case.get("id", -1)) == target_id:
            return index
    return None


def find_follow_up(case: dict[str, Any], follow_question: str) -> tuple[int, dict[str, Any]] | None:
    for index, follow in enumerate(case.get("follow_ups", []) or []):
        if text_matches(follow_question, str(follow.get("question", ""))):
            return index, follow
    return None


def infer_turn_type(question: str, requested_turn_type: str = "") -> str:
    requested = requested_turn_type.strip().lower()
    if requested in {"behavioral", "non_behavioral"}:
        return requested
    return "behavioral" if any(pattern.search(question) for pattern in BEHAVIORAL_PATTERNS) else "non_behavioral"


def find_response_after_question(raw_text: str, question: str) -> str:
    turns = _extract_turns(raw_text)
    for index, turn in enumerate(turns):
        if turn["speaker"] == "interviewer" and text_matches(question, str(turn.get("text", ""))):
            if index + 1 < len(turns) and turns[index + 1]["speaker"] == "candidate":
                return str(turns[index + 1].get("text", "")).strip()
    return ""


def renumber_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for index, case in enumerate(cases, start=1):
        case["id"] = index
        case["label"] = f"Auto case {index}"
    return cases


def make_case_from_question(
    case_id: int,
    question: str,
    response: str,
    turn_type: str,
    reasoning: str,
) -> dict[str, Any]:
    return {
        "id": case_id,
        "label": f"Auto case {case_id}",
        "turn_type": turn_type,
        "rubric_type": turn_type,
        "classification_source": "agent2-structure-review",
        "classification_reasoning": reasoning or "Agent 2 requested this structure correction.",
        "question": question.strip(),
        "response": response.strip(),
        "follow_ups": [],
        "expected": {},
    }


def case_exists(cases: list[dict[str, Any]], question: str) -> bool:
    return any(text_matches(question, str(case.get("question", ""))) for case in cases)


def find_case_by_question(cases: list[dict[str, Any]], question: str) -> tuple[int, dict[str, Any]] | None:
    for index, case in enumerate(cases):
        if text_matches(question, str(case.get("question", ""))):
            return index, case
    return None


def find_follow_up_anywhere(
    cases: list[dict[str, Any]],
    follow_question: str,
) -> tuple[int, int, dict[str, Any]] | None:
    for case_index, case in enumerate(cases):
        found = find_follow_up(case, follow_question)
        if found is not None:
            follow_index, follow = found
            return case_index, follow_index, follow
    return None


def operation_already_satisfied(cases: list[dict[str, Any]], operation: dict[str, Any]) -> bool:
    op_name = operation.get("op")
    follow_question = str(operation.get("follow_up_question") or operation.get("question") or "")
    question = str(operation.get("question") or operation.get("follow_up_question") or "")

    if op_name in {"split_follow_up_to_case", "add_missing_case"}:
        return bool(question and case_exists(cases, question))

    if op_name == "move_follow_up":
        target_index = find_case_index(cases, operation.get("target_case_id"))
        if target_index is not None and find_follow_up(cases[target_index], follow_question) is not None:
            return True
        return bool(find_case_by_question(cases, follow_question))

    if op_name == "change_probe_type":
        source_index = find_case_index(cases, operation.get("source_case_id"))
        probe_type = str(operation.get("probe_type", "")).strip().lower()
        if source_index is None or probe_type not in {"clarifying", "deepening"}:
            return False
        found = find_follow_up(cases[source_index], follow_question)
        if found is None:
            return bool(find_case_by_question(cases, follow_question))
        _, follow = found
        return str(follow.get("probe_type", "")).strip().lower() == probe_type

    if op_name == "remove_case":
        case_index = find_case_index(cases, operation.get("source_case_id") or operation.get("case_id"))
        if case_index is None:
            return True
        op_question = str(operation.get("question", "")).strip()
        return bool(op_question and not case_exists(cases, op_question))

    return False


def all_operations_already_satisfied(cases: list[dict[str, Any]], operations: list[dict[str, Any]]) -> bool:
    return bool(operations) and all(operation_already_satisfied(cases, operation) for operation in operations)


def apply_agent2_structure_operations(
    cases: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    raw_text: str,
) -> list[dict[str, Any]]:
    updated = json.loads(json.dumps(cases))
    for operation in operations:
        op_name = operation.get("op")
        reason = str(operation.get("reason", "Agent 2 structure operation."))
        if op_name == "split_follow_up_to_case":
            source_index = find_case_index(updated, operation.get("source_case_id"))
            if source_index is None:
                continue
            found = find_follow_up(updated[source_index], str(operation.get("follow_up_question", "")))
            if found is None:
                continue
            follow_index, follow = found
            del updated[source_index]["follow_ups"][follow_index]
            question = str(follow.get("question", "")).strip()
            response = str(follow.get("response", "")).strip()
            turn_type = infer_turn_type(question, str(operation.get("turn_type", "")))
            new_case = make_case_from_question(0, question, response, turn_type, reason)
            updated.insert(source_index + 1, new_case)
        elif op_name == "add_missing_case":
            question = str(operation.get("question", "")).strip()
            if not question or case_exists(updated, question):
                continue
            response = str(operation.get("response", "")).strip() or find_response_after_question(raw_text, question)
            turn_type = infer_turn_type(question, str(operation.get("turn_type", "")))
            updated.append(make_case_from_question(0, question, response, turn_type, reason))
        elif op_name == "remove_case":
            case_index = find_case_index(updated, operation.get("source_case_id") or operation.get("case_id"))
            if case_index is not None:
                del updated[case_index]
        elif op_name == "move_follow_up":
            source_index = find_case_index(updated, operation.get("source_case_id"))
            target_index = find_case_index(updated, operation.get("target_case_id"))
            if source_index is None or target_index is None:
                if operation_already_satisfied(updated, operation):
                    continue
                continue
            found = find_follow_up(updated[source_index], str(operation.get("follow_up_question", "")))
            if found is None:
                if operation_already_satisfied(updated, operation):
                    continue
                anywhere = find_follow_up_anywhere(
                    updated,
                    str(operation.get("follow_up_question", "")),
                )
                if anywhere is None:
                    continue
                source_index, follow_index, follow = anywhere
                del updated[source_index]["follow_ups"][follow_index]
                updated[target_index].setdefault("follow_ups", []).append(follow)
                continue
            follow_index, follow = found
            del updated[source_index]["follow_ups"][follow_index]
            updated[target_index].setdefault("follow_ups", []).append(follow)
        elif op_name == "change_probe_type":
            source_index = find_case_index(updated, operation.get("source_case_id"))
            if source_index is None:
                continue
            found = find_follow_up(updated[source_index], str(operation.get("follow_up_question", "")))
            if found is None:
                continue
            _, follow = found
            probe_type = str(operation.get("probe_type", "")).strip().lower()
            if probe_type in {"clarifying", "deepening"}:
                follow["probe_type"] = probe_type
                follow["classification_source"] = "agent2-structure-review"
    return renumber_cases(updated)


def structure_fingerprint(cases: list[dict[str, Any]]) -> str:
    outline = [
        {
            "question": normalize_for_match(str(case.get("question", ""))),
            "follow_ups": [
                {
                    "question": normalize_for_match(str(follow.get("question", ""))),
                    "probe_type": str(follow.get("probe_type", "")),
                }
                for follow in case.get("follow_ups", []) or []
            ],
        }
        for case in cases
    ]
    return json.dumps(outline, sort_keys=True)


def write_structure_review_failure_log(
    input_path: Path,
    iteration: int,
    prompt: str,
    response_text: str,
    error_message: str,
    repair_response_text: str = "",
) -> Path:
    log_dir = agent2_structure_review_dir_for_input(input_path)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{input_path.stem}_agent2_structure_review_{iteration}_parse_error.md"
    log_path.write_text(
        "\n".join(
            [
                "# Agent 2 Structure Review Parse Error",
                "",
                f"Iteration: {iteration}",
                f"Error: {error_message}",
                "",
                "## Raw Response",
                response_text,
                "",
                "## Repair Response",
                repair_response_text or "(not attempted or empty)",
                "",
                "## Prompt",
                prompt,
            ]
        ),
        encoding="utf-8",
    )
    return log_path


def request_structure_review(prompt: str) -> str:
    response = call_mistral_agent(prompt)
    return extract_text(response) or json.dumps(response, indent=2)


def request_repaired_structure_review(raw_response: str) -> str:
    response = call_mistral_agent(build_structure_json_repair_prompt(raw_response))
    return extract_text(response) or json.dumps(response, indent=2)


def run_agent2_structure_review_loop(
    raw_text: str,
    parsed_cases: list[dict[str, Any]],
    input_path: Path,
    max_iterations: int = DEFAULT_STRUCTURE_REVIEW_ITERATIONS,
) -> list[dict[str, Any]]:
    if max_iterations == 0:
        LOGGER.info("Agent 2 structure review disabled.")
        return parsed_cases
    if not os.environ.get("MISTRAL_API_KEY"):
        LOGGER.warning("Skipping Agent 2 structure review because MISTRAL_API_KEY is not set.")
        return parsed_cases

    current_cases = parsed_cases
    no_progress_count = 0
    iteration = 1
    while max_iterations < 0 or iteration <= max_iterations:
        compact_context = compact_structure_context(raw_text, current_cases)
        prompt = build_structure_review_prompt(
            compact_context,
            current_cases,
            iteration,
            input_path.as_posix(),
        )
        iteration_label = "until satisfied" if max_iterations < 0 else str(max_iterations)
        LOGGER.info(
            "Starting Agent 2 structure review iteration %s/%s",
            iteration,
            iteration_label,
        )
        prompt_log_path = write_structure_review_prompt_log(input_path, iteration, prompt)
        LOGGER.info("Wrote Agent 2 structure review prompt to %s", prompt_log_path)
        response_text = request_structure_review(prompt)
        repair_response_text = ""
        try:
            review = parse_agent2_structure_response(response_text)
        except Exception as exc:
            LOGGER.warning(
                "Agent 2 structure review iteration %s returned non-JSON; requesting repair: %s",
                iteration,
                exc,
            )
            try:
                repair_response_text = request_repaired_structure_review(response_text)
                review = parse_agent2_structure_response(repair_response_text)
                response_text = repair_response_text
            except Exception as repair_exc:
                log_path = write_structure_review_failure_log(
                    input_path,
                    iteration,
                    prompt,
                    response_text,
                    str(repair_exc),
                    repair_response_text,
                )
                LOGGER.warning(
                    "Agent 2 structure review parse failed after repair. log=%s",
                    log_path,
                )
                no_progress_count += 1
                if no_progress_count >= MAX_STRUCTURE_REVIEW_NO_PROGRESS:
                    raise RuntimeError(
                        "Agent 2 could not return parseable structure-review JSON after "
                        f"{MAX_STRUCTURE_REVIEW_NO_PROGRESS} attempts. See {log_path}."
                    )
                iteration += 1
                continue
        log_path = write_structure_review_log(input_path, iteration, prompt, response_text, review)
        LOGGER.info(
            "Agent 2 structure review iteration %s satisfied=%s issues=%s log=%s",
            iteration,
            review.get("satisfied"),
            len(review.get("issues", [])),
            log_path,
        )

        desired_cases = review.get("desired_cases")
        before_fingerprint = structure_fingerprint(current_cases)
        if desired_cases:
            current_cases = desired_cases
        elif review.get("operations"):
            current_cases = apply_agent2_structure_operations(
                current_cases,
                review["operations"],
                raw_text,
            )
        elif not review.get("satisfied"):
            LOGGER.warning(
                "Agent 2 was not satisfied but did not provide usable operations."
            )
            no_progress_count += 1
            if no_progress_count >= MAX_STRUCTURE_REVIEW_NO_PROGRESS:
                raise RuntimeError(
                    "Agent 2 repeatedly rejected the structure without usable operations. "
                    f"Latest review log: {log_path}"
                )
            iteration += 1
            continue

        if review.get("satisfied"):
            return current_cases

        after_fingerprint = structure_fingerprint(current_cases)
        if after_fingerprint == before_fingerprint:
            if all_operations_already_satisfied(current_cases, review.get("operations", [])):
                LOGGER.info(
                    "Agent 2 re-requested operations that are already satisfied; treating structure as converged."
                )
                return current_cases
            no_progress_count += 1
            LOGGER.warning(
                "Agent 2 structure operations made no structural change (%s/%s no-progress attempts).",
                no_progress_count,
                MAX_STRUCTURE_REVIEW_NO_PROGRESS,
            )
            if no_progress_count >= MAX_STRUCTURE_REVIEW_NO_PROGRESS:
                raise RuntimeError(
                    "Agent 2 did not approve the structure and operations stopped changing it. "
                    f"Latest review log: {log_path}"
                )
        else:
            no_progress_count = 0
        iteration += 1

    LOGGER.warning(
        "Agent 2 structure review reached manual max iterations (%s); using latest structure.",
        max_iterations,
    )
    return current_cases


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def mistral_chat_json(system_prompt: str, user_message: str, model: str, max_tokens: int = 256) -> Any | None:
    load_dotenv()
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        LOGGER.warning("MISTRAL_API_KEY is not set; falling back to heuristic classification.")
        return None

    api_base = os.environ.get("MISTRAL_API_BASE", DEFAULT_MISTRAL_API_BASE).rstrip("/")
    timeout = float(os.environ.get("MISTRAL_CLASSIFIER_TIMEOUT_SECONDS", "45"))
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": DETERMINISTIC_TEMPERATURE,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    req = request.Request(
        f"{api_base}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        LOGGER.warning("Ministral classifier HTTP %s: %s", exc.code, detail[:500])
        return None
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        LOGGER.warning("Ministral classifier request failed: %s", exc)
        return None

    content = extract_mistral_content(payload)
    parsed = extract_json_fragment(content)
    if parsed is None:
        LOGGER.warning("Ministral classifier returned non-JSON content: %s", content[:500])
    return parsed


class MinistralClassifierAgent:
    """Small Mistral-powered agent for low-reasoning transcript categorization."""

    def __init__(self, model: str = DEFAULT_CLASSIFIER_MODEL) -> None:
        self.model = model
        self.source = f"ministral:{model}"

    def classify_turn(self, question_text: str) -> dict[str, str | bool] | None:
        parsed = mistral_chat_json(
            "You classify interviewer turns for an interview transcript evaluator. Return JSON only.",
            f"""Classify this interviewer turn.

Return exactly:
{{
  "turn_type": "behavioral" | "non_behavioral" | "non_question",
  "is_scorable": true | false,
  "reasoning": "one short sentence"
}}

Definitions:
- behavioral: asks for a specific past example or concrete prior experience.
- non_behavioral: substantive scorable interview question that does not require a specific past example.
- non_question: greeting, logistics, transition, setup, or not enough substance to score.

Interviewer turn:
{question_text}
""",
            self.model,
        )
        if not isinstance(parsed, dict):
            return None
        turn_type = str(parsed.get("turn_type", "")).strip().lower()
        if turn_type not in {"behavioral", "non_behavioral", "non_question"}:
            return None
        return {
            "turn_type": turn_type,
            "is_scorable": bool(parsed.get("is_scorable", turn_type != "non_question")),
            "reasoning": str(parsed.get("reasoning", "Ministral classifier.")),
            "source": self.source,
        }

    def is_follow_up(self, question_text: str, previous_case: dict[str, Any]) -> bool | None:
        parsed = mistral_chat_json(
            "You identify follow-up probes in interview transcripts. Return JSON only.",
            f"""Decide whether the current interviewer turn is a follow-up probe on the immediately previous case.

Return exactly:
{{
  "is_follow_up": true | false,
  "reasoning": "one short sentence"
}}

Previous main question:
{previous_case.get("question", "")}

Previous candidate response:
{previous_case.get("response", "")}

Current interviewer turn:
{question_text}
""",
            self.model,
        )
        if not isinstance(parsed, dict) or "is_follow_up" not in parsed:
            return None
        return bool(parsed.get("is_follow_up"))

    def classify_segment(
        self,
        question_text: str,
        response_text: str,
        last_main_case: dict[str, Any] | None,
        previous_interviewer_turn: str,
        previous_candidate_response: str,
        previous_was_follow_up: bool,
    ) -> str | None:
        parsed = mistral_chat_json(
            "You segment interview transcripts for scoring. Return JSON only.",
            f"""Decide how to segment the current interviewer turn.

Return exactly:
{{
  "decision": "new_case" | "follow_up" | "non_scorable",
  "reasoning": "one short sentence"
}}

Rules:
- new_case: a standalone interview question that should be scored on its own.
- follow_up: a dependent probe that clarifies or deepens the current parent case.
- non_scorable: greeting, logistics, candidate Q&A, interviewer answer, transition, or closing.
- If the previous interviewer turn was a follow-up, another dependent probe should usually attach to the same parent case.

Current parent case question:
{last_main_case.get("question", "") if last_main_case else ""}

Current parent case candidate response:
{last_main_case.get("response", "") if last_main_case else ""}

Previous interviewer turn:
{previous_interviewer_turn}

Previous candidate response:
{previous_candidate_response}

Previous interviewer turn was follow-up:
{previous_was_follow_up}

Current interviewer turn:
{question_text}

Current candidate response:
{response_text}
""",
            self.model,
        )
        if not isinstance(parsed, dict):
            return None
        decision = str(parsed.get("decision", "")).strip().lower()
        if decision not in {SEGMENT_NEW_CASE, SEGMENT_FOLLOW_UP, SEGMENT_NON_SCORABLE}:
            return None
        return decision

    def classify_probe_type(self, question_text: str) -> tuple[str, str] | None:
        parsed = mistral_chat_json(
            "You classify interview follow-up probes. Return JSON only.",
            f"""Classify this follow-up probe.

Return exactly:
{{
  "probe_type": "clarifying" | "deepening",
  "reasoning": "one short sentence"
}}

Definitions:
- clarifying: tries to recover missing facts, specificity, metrics, timeline, role, or context.
- deepening: presses further into tradeoffs, decisions, reflection, conflict, or lessons.

Follow-up question:
{question_text}
""",
            self.model,
        )
        if not isinstance(parsed, dict):
            return None
        probe_type = str(parsed.get("probe_type", "")).strip().lower()
        if probe_type not in {"clarifying", "deepening"}:
            return None
        return probe_type, self.source


def agent1_log_dir_for_input(input_path: Path) -> Path:
    return Path("logs") / "agent1" / input_path.stem


def agent2_log_dir_for_input(input_path: Path) -> Path:
    return Path("logs") / "agent2" / input_path.stem


def agent2_structure_review_dir_for_input(input_path: Path) -> Path:
    return agent2_log_dir_for_input(input_path) / "structure_review"


def entry_timing_log_path_for_input(input_path: Path) -> Path:
    return Path("logs") / "entry_timing" / f"{input_path.stem}_entry_timing.log"


def evaluator_log_path_for_input(input_path: Path) -> Path:
    return agent1_log_dir_for_input(input_path) / f"{input_path.stem}_eval.log"


def result_log_path_for_input(input_path: Path) -> Path:
    return agent1_log_dir_for_input(input_path) / f"{input_path.stem}.log"


def configure_file_logging(log_file: Path) -> Path:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_file,
        filemode="w",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        encoding="utf-8",
        force=True,
    )
    return log_file


def clean_log_files(log_root: Path = Path("logs")) -> int:
    resolved_root = (Path.cwd() / log_root).resolve()
    workspace_root = Path.cwd().resolve()
    if workspace_root not in (resolved_root, *resolved_root.parents):
        raise ValueError(f"Refusing to clean logs outside the workspace: {resolved_root}")
    if not resolved_root.exists():
        return 0
    if not resolved_root.is_dir():
        raise ValueError(f"Log path is not a directory: {resolved_root}")

    removed = 0
    for path in sorted(resolved_root.rglob("*")):
        if path.is_file():
            path.unlink()
            removed += 1
    resolved_root.mkdir(parents=True, exist_ok=True)
    return removed

def strip_fixture_footer(raw_text: str) -> str:
    match = re.search(r"(?ms)^\s*---\s*\n\s*#\s*Expected rubric mapping\b", raw_text)
    if match:
        return raw_text[: match.start()].rstrip()
    return raw_text


# extract turns from raw text
def _extract_turns(raw_text: str) -> list[dict[str, Any]]:
    lines = strip_fixture_footer(raw_text).splitlines()
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

"""
Generate JSON response from Ollama.
@param prompt - The prompt to send to the model.
@param model - The model to use.
@param host - The host to use.
@return The JSON response from the model.
"""
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
    return extract_json_fragment(raw_response)

"""
Heuristic turn classification.
@param question_text - The question text to classify.
@return The classification result.
"""
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

"""
Classify the turn using Ollama.
@param question_text - The question text to classify.
@param ollama_model - The model to use.
@param ollama_host - The host to use.
@return The classification result.
"""
def _classify_turn(
    question_text: str,
    ollama_model: str | None,
    ollama_host: str,
    classifier_agent: MinistralClassifierAgent | None = None,
) -> dict[str, str | bool]:
    if classifier_agent is not None:
        classified = classifier_agent.classify_turn(question_text)
        if classified is not None:
            return classified
        LOGGER.info("Falling back to heuristic turn classification for: %s", question_text[:120])

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

"""
Check if the question is a follow-up.
@param question_text - The question text to check.
@return True if the question is a follow-up, False otherwise.
"""
def _heuristic_is_follow_up(question_text: str) -> bool:
    cleaned = question_text.strip()
    return any(pattern.search(cleaned) for pattern in FOLLOW_UP_PATTERNS)


def normalize_turn_text(text: str) -> str:
    return " ".join(text.strip().split())


def _looks_like_new_main_question(question_text: str) -> bool:
    cleaned = normalize_turn_text(question_text)
    if not cleaned:
        return False
    if any(pattern.search(cleaned) for pattern in BEHAVIORAL_PATTERNS):
        return True
    return any(pattern.search(cleaned) for pattern in MAIN_QUESTION_PATTERNS)


def _looks_like_non_scorable(question_text: str) -> bool:
    cleaned = normalize_turn_text(question_text)
    return any(pattern.search(cleaned) for pattern in NON_SCORABLE_PATTERNS + NON_QUESTION_PATTERNS)


def _starts_candidate_qa(question_text: str) -> bool:
    cleaned = normalize_turn_text(question_text)
    return any(pattern.search(cleaned) for pattern in CANDIDATE_QA_START_PATTERNS)


def _looks_like_dependent_follow_up(question_text: str) -> bool:
    cleaned = normalize_turn_text(question_text)
    return any(pattern.search(cleaned) for pattern in DEPENDENT_FOLLOW_UP_PATTERNS)


def _deterministic_segment_decision(
    question_text: str,
    last_main_case: dict[str, Any] | None,
) -> str | None:
    if _starts_candidate_qa(question_text) or _looks_like_non_scorable(question_text):
        return SEGMENT_NON_SCORABLE
    if _looks_like_new_main_question(question_text):
        return SEGMENT_NEW_CASE
    if last_main_case is not None and _looks_like_dependent_follow_up(question_text):
        return SEGMENT_FOLLOW_UP
    return None


def _model_segment_decision(
    question_text: str,
    response_text: str,
    last_main_case: dict[str, Any] | None,
    previous_interviewer_turn: str,
    previous_candidate_response: str,
    previous_was_follow_up: bool,
    classifier_agent: MinistralClassifierAgent | None,
) -> str | None:
    if classifier_agent is None:
        return None
    decision = classifier_agent.classify_segment(
        question_text,
        response_text,
        last_main_case,
        previous_interviewer_turn,
        previous_candidate_response,
        previous_was_follow_up,
    )
    if decision == SEGMENT_FOLLOW_UP and last_main_case is None:
        return SEGMENT_NEW_CASE
    return decision

"""
Check if the question is a follow-up question.
@param question_text - The question text to check.
@param previous_case - The previous case.
@param ollama_model - The model to use.
@param ollama_host - The host to use.
@return True if the question is a follow-up question, False otherwise.
"""
def _is_follow_up_question(
    question_text: str,
    previous_case: dict[str, Any] | None,
    ollama_model: str | None,
    ollama_host: str,
    classifier_agent: MinistralClassifierAgent | None = None,
) -> bool:
    if previous_case is None:
        return False
    if _looks_like_new_main_question(question_text):
        return False
    if _heuristic_is_follow_up(question_text):
        return True
    if classifier_agent is not None:
        classified = classifier_agent.is_follow_up(question_text, previous_case)
        if classified is not None:
            return classified
        LOGGER.info("Falling back to heuristic follow-up detection for: %s", question_text[:120])
    if not ollama_model:
        return False

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
        return False
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
    classifier_agent: MinistralClassifierAgent | None = None,
) -> tuple[str, str]:
    if classifier_agent is not None:
        classified = classifier_agent.classify_probe_type(question_text)
        if classified is not None:
            return classified
        LOGGER.info("Falling back to heuristic probe classification for: %s", question_text[:120])

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
    classifier_provider: str = DEFAULT_CLASSIFIER_PROVIDER,
    classifier_model: str = DEFAULT_CLASSIFIER_MODEL,
) -> list[dict[str, Any]]:
    turns = _extract_turns(raw_text)
    cases: list[dict[str, Any]] = []
    case_id = 1
    i = 0
    last_main_case: dict[str, Any] | None = None
    previous_interviewer_turn = ""
    previous_candidate_response = ""
    previous_was_follow_up = False
    candidate_qa_mode = False
    provider = classifier_provider.strip().lower()
    classifier_agent = (
        MinistralClassifierAgent(classifier_model)
        if provider in {"mistral", "ministral"}
        else None
    )

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

        if candidate_qa_mode:
            previous_interviewer_turn = question
            previous_candidate_response = response
            previous_was_follow_up = False
            i += 2 if consumed_candidate else 1
            continue

        deterministic_decision = _deterministic_segment_decision(question, last_main_case)
        if _starts_candidate_qa(question):
            candidate_qa_mode = True

        decision = deterministic_decision
        if decision is None:
            decision = _model_segment_decision(
                question,
                response,
                last_main_case,
                previous_interviewer_turn,
                previous_candidate_response,
                previous_was_follow_up,
                classifier_agent,
            )
        if decision is None:
            decision = SEGMENT_NEW_CASE

        if decision == SEGMENT_NON_SCORABLE:
            previous_interviewer_turn = question
            previous_candidate_response = response
            previous_was_follow_up = False
            i += 2 if consumed_candidate else 1
            continue

        if decision == SEGMENT_FOLLOW_UP and last_main_case is not None:
            probe_type, probe_source = _classify_probe_type(
                question, ollama_model, ollama_host, classifier_agent
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
            previous_interviewer_turn = question
            previous_candidate_response = response
            previous_was_follow_up = True
        else:
            turn_info = _classify_turn(question, ollama_model, ollama_host, classifier_agent)
            if not bool(turn_info["is_scorable"]):
                previous_interviewer_turn = question
                previous_candidate_response = response
                previous_was_follow_up = False
                i += 2 if consumed_candidate else 1
                continue

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
            last_main_case = case_entry
            case_id += 1
            previous_interviewer_turn = question
            previous_candidate_response = response
            previous_was_follow_up = False

        i += 2 if consumed_candidate else 1

    return cases


def get_input_path(input_arg: str | None) -> Path:
    if input_arg:
        return resolve_input_path(input_arg)

    while True:
        prompted_path = input("Enter the TXT file to convert: ").strip().strip('"')
        if prompted_path:
            return resolve_input_path(prompted_path)
        print("Please enter a file path.")


def resolve_input_path(input_value: str) -> Path:
    input_path = Path(input_value)
    if input_path.exists() or input_path.parent != Path("."):
        return input_path

    input_data_path = Path("input data") / input_path
    if input_data_path.exists():
        return input_data_path

    return input_path


def get_batch_size(batch_size_arg: int | None) -> int:
    if batch_size_arg is not None:
        if 1 <= batch_size_arg <= 7:
            return batch_size_arg
        raise ValueError("Batch size must be between 1 and 7.")

    while True:
        prompted_size = input("Enter batch size (1-7): ").strip()
        try:
            batch_size = int(prompted_size)
        except ValueError:
            print("Please enter a whole number from 1 to 7.")
            continue

        if 1 <= batch_size <= 7:
            return batch_size
        print("Please enter a batch size from 1 to 7.")


def log_parsed_cases(cases: list[dict[str, Any]]) -> None:
    LOGGER.info("Detected %s evaluator cases", len(cases))
    for case in cases:
        pair_started_at = local_time_mark()
        question = str(case.get("question", ""))
        response = str(case.get("response", ""))
        pair_finished_at = local_time_mark()
        LOGGER.info(
            "Question/answer pair %s: started_at=%s finished_at=%s "
            "question_chars=%s answer_chars=%s follow_ups=%s",
            case.get("id"),
            pair_started_at,
            pair_finished_at,
            len(question),
            len(response),
            len(case.get("follow_ups", []) or []),
        )


def run_evaluator_html(
    json_path: Path,
    batch_size: int,
    evaluator_html_path: str = "src/frontend/evaluator.html",
    eval_log_file: Path | None = None,
    result_log_file: Path | None = None,
) -> str:
    evaluator_html = Path(evaluator_html_path)
    if not evaluator_html.exists():
        raise FileNotFoundError(f"Missing evaluator HTML file: {evaluator_html}")

    server_port = start_http_server_if_needed(EVALUATOR_PORT)
    query_input = json_path_for_browser(json_path)
    query_args = {
        "v": EVALUATOR_ASSET_VERSION,
        "input": query_input,
        "batch_size": batch_size,
    }
    if eval_log_file is not None:
        query_args["log_file"] = log_path_for_browser(eval_log_file)
    if result_log_file is not None:
        query_args["result_log_file"] = log_path_for_browser(result_log_file)
    query = urlencode(query_args)
    evaluator_url = f"http://localhost:{server_port}/{evaluator_html.as_posix()}?{query}"

    LOGGER.info("Opening evaluator HTML: %s", evaluator_url)
    webbrowser.open(evaluator_url)
    return evaluator_url


def json_path_for_browser(json_path: Path) -> str:
    try:
        return json_path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        LOGGER.warning(
            "Output JSON is outside the project folder and may not be loadable: %s",
            json_path,
        )
        return json_path.as_posix()


def log_path_for_browser(log_file: Path) -> str:
    try:
        return log_file.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        LOGGER.warning(
            "Log file is outside the project folder and may not be writable from evaluator: %s",
            log_file,
        )
        return log_file.as_posix()


def pipeline_server_is_available(port: int) -> bool:
    try:
        with request.urlopen(f"http://127.0.0.1:{port}/pipeline-log/health", timeout=1) as resp:
            return resp.status == HTTPStatus.NO_CONTENT
    except (error.URLError, TimeoutError):
        return False


def port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def find_pipeline_server_port(preferred_port: int) -> int:
    for offset in range(20):
        candidate = preferred_port + offset
        if pipeline_server_is_available(candidate):
            LOGGER.info("Reusing existing pipeline server on port %s", candidate)
            return candidate
        if not port_is_open(candidate):
            return candidate
    raise RuntimeError("Could not find an available local server port.")


def start_http_server_if_needed(port: int) -> int:
    server_port = find_pipeline_server_port(port)
    if pipeline_server_is_available(server_port):
        return server_port

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    subprocess.Popen(
        [sys.executable, "-m", "src.agent1.txt_to_json", "--serve-internal", str(server_port)],
        cwd=Path.cwd(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    time.sleep(1)
    if not pipeline_server_is_available(server_port):
        raise RuntimeError(f"Pipeline server did not start on port {server_port}.")
    LOGGER.info("Started pipeline server on port %s", server_port)
    return server_port


def extract_mistral_content(payload: dict[str, Any]) -> str:
    message = payload.get("choices", [{}])[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                chunks.append(item["text"])
            elif isinstance(item, str):
                chunks.append(item)
        return "\n".join(chunks)
    return ""


def call_mistral_evaluator(system_prompt: str, user_message: str, model: str | None = None) -> dict[str, Any]:
    load_dotenv()
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is not set in .env or the environment.")

    selected_model = model or os.environ.get("MISTRAL_EVALUATOR_MODEL", DEFAULT_MISTRAL_MODEL)
    api_base = os.environ.get("MISTRAL_API_BASE", DEFAULT_MISTRAL_API_BASE).rstrip("/")
    timeout = float(os.environ.get("MISTRAL_EVALUATOR_TIMEOUT_SECONDS", "180"))
    body = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": DETERMINISTIC_TEMPERATURE,
        "response_format": {"type": "json_object"},
    }
    req = request.Request(
        f"{api_base}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            response_payload = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Mistral API HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Mistral API request failed: {exc}") from exc

    content = extract_mistral_content(response_payload)
    if not content:
        raise RuntimeError("Empty response from Mistral API.")
    return {
        "model": selected_model,
        "content": content,
        "raw": response_payload,
    }


class PipelineHTTPRequestHandler(SimpleHTTPRequestHandler):
    server_version = "TranscriptEvaluatorPipeline/1.0"

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        LOGGER.info("server %s - %s", self.address_string(), format % args)

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/agent2-ws":
            self.handle_agent2_websocket()
            return
        if self.path == "/pipeline-log/health":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path == "/agent2/handoff":
            port = int(getattr(self.server, "server_port", EVALUATOR_PORT))
            AGENT2_BRIDGE.handle_handoff(self, port)
            return
        if self.path == "/mistral/evaluate":
            self.handle_mistral_evaluate()
            return
        if self.path == "/interview-db/agent1-result":
            self.handle_agent1_result()
            return
        if self.path != "/pipeline-log":
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(body)
            log_file = resolve_pipeline_log_path(str(payload.get("log_file", "")))
            text = str(payload.get("text", ""))
            write_mode = str(payload.get("write_mode", "a")).strip().lower()
            if write_mode not in {"a", "w"}:
                raise ValueError("write_mode must be 'a' or 'w'")
            if write_mode != "w" and not text:
                raise ValueError("missing text")
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open(write_mode, encoding="utf-8", newline="") as f:
                f.write(text)
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
        except Exception as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def handle_agent2_websocket(self) -> None:
        AGENT2_BRIDGE.handle_websocket(self)

    def handle_mistral_evaluate(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(body)
            system_prompt = str(payload.get("system_prompt", ""))
            user_message = str(payload.get("user_message", ""))
            model = str(payload.get("model", "")).strip() or None
            if not system_prompt or not user_message:
                raise ValueError("missing system_prompt or user_message")
            result = call_mistral_evaluator(system_prompt, user_message, model)
            write_json_response(self, HTTPStatus.OK, result)
        except Exception as exc:
            write_json_response(self, HTTPStatus.BAD_REQUEST, {"status": "error", "message": str(exc)})

    def handle_agent1_result(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(body)
            saved = save_agent1_result(payload, Path(os.environ.get("INTERVIEW_SQLITE_DB", str(DEFAULT_DB_PATH))))
            write_json_response(self, HTTPStatus.OK, {"status": "saved" if saved else "skipped"})
        except Exception as exc:
            write_json_response(self, HTTPStatus.BAD_REQUEST, {"status": "error", "message": str(exc)})


def run_pipeline_server(port: int) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        encoding="utf-8",
    )
    server = ThreadingHTTPServer(("127.0.0.1", port), PipelineHTTPRequestHandler)
    LOGGER.info("Serving transcript evaluator pipeline on http://127.0.0.1:%s", port)
    server.serve_forever()


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Convert transcript text into evaluator-ready JSON and run evaluation."
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Path to transcript text file, or 'clean' to erase all files under logs/.",
    )
    parser.add_argument(
        "--clean-logs",
        action="store_true",
        help="Erase all files under logs/ and exit.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation (default: 2)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        help="Evaluator batch size from 1 to 7. If omitted, you will be prompted.",
    )
    parser.add_argument(
        "--evaluator-html",
        default="src/frontend/evaluator.html",
        help="Path to evaluator.html. Defaults to src/frontend/evaluator.html.",
    )
    parser.add_argument(
        "--sqlite-db",
        default=os.environ.get("INTERVIEW_SQLITE_DB", str(DEFAULT_DB_PATH)),
        help="SQLite database path for approved interview structure.",
    )
    parser.add_argument(
        "--structure-review-iterations",
        type=int,
        default=int(os.environ.get("AGENT2_STRUCTURE_REVIEW_ITERATIONS", DEFAULT_STRUCTURE_REVIEW_ITERATIONS)),
        help=(
            "Agent 2 structure-review loop count. Defaults to -1, which means keep looping "
            "until Agent 2 is satisfied. Use 0 to skip, or a positive number to set a manual cap."
        ),
    )
    parser.add_argument(
        "--classifier-provider",
        choices=["ministral", "mistral", "heuristic", "ollama"],
        default=os.environ.get("CLASSIFIER_PROVIDER", DEFAULT_CLASSIFIER_PROVIDER),
        help=(
            "Classifier for transcript categorization. Defaults to ministral. "
            "Use heuristic for no AI classifier, or ollama for the legacy local path."
        ),
    )
    parser.add_argument(
        "--classifier-model",
        default=os.environ.get("MISTRAL_CLASSIFIER_MODEL", DEFAULT_CLASSIFIER_MODEL),
        help="Mistral/Ministral model for transcript categorization.",
    )
    parser.add_argument(
        "--ollama-model",
        default=os.environ.get("OLLAMA_MODEL"),
        help="Optional legacy Ollama model name when --classifier-provider ollama is used.",
    )
    parser.add_argument(
        "--ollama-host",
        default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        help="Ollama host URL (default: http://127.0.0.1:11434).",
    )
    parser.add_argument(
        "--serve-internal",
        type=int,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    os.environ["INTERVIEW_SQLITE_DB"] = str(args.sqlite_db) if hasattr(args, "sqlite_db") else str(DEFAULT_DB_PATH)

    if args.serve_internal:
        run_pipeline_server(args.serve_internal)
        return

    if args.clean_logs or str(args.input or "").strip().lower() == "clean":
        removed = clean_log_files()
        print(f"Removed {removed} log file(s) from logs/.")
        return

    input_path = get_input_path(args.input)
    batch_size = get_batch_size(args.batch_size)
    entry_timing_log = configure_file_logging(entry_timing_log_path_for_input(input_path))
    eval_log_file = evaluator_log_path_for_input(input_path)
    result_log_file = result_log_path_for_input(input_path)
    eval_log_file.parent.mkdir(parents=True, exist_ok=True)
    result_log_file.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.info("Starting convert and evaluate task; logging to %s", entry_timing_log)
    LOGGER.info("input=%s batch_size=%s", input_path, batch_size)

    if not input_path.exists():
        LOGGER.error("Input file not found: %s", input_path)
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if input_path.suffix.lower() != ".txt":
        LOGGER.error("Input must be a .txt file. Got: %s", input_path.name)
        raise ValueError(f"Input must be a .txt file. Got: {input_path.name}")

    classifier_provider = args.classifier_provider.strip().lower()
    active_ollama_model = args.ollama_model if classifier_provider == "ollama" else None
    classifier_mode = (
        f"ministral:{args.classifier_model}"
        if classifier_provider in {"mistral", "ministral"}
        else f"ollama:{active_ollama_model or 'heuristic-fallback'}"
        if classifier_provider == "ollama"
        else "heuristic-only"
    )

    conversion_started_at = local_time_mark()
    output_path = input_path.with_suffix(".json")
    raw_text = input_path.read_text(encoding="utf-8")
    LOGGER.info(
        "Parsing transcript: input=%s chars=%s classifier=%s",
        input_path,
        len(raw_text),
        classifier_mode,
    )
    parsed_cases = parse_transcript_to_test_cases(
        raw_text,
        ollama_model=active_ollama_model,
        ollama_host=args.ollama_host,
        classifier_provider=classifier_provider,
        classifier_model=args.classifier_model,
    )
    parsed_cases = run_agent2_structure_review_loop(
        raw_text,
        parsed_cases,
        input_path,
        max_iterations=args.structure_review_iterations,
    )
    LOGGER.info("Parsed transcript into %s cases", len(parsed_cases))
    log_parsed_cases(parsed_cases)
    output_path.write_text(
        json.dumps(parsed_cases, indent=args.indent), encoding="utf-8"
    )
    interview_id = save_interview_cases(
        parsed_cases,
        input_path.stem,
        input_path,
        output_path,
        Path(args.sqlite_db),
    )
    conversion_finished_at = local_time_mark()
    LOGGER.info(
        "Finished conversion: input=%s output=%s started_at=%s finished_at=%s "
        "input_chars=%s cases=%s batch_size=%s",
        input_path,
        output_path,
        conversion_started_at,
        conversion_finished_at,
        len(raw_text),
        len(parsed_cases),
        batch_size,
    )
    LOGGER.info("Stored approved interview structure in SQLite: db=%s interview_id=%s", args.sqlite_db, interview_id)

    print(f"Wrote JSON to: {output_path}")
    print(f"Stored SQLite interview id: {interview_id} ({args.sqlite_db})")
    print(f"Cases: {len(parsed_cases)}")
    print(f"Classifier: {classifier_mode}")
    evaluator_url = run_evaluator_html(
        output_path,
        batch_size,
        args.evaluator_html,
        eval_log_file,
        result_log_file,
    )
    print(f"Opened evaluator: {evaluator_url}")


if __name__ == "__main__":
    main()
