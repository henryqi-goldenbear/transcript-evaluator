"""Playground-style runner for the configured Mistral Agent 2.

By default this talks directly to the Mistral Agent from the console URL:
https://console.mistral.ai/build/playground?agentId=ag_019e9f09fadc72f7b26c3a4eace4fcd1&from=agents

When launched by src/bridge/agent2_connection.py with a websocket URL, it still accepts
the evaluator handoff payload and sends that to the same agent.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import ssl
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import urlparse
from src.shared.interview_db import DEFAULT_DB_PATH, save_agent2_report_note


DEFAULT_AGENT_ID = "ag_019e9f09fadc72f7b26c3a4eace4fcd1"
DEFAULT_AGENT_VERSION = "1"
DEFAULT_API_BASE = "https://api.mistral.ai/v1"
DEFAULT_PLAYGROUND_PROMPT = "Hello! Reply with one short sentence confirming Agent 2 is connected."
MAX_TEXT_CHARS = 20_000
DEFAULT_LOG_CHARS = 12_000
DEFAULT_JSON_CHARS = 12_000
DEFAULT_TRANSCRIPT_CHARS = 10_000


def local_file_stamp(include_date: bool = True) -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S" if include_date else "%H%M%S")


def local_report_date_label() -> str:
    return datetime.now().strftime("%m/%d/%y")


def local_timestamp_label() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def local_report_date_filename() -> str:
    return datetime.now().strftime("%m-%d-%y")


def local_time_mark() -> str:
    return datetime.now().strftime("%H:%M:%S")


def safe_filename_part(value: str, fallback: str = "handoff") -> str:
    clean = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())
    clean = "_".join(part for part in clean.split("_") if part)
    return clean or fallback


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not find an available report filename for {path}")


def load_dotenv(path: Path) -> None:
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


def logs_dir() -> Path:
    path = Path.cwd() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def agent2_logs_dir() -> Path:
    path = logs_dir() / "agent2"
    path.mkdir(parents=True, exist_ok=True)
    return path


def agent2_named_logs_dir(file_stem: str) -> Path:
    path = agent2_logs_dir() / safe_filename_part(file_stem)
    path.mkdir(parents=True, exist_ok=True)
    return path


def agent2_system_logs_dir() -> Path:
    path = agent2_logs_dir() / "system"
    path.mkdir(parents=True, exist_ok=True)
    return path


def append_agent_log(message: str) -> None:
    line = f"{local_time_mark()} {message}\n"
    (agent2_system_logs_dir() / "agent2.log").open("a", encoding="utf-8").write(line)


def redact(value: str | None) -> str:
    if not value:
        return "<missing>"
    return "<set>"


def websocket_receive_text(ws_url: str, timeout: float = 15.0) -> str:
    parsed = urlparse(ws_url)
    if parsed.scheme not in {"ws", "wss"}:
        raise ValueError(f"Unsupported websocket scheme: {parsed.scheme}")
    if not parsed.hostname:
        raise ValueError("Websocket URL must include a hostname")

    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    sock = socket.create_connection((parsed.hostname, port), timeout=timeout)
    try:
        if parsed.scheme == "wss":
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=parsed.hostname)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        sock.sendall(handshake.encode("ascii"))
        response_bytes = b""
        while b"\r\n\r\n" not in response_bytes:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("Websocket handshake closed early")
            response_bytes += chunk
        header_bytes, remainder = response_bytes.split(b"\r\n\r\n", 1)
        header_text = header_bytes.decode("iso-8859-1")
        if " 101 " not in header_text.splitlines()[0]:
            raise ConnectionError(f"Websocket handshake failed: {header_text.splitlines()[0]}")

        expected_accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        if expected_accept.lower() not in header_text.lower():
            raise ConnectionError("Websocket handshake returned an unexpected accept key")

        data = bytearray(remainder)
        while len(data) < 2:
            data.extend(sock.recv(4096))
        first, second = data[0], data[1]
        opcode = first & 0x0F
        if opcode == 0x8:
            raise ConnectionError("Websocket closed before sending a payload")
        if opcode != 0x1:
            raise ConnectionError(f"Expected text websocket frame, got opcode {opcode}")

        masked = bool(second & 0x80)
        length = second & 0x7F
        offset = 2
        if length == 126:
            while len(data) < offset + 2:
                data.extend(sock.recv(4096))
            length = int.from_bytes(data[offset : offset + 2], "big")
            offset += 2
        elif length == 127:
            while len(data) < offset + 8:
                data.extend(sock.recv(4096))
            length = int.from_bytes(data[offset : offset + 8], "big")
            offset += 8

        mask = b""
        if masked:
            while len(data) < offset + 4:
                data.extend(sock.recv(4096))
            mask = bytes(data[offset : offset + 4])
            offset += 4

        while len(data) < offset + length:
            data.extend(sock.recv(4096))
        payload = bytes(data[offset : offset + length])
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return payload.decode("utf-8")
    finally:
        sock.close()


def shorten(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    if len(text) <= limit:
        return text
    keep = limit // 2
    omitted = len(text) - (keep * 2)
    return f"{text[:keep]}\n\n[...omitted {omitted} characters...]\n\n{text[-keep:]}"


def env_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default
    try:
        return max(500, int(raw_value))
    except ValueError:
        return default


def build_prompt(payload: dict[str, Any]) -> str:
    if payload.get("error"):
        raise ValueError(str(payload["error"]))
    log_file = payload.get("log_file", "unknown log")
    input_file = payload.get("input_file", "unknown input")
    input_json_file = payload.get("input_json_file", "not provided")
    return f"""You are Agent 2 for the transcript evaluator.

