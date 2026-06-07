"""First-agent bridge for creating and delivering handoffs to Agent 2."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger(__name__)
WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def path_for_browser(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_pipeline_log_path(raw_path: str) -> Path:
    log_root = (Path.cwd() / "logs").resolve()
    requested = Path(raw_path)
    resolved = requested.resolve() if requested.is_absolute() else (Path.cwd() / requested).resolve()
    if log_root not in (resolved, *resolved.parents):
        raise ValueError("pipeline log path must be inside the logs directory")
    return resolved


def resolve_input_text_path(raw_path: str) -> Path:
    input_root = (Path.cwd() / "input data").resolve()
    requested = Path(raw_path)
    resolved = requested.resolve() if requested.is_absolute() else (Path.cwd() / requested).resolve()
    if input_root not in (resolved, *resolved.parents):
        raise ValueError("input text path must be inside the input data directory")
    if resolved.suffix.lower() != ".txt":
        raise ValueError("input file must be a .txt file")
    return resolved


def resolve_input_json_path(raw_path: str) -> Path:
    input_root = (Path.cwd() / "input data").resolve()
    requested = Path(raw_path)
    resolved = requested.resolve() if requested.is_absolute() else (Path.cwd() / requested).resolve()
    if input_root not in (resolved, *resolved.parents):
        raise ValueError("input JSON path must be inside the input data directory")
    if resolved.suffix.lower() != ".json":
        raise ValueError("input JSON file must be a .json file")
    return resolved


def websocket_frame_text(text: str) -> bytes:
    payload = text.encode("utf-8")
    header = bytearray([0x81])
    length = len(payload)
    if length < 126:
        header.append(length)
    elif length < 65536:
        header.extend([126, (length >> 8) & 0xFF, length & 0xFF])
    else:
        header.extend(
            [
                127,
                (length >> 56) & 0xFF,
                (length >> 48) & 0xFF,
                (length >> 40) & 0xFF,
                (length >> 32) & 0xFF,
                (length >> 24) & 0xFF,
                (length >> 16) & 0xFF,
                (length >> 8) & 0xFF,
                length & 0xFF,
            ]
        )
    return bytes(header) + payload


def write_json_response(handler: SimpleHTTPRequestHandler, status: HTTPStatus, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Agent2Bridge:
    def __init__(self, agent2_script: Path | None = None) -> None:
        self.agent2_script = agent2_script or Path(__file__).with_name("agent2.py")
        self._pending_payloads: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def queue_payload(
        self,
        log_file: Path,
        input_file: Path,
        input_json_file: Path | None = None,
    ) -> dict[str, Any]:
        if not log_file.exists():
            raise FileNotFoundError(f"Evaluation log not found yet: {log_file}")
        if not input_file.exists():
            raise FileNotFoundError(f"Input text file not found: {input_file}")
        if input_json_file is not None and not input_json_file.exists():
            raise FileNotFoundError(f"Input JSON file not found: {input_json_file}")

        payload = {
            "type": "evaluation_handoff",
            "created_at": utc_timestamp(),
            "log_file": path_for_browser(log_file),
            "input_file": path_for_browser(input_file),
            "log_text": log_file.read_text(encoding="utf-8", errors="replace"),
            "input_text": input_file.read_text(encoding="utf-8", errors="replace"),
        }
        if input_json_file is not None:
            payload["input_json_file"] = path_for_browser(input_json_file)
            payload["input_json_text"] = input_json_file.read_text(encoding="utf-8", errors="replace")
        with self._lock:
            self._pending_payloads.append(payload)
        return payload

    def pop_payload(self) -> dict[str, Any]:
        with self._lock:
            payload = self._pending_payloads.pop(0) if self._pending_payloads else None
        return payload or {
            "type": "evaluation_handoff",
            "created_at": utc_timestamp(),
            "error": "no pending Agent 2 payload",
        }

    def start_agent2(self, ws_url: str) -> None:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        command = [sys.executable, str(self.agent2_script.resolve()), ws_url]
        if os.environ.get("MISTRAL_AGENT2_DRY_RUN", "").lower() in {"1", "true", "yes"}:
            command.append("--dry-run")
        subprocess.Popen(
            command,
            cwd=Path.cwd(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )

    def handle_handoff(self, handler: SimpleHTTPRequestHandler, port: int) -> None:
        try:
            content_length = int(handler.headers.get("Content-Length", "0"))
            body = handler.rfile.read(content_length).decode("utf-8")
            payload = json.loads(body)
            log_file = resolve_pipeline_log_path(str(payload.get("log_file", "")))
            input_file = resolve_input_text_path(str(payload.get("input_file", "")))
            raw_json_file = str(payload.get("input_json_file", "")).strip()
            input_json_file = resolve_input_json_path(raw_json_file) if raw_json_file else None
            queued = self.queue_payload(log_file, input_file, input_json_file)
            ws_url = f"ws://127.0.0.1:{port}/agent2-ws"
            self.start_agent2(ws_url)
            LOGGER.info(
                "Queued Agent 2 handoff: log=%s input=%s json=%s bytes=%s/%s/%s",
                log_file,
                input_file,
                input_json_file,
                len(str(queued["log_text"])),
                len(str(queued["input_text"])),
                len(str(queued.get("input_json_text", ""))),
            )
            write_json_response(
                handler,
                HTTPStatus.OK,
                {
                    "status": "queued",
                    "message": "evaluation log, input text, and input JSON queued for Agent 2 websocket delivery",
                    "websocket": ws_url,
                },
            )
        except Exception as exc:
            write_json_response(handler, HTTPStatus.BAD_REQUEST, {"status": "error", "message": str(exc)})

    def handle_websocket(self, handler: SimpleHTTPRequestHandler) -> None:
        key = handler.headers.get("Sec-WebSocket-Key", "")
        if not key:
            handler.send_error(HTTPStatus.BAD_REQUEST, "Missing Sec-WebSocket-Key")
            return
        accept = base64.b64encode(
            hashlib.sha1((key + WEBSOCKET_GUID).encode("ascii")).digest()
        ).decode("ascii")
        handler.send_response(HTTPStatus.SWITCHING_PROTOCOLS)
        handler.send_header("Upgrade", "websocket")
        handler.send_header("Connection", "Upgrade")
        handler.send_header("Sec-WebSocket-Accept", accept)
        handler.end_headers()
        handler.wfile.write(websocket_frame_text(json.dumps(self.pop_payload())))
        handler.wfile.flush()
