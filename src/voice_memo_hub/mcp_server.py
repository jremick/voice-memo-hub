from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

from .actions import list_action_candidates, prepare_codex_task, update_action_status
from .paths import db_path, default_runtime_dir, ensure_runtime_dirs
from .queries import digest, recent_recordings, recording_detail, search_transcripts
from .store import init_db


def runtime_db(runtime_dir: Optional[str]) -> Path:
    runtime = Path(runtime_dir).expanduser() if runtime_dir else default_runtime_dir()
    ensure_runtime_dirs(runtime)
    path = db_path(runtime)
    init_db(path)
    return path


def tools() -> list[dict]:
    return [
        {
            "name": "memo_recent",
            "description": "List recent Voice Memo Hub recordings with transcript excerpts.",
            "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer"}}},
        },
        {
            "name": "memo_search",
            "description": "Search Voice Memo Hub transcripts with SQLite FTS5.",
            "inputSchema": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
                "required": ["query"],
            },
        },
        {
            "name": "memo_get",
            "description": "Read one recording, latest transcript, and segments.",
            "inputSchema": {
                "type": "object",
                "properties": {"recording_id": {"type": "string"}},
                "required": ["recording_id"],
            },
        },
        {
            "name": "memo_action_candidates",
            "description": "List action candidates for review.",
            "inputSchema": {
                "type": "object",
                "properties": {"status": {"type": "string"}, "limit": {"type": "integer"}},
            },
        },
        {
            "name": "memo_mark_reviewed",
            "description": "Mark an action candidate reviewed.",
            "inputSchema": {
                "type": "object",
                "properties": {"action_id": {"type": "integer"}, "note": {"type": "string"}},
                "required": ["action_id"],
            },
        },
        {
            "name": "memo_prepare_codex_task",
            "description": "Prepare a safe Codex task prompt from an action candidate.",
            "inputSchema": {
                "type": "object",
                "properties": {"action_id": {"type": "integer"}},
                "required": ["action_id"],
            },
        },
        {
            "name": "memo_digest",
            "description": "Render a Markdown digest of recent recordings.",
            "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer"}}},
        },
    ]


def call_tool(name: str, arguments: dict[str, Any]) -> Any:
    path = runtime_db(arguments.pop("runtime_dir", None))
    if name == "memo_recent":
        return recent_recordings(path, int(arguments.get("limit", 10)))
    if name == "memo_search":
        return search_transcripts(path, arguments["query"], int(arguments.get("limit", 20)))
    if name == "memo_get":
        return recording_detail(path, arguments["recording_id"])
    if name == "memo_action_candidates":
        return list_action_candidates(path, arguments.get("status"), int(arguments.get("limit", 20)))
    if name == "memo_mark_reviewed":
        return update_action_status(path, int(arguments["action_id"]), "reviewed", arguments.get("note"))
    if name == "memo_prepare_codex_task":
        return prepare_codex_task(path, int(arguments["action_id"]))
    if name == "memo_digest":
        return digest(path, int(arguments.get("limit", 10)))
    raise ValueError(f"Unknown tool: {name}")


def read_message() -> Optional[dict]:
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            break
        key, _, value = line.decode("utf-8").partition(":")
        headers[key.lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))


def write_message(message: dict) -> None:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def result_response(request_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error_response(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(message: dict) -> Optional[dict]:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        return result_response(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "voice-memo-hub", "version": "0.1.0a2"},
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return result_response(request_id, {"tools": tools()})
    if method == "tools/call":
        try:
            content = call_tool(params["name"], params.get("arguments") or {})
            return result_response(
                request_id,
                {"content": [{"type": "text", "text": json.dumps(content, indent=2, default=str)}]},
            )
        except Exception as exc:  # noqa: BLE001 - MCP should return structured errors.
            return error_response(request_id, -32000, str(exc))
    return error_response(request_id, -32601, f"Method not found: {method}")


def main() -> int:
    while True:
        message = read_message()
        if message is None:
            return 0
        response = handle(message)
        if response is not None:
            write_message(response)


if __name__ == "__main__":
    raise SystemExit(main())
