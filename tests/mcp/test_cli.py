# tests/mcp/test_cli.py
"""§23's two start paths: the `--mcp` flag and `python -m pgtp_editor.mcp`.

Both must be strictly opt-in, headless (no QApplication, no `pgtp_editor.ui`
import), and share one implementation. The serve function is always injected or
patched -- a test must never enter a real stdio loop.
"""
import subprocess
import sys

import pytest

import pgtp_editor.main as main_mod
from pgtp_editor.main import parse_args, run_mcp_server

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


class _RecordingServe:
    """Stand-in for `serve_stdio`: records the provider it was handed."""

    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return object()


# --- the flag exists, and is off by default --------------------------------


def test_mcp_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("PGTP_EDITOR_DEBUG", raising=False)
    assert parse_args([]).mcp is False


def test_mcp_flag_sets_true(monkeypatch):
    monkeypatch.delenv("PGTP_EDITOR_DEBUG", raising=False)
    assert parse_args(["--mcp"]).mcp is True


def test_mcp_flag_takes_optional_file(monkeypatch):
    monkeypatch.delenv("PGTP_EDITOR_DEBUG", raising=False)
    args = parse_args(["--mcp", "proj.pgtp"])
    assert (args.mcp, args.file) == (True, "proj.pgtp")


def test_mcp_flag_not_implied_by_a_file_argument(monkeypatch):
    monkeypatch.delenv("PGTP_EDITOR_DEBUG", raising=False)
    assert parse_args(["proj.pgtp"]).mcp is False


# --- run_mcp_server: the one implementation --------------------------------


def test_run_mcp_server_without_path_uses_default_provider(capsys):
    serve = _RecordingServe()

    rc = run_mcp_server(None, serve=serve)

    assert rc == 0
    assert len(serve.calls) == 1
    _, kwargs = serve.calls[0]
    # No path given -> no provider override, so build_registry's own default
    # (FileProjectProvider) applies.
    assert kwargs == {"provider": None}
    assert "MCP server on stdio" in capsys.readouterr().err


def test_run_mcp_server_with_path_defaults_that_project(project_path):
    serve = _RecordingServe()

    rc = run_mcp_server(project_path, serve=serve)

    assert rc == 0
    provider = serve.calls[0][1]["provider"]
    assert isinstance(provider, main_mod._DefaultPathProvider)
    # A path-less call resolves to the command-line project...
    assert provider.resolve(None).path == project_path
    # ...and an explicit path still wins.
    with pytest.raises(Exception) as excinfo:
        provider.resolve("/nonexistent/other.pgtp")
    assert "other.pgtp" in str(excinfo.value)


def test_run_mcp_server_uses_file_provider_not_live(project_path):
    from pgtp_editor.mcp import FileProjectProvider, LiveProjectProvider

    serve = _RecordingServe()
    run_mcp_server(project_path, serve=serve)
    provider = serve.calls[0][1]["provider"]

    assert isinstance(provider._delegate, FileProjectProvider)
    assert not isinstance(provider._delegate, LiveProjectProvider)


def test_run_mcp_server_missing_file_errors_without_traceback(tmp_path, capsys):
    serve = _RecordingServe()
    missing = tmp_path / "nope.pgtp"

    rc = run_mcp_server(str(missing), serve=serve)

    err = capsys.readouterr().err
    assert rc != 0
    assert serve.calls == []
    assert "no such .pgtp file" in err
    assert "Traceback" not in err


def test_run_mcp_server_unreadable_file_errors(tmp_path, capsys):
    unreadable = tmp_path / "locked.pgtp"
    unreadable.write_text(PROJECT_XML, encoding="utf-8")
    unreadable.chmod(0o000)
    try:
        with unreadable.open("rb"):
            pytest.skip("cannot make a file unreadable (running as root?)")
    except PermissionError:
        pass

    serve = _RecordingServe()
    try:
        rc = run_mcp_server(str(unreadable), serve=serve)
    finally:
        unreadable.chmod(0o600)

    err = capsys.readouterr().err
    assert rc != 0
    assert serve.calls == []
    assert "cannot read" in err
    assert "Traceback" not in err


def test_run_mcp_server_directory_argument_errors(tmp_path, capsys):
    serve = _RecordingServe()

    rc = run_mcp_server(str(tmp_path), serve=serve)

    assert rc != 0
    assert serve.calls == []
    assert "no such .pgtp file" in capsys.readouterr().err


# --- main(): the flag routes to the headless path, GUI-free ----------------


@pytest.fixture
def quiet_debuglog(monkeypatch):
    monkeypatch.setattr(main_mod.debuglog, "setup", lambda debug: None)
    monkeypatch.setattr(main_mod.debuglog, "install_qt_handler", lambda: None)


