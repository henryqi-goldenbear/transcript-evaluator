"""Generate synthetic interview transcripts via Mistral for testing.

Writes 30 interviews into ``input data/test/`` with varying quality levels
and varying roles. Uses temperature 0.7 so outputs differ across runs.

Usage:
    python scripts/generate_test_interviews.py
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path
from urllib import error, request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = PROJECT_ROOT / "input data" / "test"
ENV_PATH = PROJECT_ROOT / ".env"

MISTRAL_API_BASE = "https://api.mistral.ai/v1"
MODEL = os.environ.get("MISTRAL_GENERATOR_MODEL", "mistral-large-latest")
TEMPERATURE = 0.7
MAX_TOKENS = 4000
TIMEOUT_SECONDS = 180
NUM_INTERVIEWS = 30

QUALITY_LEVELS = [
    (
        "very_poor",
        "Candidate performs very poorly. Vague, evasive, lacks concrete examples, "
        "shows little ownership, gives one-line answers, contradicts themselves, "
        "and asks no thoughtful questions.",
    ),
    (
        "poor",
        "Candidate performs poorly. Mostly generic answers, weak examples, "
        "limited self-awareness, shallow technical depth, and few specifics or metrics.",
    ),
    (
        "mediocre",
        "Candidate performs at a mediocre level. Some real examples but lacking depth, "
        "occasional metrics, mixed self-awareness, and inconsistent ownership.",
    ),
    (
        "good",
        "Candidate performs well. Concrete situations, decent metrics, clear ownership, "
        "reasonable trade-off discussion, and a few thoughtful questions at the end.",
    ),
    (
        "excellent",
        "Candidate performs excellently. Crisp STAR-format answers with quantified impact, "
        "honest reflection on tradeoffs and failures, strong ownership, deep technical "
        "specifics, and incisive questions for the interviewer.",
    ),
]

ROLES = [
    ("Backend Software Engineer", "Platform team @ Northline Financial",
     "Go, Postgres, distributed systems, payments/ledger consistency"),
    ("Frontend Engineer", "Growth team @ Brightlane",
     "React, TypeScript, performance optimization, A/B testing infrastructure"),
    ("Data Engineer", "Analytics Platform @ Quanta Logistics",
     "Spark, Airflow, dbt, warehouse modeling, batch + streaming pipelines"),
    ("Site Reliability Engineer", "Core Infrastructure @ Mesa Cloud",
     "Kubernetes, observability, incident response, capacity planning, SLOs"),
    ("Senior Product Manager", "Marketplace team @ Hearthside",
     "experimentation, roadmap tradeoffs, two-sided marketplace dynamics"),
    ("Machine Learning Engineer", "Recommendations team @ TideStream",
     "feature stores, offline/online evaluation, model serving, A/B testing"),
]


def load_dotenv() -> None:
    if not ENV_PATH.exists():
        return
    for raw_line in ENV_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def mistral_chat(system_prompt: str, user_message: str) -> str | None:
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        print("ERROR: MISTRAL_API_KEY is not set in environment or .env.", file=sys.stderr)
        return None

    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }
    req = request.Request(
        f"{MISTRAL_API_BASE}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            with request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            choices = payload.get("choices") or []
            if not choices:
                return None
            return choices[0].get("message", {}).get("content")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            last_err = RuntimeError(f"HTTP {exc.code}: {detail}")
            if exc.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt * 2)
                continue
            break
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_err = exc
            time.sleep(2 ** attempt * 2)
    print(f"  request failed after retries: {last_err}", file=sys.stderr)
    return None


SYSTEM_PROMPT = (
    "You generate realistic interview transcripts for evaluating candidate "
    "performance against a behavioral + technical rubric. You write only the "
    "transcript itself. Use exactly this format, alternating turns:\n\n"
    "INTERVIEWER:\n<text>\n\nCANDIDATE:\n<text>\n\n"
    "Do not add narration, scoring, headings other than the optional file header, "
    "or commentary outside of the speaker turns. Keep wording natural and "
    "conversational. The interviewer should mostly ask behavioral questions "
    "(STAR-style), with a few resume / role-fit / technical depth questions mixed "
    "in. End with the candidate asking (or failing to ask) questions for the "
    "interviewer."
)


def build_user_prompt(role: tuple[str, str, str], quality_label: str, quality_desc: str, idx: int) -> str:
    role_title, role_team, role_focus = role
    interviewer = random.choice(["Priya", "Marcus", "Dana", "Hassan", "Lin", "Renee", "Theo", "Kira"])
    candidate = random.choice(["Alex", "Jordan", "Sam", "Riley", "Morgan", "Quinn", "Devon", "Casey", "Avery", "Sasha"])

    return (
        f"Generate one full interview transcript (target length: 18 to 28 question/"
        f"answer turn pairs).\n\n"
        f"Role: {role_title}, {role_team}\n"
        f"Technical focus: {role_focus}\n"
        f"Interviewer name: {interviewer}\n"
        f"Candidate name: {candidate}\n"
        f"Quality target: {quality_label} candidate performance\n"
        f"Quality description: {quality_desc}\n\n"
        "Begin the file with these comment lines (verbatim, no extra header):\n"
        "# Interview transcript fixture\n"
        f"# Role: {role_title}, {role_team}\n"
        f"# Quality target: {quality_label} candidate performance\n"
        "# Format: INTERVIEWER / CANDIDATE turns\n\n"
        "---\n\n"
        "Then alternate INTERVIEWER and CANDIDATE turns as described in the system "
        "prompt. Cover: warm-up, resume walk, role motivation, 1-2 technical depth "
        "questions appropriate to the role, several behavioral prompts (leadership, "
        "conflict, failure, mentoring, prioritization, persuasion, process "
        "improvement, weakness), and end with the candidate's questions and a quick "
        "closing exchange. Stay in-character at the requested quality level "
        "throughout; do not break style mid-interview.\n"
        f"\n(Variation seed: interview #{idx:02d})"
    )


def quality_distribution(n: int) -> list[tuple[str, str]]:
    base, remainder = divmod(n, len(QUALITY_LEVELS))
    counts = [base] * len(QUALITY_LEVELS)
    for i in range(remainder):
        counts[i] += 1
    out: list[tuple[str, str]] = []
    for (label, desc), count in zip(QUALITY_LEVELS, counts):
        out.extend([(label, desc)] * count)
    random.shuffle(out)
    return out


def main() -> int:
    load_dotenv()
    if not os.environ.get("MISTRAL_API_KEY"):
        print("MISTRAL_API_KEY missing; aborting.", file=sys.stderr)
        return 1

    TEST_DIR.mkdir(parents=True, exist_ok=True)
    random.seed()

    quality_plan = quality_distribution(NUM_INTERVIEWS)
    print(f"Generating {NUM_INTERVIEWS} interviews into {TEST_DIR} using {MODEL} "
          f"(temperature={TEMPERATURE}).")

    for idx in range(1, NUM_INTERVIEWS + 1):
        quality_label, quality_desc = quality_plan[idx - 1]
        role = random.choice(ROLES)
        out_path = TEST_DIR / f"interview_{idx:02d}_{quality_label}.txt"
        if out_path.exists():
            print(f"[{idx:02d}/{NUM_INTERVIEWS}] {out_path.name} exists; skipping.")
            continue

        print(f"[{idx:02d}/{NUM_INTERVIEWS}] {quality_label:<10} | {role[0]}")
        user_prompt = build_user_prompt(role, quality_label, quality_desc, idx)
        text = mistral_chat(SYSTEM_PROMPT, user_prompt)
        if not text:
            print(f"  failed to generate interview {idx:02d}; continuing.")
            continue
        out_path.write_text(text.strip() + "\n", encoding="utf-8")
        print(f"  wrote {out_path.relative_to(PROJECT_ROOT)} ({len(text)} chars)")
        time.sleep(0.5)

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