Review the evaluation run below. Agent 1 is the evaluator that produced the ratings in the
evaluation log. Use the evaluator JSON and original transcript as the source of truth.

Your job is both QA reviewer and Agent 1 auditor:
1. Verdict: pass, needs review, or fail.
2. Agent 1 bias audit: say whether Agent 1 appears fair, too favorable/lenient, too harsh,
   or inconsistent. Favorable bias means Agent 1 gives high ratings without enough explicit
   evidence, ignores missing specifics, treats vague or hypothetical answers as strong,
   over-rewards follow-up recovery, or fails to penalize contradictions/deflection.
3. Structure audit: compare the original transcript against the evaluator JSON and say whether
   Agent 1 structured the interview correctly. Check:
   - missed main questions that should have become cases
   - non-scorable greetings, logistics, interviewer explanations, or candidate questions that were
     incorrectly turned into cases
   - separate main questions that were incorrectly merged
   - dependent follow-ups that were incorrectly split into new cases
   - independent questions that were incorrectly attached as follow-ups
   - follow-up probe type mistakes: clarifying vs deepening
   - follow-up response placement mistakes, especially when a candidate answer belongs to the
     previous follow-up or the next main question
4. Follow-up audit: for every follow-up in the evaluator JSON, decide whether it is attached to
   the correct parent case. If it is wrong, pinpoint:
   - parent case id/label if available
   - the follow-up question text
   - the transcript location or nearby preceding/following question
   - the correct action: keep as follow-up, move to another parent, split into a new case,
     mark non-scorable, or change probe_type
   If no follow-up issues exist, say that clearly.
5. Corrected ratings: for every suspicious case, list the Agent 1 overall rating, your
   corrected overall rating, the reason for the correction, and the evidence from the
   transcript/log. If Agent 1 is materially biased, include a corrected average or summary
   direction (for example: "average likely drops from 4.7 to about 3.8").
6. Agent 1 structuring guidance: write concrete changes for the structuring agent in
   txt_to_json.py. Include rules or prompt changes that would prevent the observed segmentation
   or follow-up errors next time.
7. Agent 1 rating correction guidance: write concrete prompt/rubric changes that would make
   Agent 1 rate less favorably next time. Include any caps or downgrade rules that should be added.
8. Top issues, grouped by severity, including malformed output, missing evidence, suspicious
   ratings, segmentation issues, or rate-limit/API failures.
9. Concrete next steps.

Be strict but fair. Do not simply rubber-stamp Agent 1. Do not change ratings just to be
different; only correct when the transcript evidence does not support Agent 1's rating.
Prefer explicit evidence over vibes. Quote short snippets only when necessary.
When you flag a structure problem, be precise enough that a developer can locate the bug in
txt_to_json.py without rereading the whole transcript.

Suggested report format:
- Verdict
- Agent 1 Bias Audit
- Structure Audit
- Follow-Up Audit
- Corrected Ratings
- Agent 1 Structuring Corrections
- Agent 1 Rating Corrections
- Other QA Issues
- Next Steps

Evaluation log file: {log_file}
Evaluator JSON file: {input_json_file}
Input transcript file: {input_file}