def test_main_with_mcp_flag_never_builds_a_gui(monkeypatch, quiet_debuglog):
    from PySide6 import QtWidgets

    called = []
    monkeypatch.setattr(main_mod, "run_mcp_server", lambda path: called.append(path) or 0)

    class _ExplodingApp:
        """Any attempt to construct it fails the test. `instance()` stays sane
        so pytest-qt's own setup/teardown hooks keep working."""

        def __init__(self, *args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("--mcp must not construct a QApplication")

        @staticmethod
        def instance():
            return None

    monkeypatch.setattr(QtWidgets, "QApplication", _ExplodingApp)
    monkeypatch.setattr(main_mod.sys, "argv", ["pgtp_editor", "--mcp"])

    assert main_mod.main() == 0
    assert called == [None]


def test_main_with_mcp_flag_passes_the_file(monkeypatch, quiet_debuglog,
                                            project_path):
    called = []
    monkeypatch.setattr(main_mod, "run_mcp_server", lambda path: called.append(path) or 3)
    monkeypatch.setattr(main_mod.sys, "argv", ["pgtp_editor", "--mcp", project_path])

    assert main_mod.main() == 3
    assert called == [project_path]


def test_main_without_the_flag_starts_no_server(monkeypatch, quiet_debuglog):
    """Normal startup is unchanged: run_mcp_server is never reached."""
    monkeypatch.setattr(
        main_mod, "run_mcp_server",
        lambda path: pytest.fail("no --mcp: the server must not start"),
    )

    from PySide6 import QtWidgets

    import pgtp_editor.ui.main_window as mw_mod

    class _FakeApp:
        def __init__(self, argv):
            pass

        @staticmethod
        def instance():
            return None

        def exec(self):
            return 0

    class _FakeWindow:
        def __init__(self, *a, **k):
            pass

        def show(self):
            pass

    monkeypatch.setattr(QtWidgets, "QApplication", _FakeApp)
    monkeypatch.setattr(mw_mod, "MainWindow", _FakeWindow)
    monkeypatch.setattr(main_mod.sys, "argv", ["pgtp_editor"])

    assert main_mod.main() == 0


# --- python -m pgtp_editor.mcp reaches the same entry point ----------------


def test_module_main_delegates_to_run_mcp_server(monkeypatch, project_path):
    import pgtp_editor.mcp.__main__ as module_main

    calls = []
    monkeypatch.setattr(module_main, "run_mcp_server",
                        lambda path: calls.append(path) or 0)

    assert module_main.main([project_path]) == 0
    assert calls == [project_path]


def test_module_main_accepts_the_redundant_mcp_flag(monkeypatch, project_path):
    import pgtp_editor.mcp.__main__ as module_main

    calls = []
    monkeypatch.setattr(module_main, "run_mcp_server",
                        lambda path: calls.append(path) or 0)

    assert module_main.main(["--mcp", project_path]) == 0
    assert calls == [project_path]


def test_module_main_with_no_arguments_serves_the_default_provider(monkeypatch):
    """`python -m pgtp_editor.mcp` with no file is a supported invocation (the
    per-tool `path` argument then carries the project), so it must reach the same
    one entry point with `None` rather than erroring on a missing path."""
    import pgtp_editor.mcp.__main__ as module_main

    calls = []
    monkeypatch.setattr(module_main, "run_mcp_server",
                        lambda path: calls.append(path) or 0)

    assert module_main.main([]) == 0
    assert calls == [None]


def test_module_main_missing_file_exits_nonzero(tmp_path, capsys):
    import pgtp_editor.mcp.__main__ as module_main

    rc = module_main.main([str(tmp_path / "gone.pgtp")])

    assert rc == 2
    assert "no such .pgtp file" in capsys.readouterr().err


def test_module_is_runnable_and_speaks_mcp_on_stdio():
    """End-to-end: `python -m pgtp_editor.mcp` really starts a session.

    Bounded, not blocking: stdin is closed immediately after one request, which
    ends the serve loop at EOF.
    """
    import json

    request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}) + "\n"
    proc = subprocess.run(
        [sys.executable, "-m", "pgtp_editor.mcp"],
        input=request, capture_output=True, text=True, timeout=60,
    )

    assert proc.returncode == 0, proc.stderr
    reply = json.loads(proc.stdout.strip().splitlines()[0])
    assert reply["result"]["serverInfo"]["name"] == "pgtp-editor"


def test_module_run_with_missing_file_exits_nonzero_and_says_why():
    proc = subprocess.run(
        [sys.executable, "-m", "pgtp_editor.mcp", "/nonexistent/nope.pgtp"],
        input="", capture_output=True, text=True, timeout=60,
    )

    assert proc.returncode == 2
    assert "no such .pgtp file" in proc.stderr
    assert "Traceback" not in proc.stderr
    assert proc.stdout == ""
