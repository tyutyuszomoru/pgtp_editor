# tests/mcp/test_server.py
"""Unit tests for the §23 stdio transport and its off-by-default posture."""
import io
import json
import subprocess
import sys
import threading

import pytest

from pgtp_editor.mcp import server as server_module
from pgtp_editor.mcp.providers import FileProjectProvider
from pgtp_editor.mcp.server import PROTOCOL_VERSION, StdioServer, serve_stdio
from pgtp_editor.mcp.tools import build_registry

PROJECT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Project><Presentation><Pages>
  <Page fileName="orders.php" tableName="sales.orders" caption="Orders"/>
</Pages></Presentation></Project>
"""


@pytest.fixture
def project_path(tmp_path):
    path = tmp_path / "demo.pgtp"
    path.write_text(PROJECT_XML, encoding="utf-8")
    return str(path)


def _server():
    return StdioServer(build_registry(FileProjectProvider(),
                                      introspector=_never_called))


def _never_called(params):  # pragma: no cover - a DB must never be reached here
    raise AssertionError("the transport tests must not touch a database")


def _request(method, params=None, request_id=1):
    message = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


# ---------------------------------------------------------------------------
# off by default
# ---------------------------------------------------------------------------

def test_importing_the_package_starts_nothing():
    """§23: opt-in, never silent. Import must not spawn a server thread.

    The `sys.modules` purge below is what makes the import a REAL first import,
    and it is restored afterwards: leaving the re-imported modules in place gives
    the process two distinct `LiveProjectProvider` classes, so a later
    `isinstance` check against the one bound at ITS import time fails (seen
    intermittently in `tests/ui/test_mcp_wiring.py` under `-n 10`, where
    `--dist load` decides whether the two files share a worker).
    """
    before = {t.name for t in threading.enumerate()}
    purged = {
        name: module
        for name, module in sys.modules.items()
        if name.startswith("pgtp_editor.mcp")
    }
    for name in purged:
        del sys.modules[name]
    try:
        import pgtp_editor.mcp as package  # noqa: PLC0415 — the point of the test

        after = {t.name for t in threading.enumerate()}
        assert after == before
        assert not any(name.startswith("pgtp-mcp") for name in after)
        assert hasattr(package, "serve_stdio")
    finally:
        sys.modules.update(purged)


def test_headless_import_pulls_neither_qt_nor_psycopg():
    """`--mcp` must run without a GUI. Checked in a clean subprocess because
    this process has already imported Qt via other test modules."""
    probe = (
        "import sys, pgtp_editor.mcp; "
        "print('PySide6' in sys.modules, 'psycopg' in sys.modules)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    assert completed.stdout.strip() == "False False"


def test_constructing_a_server_reads_no_input_and_opens_nothing():
    stdin = io.StringIO('{"jsonrpc":"2.0","id":1,"method":"ping"}\n')
    server = StdioServer(build_registry(FileProjectProvider(),
                                        introspector=_never_called))

    assert stdin.tell() == 0  # nothing consumed until serve() is called
    assert server.registry.names


def test_no_write_tool_is_exposed():
    names = " ".join(_server().registry.names).lower()
    for forbidden in ("exec", "sql", "write", "deploy", "apply", "save", "run"):
        assert forbidden not in names


# ---------------------------------------------------------------------------
# protocol
# ---------------------------------------------------------------------------

def test_initialize_advertises_tools_capability():
    response = _server().handle(_request("initialize"))

    assert response["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert response["result"]["capabilities"]["tools"] == {"listChanged": False}
    assert response["result"]["serverInfo"]["name"] == "pgtp-editor"


def test_tools_list_returns_six_descriptors_with_schemas():
    tools = _server().handle(_request("tools/list"))["result"]["tools"]

    assert len(tools) == 6
    for tool in tools:
        assert tool["inputSchema"]["type"] == "object"
        assert tool["description"]


def test_notifications_get_no_reply():
    assert _server().handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_unknown_method_is_method_not_found():
    response = _server().handle(_request("resources/list"))
    assert response["error"]["code"] == server_module.METHOD_NOT_FOUND


def test_tools_call_returns_structured_content(project_path):
    response = _server().handle(
        _request("tools/call", {"name": "list_pages",
                                "arguments": {"path": project_path}})
    )
    result = response["result"]

    assert result["isError"] is False
    assert result["structuredContent"]["page_count"] == 1
    assert json.loads(result["content"][0]["text"])["page_count"] == 1


def test_unknown_tool_name_is_an_invalid_params_error():
    response = _server().handle(
        _request("tools/call", {"name": "run_sql", "arguments": {}})
    )

    assert "result" not in response
    assert response["error"]["code"] == server_module.INVALID_PARAMS
    assert "run_sql" in response["error"]["message"]


def test_tool_failure_is_reported_as_a_tool_error_not_a_crash():
    response = _server().handle(
        _request("tools/call", {"name": "list_pages", "arguments": {}})
    )
    result = response["result"]

    assert result["isError"] is True
    assert "required" in result["content"][0]["text"]


def test_missing_method_is_an_invalid_request():
    assert _server().handle({"jsonrpc": "2.0", "id": 3})["error"]["code"] == (
        server_module.INVALID_REQUEST
    )


# ---------------------------------------------------------------------------
# the stdio loop
# ---------------------------------------------------------------------------

def test_serve_stdio_answers_a_whole_session_and_stops_at_eof(project_path):
    lines = [
        json.dumps(_request("initialize", request_id=1)),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps(_request("tools/list", request_id=2)),
        json.dumps(
            _request("tools/call",
                     {"name": "read_project", "arguments": {"path": project_path}},
                     request_id=3)
        ),
    ]
    stdout = io.StringIO()

    serve_stdio(
        registry=build_registry(FileProjectProvider(), introspector=_never_called),
        stdin=io.StringIO("\n".join(lines) + "\n"),
        stdout=stdout,
    )

    responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert [r["id"] for r in responses] == [1, 2, 3]  # the notification got no reply
    assert responses[2]["result"]["structuredContent"]["page_count"] == 1


def test_malformed_json_gets_a_parse_error_and_the_session_survives():
    stdout = io.StringIO()
    serve_stdio(
        registry=build_registry(FileProjectProvider(), introspector=_never_called),
        stdin=io.StringIO("{not json\n" + json.dumps(_request("ping", request_id=9)) + "\n"),
        stdout=stdout,
    )

    responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert responses[0]["error"]["code"] == server_module.PARSE_ERROR
    assert responses[1]["id"] == 9


def test_start_server_thread_runs_off_the_calling_thread(project_path):
    """The Tools ▸ "Start MCP Server" path: the GUI thread must not block."""
    stdout = io.StringIO()
    server, thread = server_module.start_server_thread(
        FileProjectProvider(),
        introspector=_never_called,
        stdin=io.StringIO(json.dumps(_request("ping", request_id=7)) + "\n"),
        stdout=stdout,
    )
    thread.join(timeout=5)

    assert thread.daemon
    assert not thread.is_alive()
    assert json.loads(stdout.getvalue())["id"] == 7
    server.stop()  # idempotent once the session has already ended


def test_sdk_availability_is_reported_not_required():
    assert isinstance(server_module.sdk_available(), bool)
