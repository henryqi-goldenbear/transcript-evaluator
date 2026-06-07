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
import logging
import os
import re
import socket
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse
from urllib import error, request
from agent2_connection import Agent2Bridge, resolve_pipeline_log_path, write_json_response
from patterns import SPEAKER_RE, NON_QUESTION_PATTERNS, BEHAVIORAL_PATTERNS, FOLLOW_UP_PATTERNS, CLARIFYING_PATTERNS, DEEPENING_PATTERNS


LOGGER = logging.getLogger(__name__)
EVALUATOR_PORT = 3000
AGENT2_BRIDGE = Agent2Bridge()
DEFAULT_MISTRAL_MODEL = "mistral-small-latest"
DEFAULT_MISTRAL_API_BASE = "https://api.mistral.ai/v1"
EVALUATOR_ASSET_VERSION = "mistral-small-1"


def local_time_mark() -> str:
    return datetime.now().strftime("%H:%M:%S")


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


def log_path_for_input(input_path: Path) -> Path:
    return Path("logs") / f"{input_path.stem}_eval.log"


def configure_file_logging(log_file: Path) -> Path:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_file,
        filemode="a",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        encoding="utf-8",
    )
    return log_file

# extract turns from raw text
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
def _classify_turn(question_text: str,ollama_model: str | None, ollama_host: str,) -> dict[str, str | bool]:
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
            case_id += 1

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
    evaluator_html_path: str = "evaluator.html",
    log_file: Path | None = None,
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
    if log_file is not None:
        query_args["log_file"] = log_path_for_browser(log_file)
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
        [sys.executable, str(Path(__file__).resolve()), "--serve-internal", str(server_port)],
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
        "temperature": 0.15,
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
        if self.path != "/pipeline-log":
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(body)
            log_file = resolve_pipeline_log_path(str(payload.get("log_file", "")))
            text = str(payload.get("text", ""))
            if not text:
                raise ValueError("missing text")
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("a", encoding="utf-8", newline="") as f:
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
    parser = argparse.ArgumentParser(
        description="Convert transcript text into evaluator-ready JSON and run evaluation."
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Path to transcript text file. If omitted, you will be prompted.",
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
        default="evaluator.html",
        help="Path to evaluator.html. Defaults to evaluator.html in this folder.",
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
        "--serve-internal",
        type=int,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    if args.serve_internal:
        run_pipeline_server(args.serve_internal)
        return

    input_path = get_input_path(args.input)
    batch_size = get_batch_size(args.batch_size)
    log_file = configure_file_logging(log_path_for_input(input_path))
    LOGGER.info("Starting convert and evaluate task; logging to %s", log_file)
    LOGGER.info("input=%s batch_size=%s", input_path, batch_size)

    if not input_path.exists():
        LOGGER.error("Input file not found: %s", input_path)
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if input_path.suffix.lower() != ".txt":
        LOGGER.error("Input must be a .txt file. Got: %s", input_path.name)
        raise ValueError(f"Input must be a .txt file. Got: {input_path.name}")

    conversion_started_at = local_time_mark()
    output_path = input_path.with_suffix(".json")
    raw_text = input_path.read_text(encoding="utf-8")
    LOGGER.info(
        "Parsing transcript: input=%s chars=%s classifier=%s",
        input_path,
        len(raw_text),
        f"ollama:{args.ollama_model}" if args.ollama_model else "heuristic-only",
    )
    parsed_cases = parse_transcript_to_test_cases(
        raw_text,
        ollama_model=args.ollama_model,
        ollama_host=args.ollama_host,
    )
    LOGGER.info("Parsed transcript into %s cases", len(parsed_cases))
    log_parsed_cases(parsed_cases)
    output_path.write_text(
        json.dumps(parsed_cases, indent=args.indent), encoding="utf-8"
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

    classifier_mode = (
        f"ollama:{args.ollama_model}" if args.ollama_model else "heuristic-only"
    )
    print(f"Wrote JSON to: {output_path}")
    print(f"Cases: {len(parsed_cases)}")
    print(f"Classifier: {classifier_mode}")
    evaluator_url = run_evaluator_html(output_path, batch_size, args.evaluator_html, log_file)
    print(f"Opened evaluator: {evaluator_url}")


if __name__ == "__main__":
    main()
