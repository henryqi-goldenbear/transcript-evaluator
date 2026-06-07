"""Playground-style runner for the configured Mistral Agent 2.

By default this talks directly to the Mistral Agent from the console URL:
https://console.mistral.ai/build/playground?agentId=ag_019e9f09fadc72f7b26c3a4eace4fcd1&from=agents

When launched by agent2_connection.py with a websocket URL, it still accepts
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import urlparse


DEFAULT_AGENT_ID = "ag_019e9f09fadc72f7b26c3a4eace4fcd1"
DEFAULT_AGENT_VERSION = "1"
DEFAULT_API_BASE = "https://api.mistral.ai/v1"
DEFAULT_PLAYGROUND_PROMPT = "Hello! Reply with one short sentence confirming Agent 2 is connected."
MAX_TEXT_CHARS = 60_000


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


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


def append_agent_log(message: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()} {message}\n"
    (agent2_logs_dir() / "agent2.log").open("a", encoding="utf-8").write(line)


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


def build_prompt(payload: dict[str, Any]) -> str:
    if payload.get("error"):
        raise ValueError(str(payload["error"]))
    log_file = payload.get("log_file", "unknown log")
    input_file = payload.get("input_file", "unknown input")
    input_json_file = payload.get("input_json_file", "not provided")
    return f"""You are Agent 2 for the transcript evaluator.

Review the evaluation run below. Use the evaluator JSON and original transcript for context.
Return a concise, actionable QA report with:
1. Verdict: pass, needs review, or fail.
2. Top issues, grouped by severity.
3. Any suspicious scoring, missing evidence, malformed output, or rate-limit/API failures.
4. Concrete next steps.

Evaluation log file: {log_file}
Evaluator JSON file: {input_json_file}
Input transcript file: {input_file}

--- Evaluation log ---
{shorten(str(payload.get("log_text", "")))}

--- Evaluator JSON ---
{shorten(str(payload.get("input_json_text", "")))}

--- Original transcript ---
{shorten(str(payload.get("input_text", "")))}
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


def write_report(response: dict[str, Any], source_name: str = "handoff") -> Path:
    report_text = extract_text(response) or json.dumps(response, indent=2)
    report_path = agent2_logs_dir() / f"agent2_report_{utc_stamp()}.md"
    conversation_id = response.get("conversation_id")
    header = f"# Agent 2 Report\n\nSource: {source_name}\n"
    if conversation_id:
        header += f"Conversation ID: {conversation_id}\n"
    report_path.write_text(f"{header}\n{report_text}\n", encoding="utf-8")
    append_agent_log(f"Wrote Agent 2 report to {report_path}")
    return report_path


def run(ws_url: str | None, prompt: str | None, dry_run: bool) -> tuple[Path, str]:
    load_dotenv(Path.cwd() / ".env")
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

    if dry_run:
        report_path = agent2_logs_dir() / f"agent2_prompt_{utc_stamp()}.txt"
        report_path.write_text(built_prompt, encoding="utf-8")
        append_agent_log(f"Wrote dry-run prompt to {report_path}")
        return report_path, built_prompt

    response = call_mistral_agent(built_prompt)
    report_path = write_report(response, source_name)
    return report_path, extract_text(response) or json.dumps(response, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Talk to the configured Mistral Agent 2.")
    parser.add_argument("ws_url", nargs="?", help="Local websocket URL from agent2_connection.py")
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
