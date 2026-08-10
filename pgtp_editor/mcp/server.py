# PGTP Editor — companion editor for SQL Maestro PostgreSQL PHP Generator .pgtp files
# Copyright (C) 2026  Botond Zalai-Ruzsics
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# pgtp_editor/mcp/server.py
"""The stdio transport for §23's MCP server — the protocol layer, kept thin.

§23 asks for stdio. The official `mcp` SDK is **not a dependency of this
project** and is not installed; adding one for an optional, off-by-default
feature would tax every install for a capability most users never enable. So
the transport is hand-written here against MCP's own stdio framing —
newline-delimited JSON-RPC 2.0 on stdin/stdout — and deliberately isolated:
`tools.py` (the part that matters, and the part that is tested) has no import
of, or knowledge of, any protocol at all. Swapping this module for an SDK
`Server` later changes nothing above it. `sdk_available()` reports whether the
SDK is importable, for a caller that wants to prefer it.

Implemented methods: `initialize`, `notifications/initialized`, `ping`,
`tools/list`, `tools/call`. Anything else answers JSON-RPC error -32601. A
failing tool answers as an MCP tool error (`isError: true`) rather than a
protocol error, which is what clients expect; an *unknown tool name* is a
caller mistake and answers -32602.

**Nothing in this module runs at import time.** `serve_stdio` must be called
explicitly — §23's "off by default, opt-in; it must not be silent or
default-on" is enforced structurally, not by a flag. Both entry points (Tools ▸
"Start MCP Server" and `--mcp`) are explicit user actions.

Diagnostics go to **stderr** only. stdout is the protocol channel and a stray
`print` there corrupts the session.
"""
from __future__ import annotations

import json
import sys
import threading

from pgtp_editor.mcp.providers import ProjectUnavailableError
from pgtp_editor.mcp.tools import ToolArgumentError, UnknownToolError, build_registry

#: The MCP revision this transport speaks.
PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "pgtp-editor"
SERVER_VERSION = "0.4.0"

# JSON-RPC 2.0 error codes used here.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def sdk_available() -> bool:
    """True if the official `mcp` SDK is importable. Informational only —
    this module never needs it."""
    try:
        import mcp  # noqa: F401, PLC0415 — probe only
    except ImportError:
        return False
    return True


class StdioServer:
    """One MCP session over a pair of text streams.

    `handle()` is a pure function of one decoded JSON-RPC message, so the whole
    protocol surface is testable without touching real stdio; `serve()` is just
    the read/write loop around it.
    """

    def __init__(self, registry=None, *, name: str = SERVER_NAME,
                 version: str = SERVER_VERSION):
        self.registry = registry if registry is not None else build_registry()
        self.name = name
        self.version = version
        self._stop = threading.Event()

    # -- protocol ----------------------------------------------------------

    def handle(self, message) -> dict | None:
        """Answer one request. Returns `None` for notifications (which by
        JSON-RPC rule get no reply) and for messages that are not requests.
        """
        if not isinstance(message, dict):
            return _error(None, INVALID_REQUEST, "request must be a JSON object")
        method = message.get("method")
        request_id = message.get("id")
        if not isinstance(method, str):
            return _error(request_id, INVALID_REQUEST, "missing 'method'")
        params = message.get("params") or {}

        if method.startswith("notifications/"):
            return None
        if method == "initialize":
            return _result(request_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": self.name, "version": self.version},
            })
        if method == "ping":
            return _result(request_id, {})
        if method == "tools/list":
            return _result(request_id, {"tools": self.registry.descriptors()})
        if method == "tools/call":
            return self._call_tool(request_id, params)
        return _error(request_id, METHOD_NOT_FOUND, f"unknown method: {method}")

    def _call_tool(self, request_id, params) -> dict:
        if not isinstance(params, dict):
            return _error(request_id, INVALID_PARAMS, "params must be an object")
        name = params.get("name")
        if not isinstance(name, str):
            return _error(request_id, INVALID_PARAMS, "missing tool 'name'")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _error(request_id, INVALID_PARAMS, "'arguments' must be an object")
        try:
            payload = self.registry.call(name, arguments)
        except UnknownToolError as exc:
            return _error(request_id, INVALID_PARAMS, str(exc))
        except (ToolArgumentError, ProjectUnavailableError) as exc:
            return _result(request_id, _tool_error(str(exc)))
        except Exception as exc:  # noqa: BLE001 — a tool failure must not kill the session
            return _result(request_id, _tool_error(f"{type(exc).__name__}: {exc}"))
        return _result(request_id, {
            "content": [{"type": "text", "text": json.dumps(payload, indent=2,
                                                            default=str)}],
            "structuredContent": payload,
            "isError": False,
        })

    # -- transport ---------------------------------------------------------

    def stop(self) -> None:
        """Ask `serve()` to finish after the message in flight."""
        self._stop.set()

    def serve(self, stdin=None, stdout=None) -> None:
        """Read newline-delimited JSON-RPC from `stdin` until EOF or `stop()`."""
        stdin = stdin if stdin is not None else sys.stdin
        stdout = stdout if stdout is not None else sys.stdout
        for line in stdin:
            if self._stop.is_set():
                break
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                _write(stdout, _error(None, PARSE_ERROR, f"invalid JSON: {exc}"))
                continue
            try:
                response = self.handle(message)
            except Exception as exc:  # noqa: BLE001 — never drop the session
                request_id = message.get("id") if isinstance(message, dict) else None
                response = _error(request_id, INTERNAL_ERROR,
                                  f"{type(exc).__name__}: {exc}")
            if response is not None:
                _write(stdout, response)


def serve_stdio(registry=None, *, provider=None, introspector=None,
                stdin=None, stdout=None) -> StdioServer:
    """Build a server and run it to EOF. THE headless `--mcp` entry point.

    Returns the `StdioServer` once the peer closes stdin, so a caller can
    inspect it in tests. Pass `provider`/`introspector` to build the default
    registry differently, or `registry` to supply one outright.
    """
    if registry is None:
        registry = build_registry(provider, introspector=introspector)
    server = StdioServer(registry)
    server.serve(stdin=stdin, stdout=stdout)
    return server


def start_server_thread(provider=None, *, registry=None, introspector=None,
                        stdin=None, stdout=None) -> tuple[StdioServer,
                                                          threading.Thread]:
    """Run a stdio server on a daemon thread. THE Tools ▸ "Start MCP Server"
    entry point: the GUI thread must not block on stdin.

    Returns `(server, thread)`; the menu action keeps the pair and calls
    `server.stop()` to end the session (the thread finishes after the message
    in flight, or at EOF). Nothing here is started implicitly — the caller
    always makes the decision, per §23.
    """
    if registry is None:
        registry = build_registry(provider, introspector=introspector)
    server = StdioServer(registry)
    thread = threading.Thread(
        target=server.serve,
        kwargs={"stdin": stdin, "stdout": stdout},
        name="pgtp-mcp-stdio",
        daemon=True,
    )
    thread.start()
    return server, thread


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _result(request_id, payload) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def _error(request_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": code, "message": message}}


def _tool_error(message: str) -> dict:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _write(stream, message) -> None:
    stream.write(json.dumps(message, default=str) + "\n")
    flush = getattr(stream, "flush", None)
    if flush is not None:
        flush()
