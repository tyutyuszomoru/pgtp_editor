"""§23 — Tools ▸ Start MCP Server, and the GUI half of the provider contract.

`pgtp_editor/mcp/` was complete and tested but reachable only headlessly
(`--mcp` / `python -m pgtp_editor.mcp`), and `LiveProjectProvider` -- the "shares
the currently-open in-memory model" half of §23 -- was constructed nowhere.

No test here may enter a real stdio loop: `StdioServer.serve` blocks on stdin.
The host exposes `_mcp_start` for exactly that, an injectable stand-in for
`mcp.start_server_thread`. The PROVIDER is never stubbed -- it is the thing under
test.
"""
from pgtp_editor.mcp import LiveProjectProvider
from pgtp_editor.ui.main_window import MainWindow
from tests.ui._menu_helpers import find_action, find_top_menu

_MINIMAL_PGTP = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Project fileName="demo">\n'
    '  <Page fileName="p1" tableName="pr.equipment" caption="Equipment"/>\n'
    "</Project>\n"
)


class _FakeServer:
    def __init__(self):
        self.stopped = 0

    def stop(self):
        self.stopped += 1


def _window(qtbot, tmp_path):
    window = MainWindow(generator_config_dir=tmp_path)
    qtbot.addWidget(window)
    return window


def _instrumented(qtbot, tmp_path):
    """A window whose MCP start is recorded instead of spawning a stdio thread."""
    window = _window(qtbot, tmp_path)
    started = []

    def fake_start(provider):
        started.append(provider)
        return (_FakeServer(), object())

    window._mcp_start = fake_start
    return window, started


def _action(window):
    return find_action(find_top_menu(window, "Tools"), "Start MCP Server")


# -- the gesture ------------------------------------------------------------


def test_the_menu_entry_exists_and_is_off_by_default(qtbot, tmp_path):
    """§23: "off by default … must not be silent or default-on"."""
    window = _window(qtbot, tmp_path)
    action = _action(window)
    assert action is not None
    assert action.isCheckable() is True
    assert action.isChecked() is False
    assert window._mcp_session is None
    assert window._mcp_action is action


def test_checking_the_entry_starts_a_session(qtbot, tmp_path):
    window, started = _instrumented(qtbot, tmp_path)

    _action(window).setChecked(True)

    assert len(started) == 1
    assert window._mcp_session is not None
    assert "MCP server" in window.statusBar().currentMessage()


def test_unchecking_stops_the_session(qtbot, tmp_path):
    window, started = _instrumented(qtbot, tmp_path)
    _action(window).setChecked(True)
    server = window._mcp_session[0]

    _action(window).setChecked(False)

    assert server.stopped == 1
    assert window._mcp_session is None
    assert window.statusBar().currentMessage() == "MCP server stopped."


def test_a_second_check_does_not_stack_a_second_server(qtbot, tmp_path):
    window, started = _instrumented(qtbot, tmp_path)
    _action(window).setChecked(True)
    window._on_mcp_server_toggled(True)
    assert len(started) == 1


def test_stopping_when_nothing_runs_is_a_no_op(qtbot, tmp_path):
    window, _started = _instrumented(qtbot, tmp_path)
    window._on_mcp_server_toggled(False)  # must not raise
    assert window._mcp_session is None


def test_a_failed_start_snaps_the_checkbox_back(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    def boom(provider):
        raise OSError("no stdio")

    window._mcp_start = boom
    _action(window).setChecked(True)

    assert window._mcp_session is None
    assert _action(window).isChecked() is False
    assert "Could not start the MCP server" in window.statusBar().currentMessage()


def test_closing_the_window_ends_the_session(qtbot, tmp_path):
    window, _started = _instrumented(qtbot, tmp_path)
    _action(window).setChecked(True)
    server = window._mcp_session[0]

    window.close()

    assert server.stopped == 1
    assert window._mcp_session is None


# -- LiveProjectProvider is genuinely constructed and shares the open model --


def test_the_provider_is_a_real_live_project_provider(qtbot, tmp_path):
    window, started = _instrumented(qtbot, tmp_path)
    _action(window).setChecked(True)
    assert isinstance(started[0], LiveProjectProvider)


def test_a_path_less_call_resolves_the_open_in_memory_model(qtbot, tmp_path):
    """The in-app server's whole reason to exist (§23): it answers from the
    editor's live model, including edits reparsed into it but never saved."""
    window, started = _instrumented(qtbot, tmp_path)
    path = tmp_path / "demo.pgtp"
    path.write_text(_MINIMAL_PGTP, encoding="utf-8", newline="")
    window.open_project_file(str(path))
    _action(window).setChecked(True)

    resolved = started[0].resolve(None)

    assert resolved.project is window._current_project
    assert resolved.path == str(path)


def test_the_provider_reads_the_host_at_call_time_not_at_start_time(qtbot, tmp_path):
    """It is handed a zero-argument callable, so opening a different project
    after the server started is reflected without restarting it."""
    window, started = _instrumented(qtbot, tmp_path)
    _action(window).setChecked(True)
    provider = started[0]

    first = tmp_path / "a.pgtp"
    first.write_text(_MINIMAL_PGTP, encoding="utf-8", newline="")
    window.open_project_file(str(first))
    assert provider.resolve(None).path == str(first)

    second = tmp_path / "b.pgtp"
    second.write_text(_MINIMAL_PGTP, encoding="utf-8", newline="")
    window.open_project_file(str(second))
    assert provider.resolve(None).path == str(second)


def test_a_call_naming_another_file_still_loads_it_from_disk(qtbot, tmp_path):
    window, started = _instrumented(qtbot, tmp_path)
    open_path = tmp_path / "open.pgtp"
    open_path.write_text(_MINIMAL_PGTP, encoding="utf-8", newline="")
    window.open_project_file(str(open_path))
    _action(window).setChecked(True)

    other = tmp_path / "other.pgtp"
    other.write_text(_MINIMAL_PGTP, encoding="utf-8", newline="")
    resolved = started[0].resolve(str(other))

    assert resolved.path == str(other)
    assert resolved.project is not window._current_project