--- Evaluation log ---
{shorten(str(payload.get("log_text", "")), env_int("MISTRAL_AGENT2_LOG_CHARS", DEFAULT_LOG_CHARS))}

--- Evaluator JSON ---
{shorten(str(payload.get("input_json_text", "")), env_int("MISTRAL_AGENT2_JSON_CHARS", DEFAULT_JSON_CHARS))}

--- Original transcript ---
{shorten(str(payload.get("input_text", "")), env_int("MISTRAL_AGENT2_TRANSCRIPT_CHARS", DEFAULT_TRANSCRIPT_CHARS))}
"""


def build_structure_review_prompt(
    compact_context: dict[str, Any],
    evaluator_json: list[dict[str, Any]],
    iteration: int,
    source_name: str,
) -> str:
    return f"""You are Agent 2 acting as the structure reviewer for Agent 0.

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
- Before returning operations, re-inspect current_cases. Do not propose an operation if the
  structure already matches that operation, such as a follow-up already attached to the requested
  parent or the question already promoted to a standalone case.
- If a question should become its own case, use split_follow_up_to_case or add_missing_case, not
  move_follow_up.
- If you cannot express the needed change with the provided operations schema, set
  "satisfied": true, leave operations empty, and describe the limitation in summary instead of
  looping forever.

Return valid JSON only. No markdown, no prose outside JSON.
Your first character must be "{{" and your last character must be "}}".

Use exactly this schema:
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
    {{
      "op": "split_follow_up_to_case" | "add_missing_case" | "remove_case" | "move_follow_up" | "change_probe_type",
      "reason": "why this operation is needed",
      "source_case_id": <number or null>,
      "target_case_id": <number or null>,
      "follow_up_question": "follow-up question text or empty string",
      "question": "main question text or empty string",
      "response": "candidate response text or empty string",
      "turn_type": "behavioral" | "non_behavioral" | "",
      "probe_type": "clarifying" | "deepening" | ""
    }}
  ]
}}

If satisfied is true, operations must be [].
If satisfied is false, operations must contain compact edits only. Do not return the full corrected JSON.
Prefer split_follow_up_to_case when Agent 0 attached an independent question as a follow-up.
Prefer add_missing_case when a transcript question is absent from the evaluator JSON.

Source: {source_name}
Review iteration: {iteration}

--- Compact transcript and current structure ---
{json.dumps(compact_context, indent=2)}
"""


def call_mistral_agent(prompt: str) -> dict[str, Any]:
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is not set. Add it to .env or your environment.")

    agent_id = os.environ.get("MISTRAL_AGENT2_ID", DEFAULT_AGENT_ID)
    agent_version = os.environ.get("MISTRAL_AGENT2_VERSION", DEFAULT_AGENT_VERSION)
    api_base = os.environ.get("MISTRAL_API_BASE", DEFAULT_API_BASE).rstrip("/")
    timeout = float(os.environ.get("MISTRAL_AGENT2_TIMEOUT_SECONDS", "120"))
    store = os.environ.get("MISTRAL_AGENT2_STORE", "true").lower() not in {"0", "false", "no"}

    body = {
        "agent_id": agent_id,
        "agent_version": int(agent_version) if str(agent_version).isdigit() else agent_version,
        "inputs": prompt,
        "stream": False,
        "store": store,
    }
    req = request.Request(
        f"{api_base}/conversations",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    append_agent_log(
        f"Calling Mistral Agent 2 id={agent_id} version={agent_version} key={redact(api_key)}"
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Mistral API HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Mistral API request failed: {exc}") from exc


def extract_text(response: dict[str, Any]) -> str:
    outputs = response.get("outputs") or []
    chunks: list[str] = []
    for output in outputs:
        content = output.get("content") if isinstance(output, dict) else None
        if isinstance(content, str):
            chunks.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    chunks.append(item["text"])
                elif isinstance(item, str):
                    chunks.append(item)
    return "\n".join(chunk.strip() for chunk in chunks if chunk.strip()).strip()


def payload_file_stem(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "playground_prompt"
    for key in ("input_json_file", "input_file", "log_file"):
        value = str(payload.get(key) or "").strip()
        if value:
            return safe_filename_part(Path(value).stem)
    return "handoff"


def write_report(response: dict[str, Any], source_name: str = "handoff", file_stem: str = "handoff") -> Path:
    report_text = extract_text(response) or json.dumps(response, indent=2)
    report_name = f"agent2_{safe_filename_part(file_stem)}_{local_report_date_filename()}.md"
    report_path = unique_path(agent2_named_logs_dir(file_stem) / report_name)
    conversation_id = response.get("conversation_id")
    header = (
        "# Agent 2 Report\n\n"
        f"Timestamp: {local_timestamp_label()}\n"
        f"Source: {source_name}\n"
        f"Date: {local_report_date_label()}\n"
    )
    if conversation_id:
        header += f"Conversation ID: {conversation_id}\n"
    report_path.write_text(f"{header}\n{report_text}\n", encoding="utf-8")
    saved = save_agent2_report_note(
        file_stem,
        f"{header}\n{report_text}\n",
        source_name,
        Path(os.environ.get("INTERVIEW_SQLITE_DB", str(DEFAULT_DB_PATH))),
        report_path.as_posix(),
    )
    if saved:
        append_agent_log(f"Stored Agent 2 report in SQLite for {file_stem}")
    append_agent_log(f"Wrote Agent 2 report to {report_path}")
    return report_path


def write_prompt_log(prompt: str, source_name: str, file_stem: str) -> Path:
    prompt_name = f"agent2_prompt_{safe_filename_part(file_stem)}_{local_report_date_filename()}_{local_file_stamp(include_date=False)}.md"
    prompt_path = unique_path(agent2_named_logs_dir(file_stem) / prompt_name)
    prompt_header = (
        "# Agent 2 Prompt\n\n"
        f"Timestamp: {local_timestamp_label()}\n"
        f"Source: {source_name}\n\n"
        "## Prompt\n\n"
    )
    prompt_path.write_text(f"{prompt_header}{prompt}", encoding="utf-8")
    append_agent_log(f"Wrote Agent 2 prompt to {prompt_path}")
    return prompt_path


def write_error_report(exc: Exception, source_name: str, file_stem: str, prompt_path: Path) -> Path:
    error_name = f"agent2_error_{safe_filename_part(file_stem)}_{local_report_date_filename()}_{local_file_stamp(include_date=False)}.md"
    error_path = unique_path(agent2_named_logs_dir(file_stem) / error_name)
    body = (
        "# Agent 2 Error\n\n"
        f"Timestamp: {local_timestamp_label()}\n"
        f"Source: {source_name}\n"
        f"Prompt file: {prompt_path}\n\n"
        "## Error\n\n"
        f"```text\n{type(exc).__name__}: {exc}\n```\n"
    )
    error_path.write_text(body, encoding="utf-8")
    append_agent_log(f"Wrote Agent 2 error report to {error_path}")
    return error_path


def run(ws_url: str | None, prompt: str | None, dry_run: bool) -> tuple[Path, str]:
    load_dotenv(Path.cwd() / ".env")
    payload: dict[str, Any] | None = None
    if ws_url:
        payload = json.loads(websocket_receive_text(ws_url))
        built_prompt = build_prompt(payload)
        source_name = str(payload.get("log_file") or "websocket handoff")
    elif prompt:
        built_prompt = prompt
        source_name = "playground prompt"
    else:
        built_prompt = DEFAULT_PLAYGROUND_PROMPT
        source_name = "playground prompt"

    file_stem = payload_file_stem(payload)
    prompt_path = write_prompt_log(built_prompt, source_name, file_stem)
    if dry_run:
        return prompt_path, built_prompt

    append_agent_log(f"Agent 2 live prompt ready chars={len(built_prompt)} prompt={prompt_path}")
    try:
        response = call_mistral_agent(built_prompt)
        append_agent_log(f"Agent 2 live response received for {file_stem}")
        report_path = write_report(response, source_name, file_stem)
    except Exception as exc:
        error_path = write_error_report(exc, source_name, file_stem, prompt_path)
        raise RuntimeError(f"{exc} (wrote Agent 2 error report to {error_path})") from exc
    return report_path, extract_text(response) or json.dumps(response, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Talk to the configured Mistral Agent 2.")
    parser.add_argument("ws_url", nargs="?", help="Local websocket URL from src/bridge/agent2_connection.py")
    parser.add_argument(
        "--prompt",
        "-p",
        help="Playground-style message to send to Agent 2. Defaults to a short connection test.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Write the prompt instead of calling Mistral")
    args = parser.parse_args()

    try:
        path, text = run(args.ws_url, args.prompt, args.dry_run)
        print(text)
        print(f"\nSaved to: {path}")
        return 0
    except Exception as exc:
        append_agent_log(f"ERROR {exc}")
        print(f"Agent 2 failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
