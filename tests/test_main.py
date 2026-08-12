"""--debug activation: CLI flag, env var, setup ordering seam.

Also covers the `file` argument, which FQ-010 narrowed to `--mcp` only: the
positional still exists and still reaches `run_mcp_server` as the headless
server's default project, but **the GUI no longer opens it**. And the FQ-010
startup launcher seam in `main()`.
"""
import importlib

import pytest

import pgtp_editor.main as main_mod
from pgtp_editor.main import main, parse_args


def test_parse_args_default_no_debug(monkeypatch):
    monkeypatch.delenv("PGTP_EDITOR_DEBUG", raising=False)
    assert parse_args([]).debug is False


def test_parse_args_debug_flag():
    assert parse_args(["--debug"]).debug is True


def test_parse_args_env_var(monkeypatch):
    monkeypatch.setenv("PGTP_EDITOR_DEBUG", "1")
    assert parse_args([]).debug is True


def test_parse_args_env_var_zero_is_off(monkeypatch):
    monkeypatch.setenv("PGTP_EDITOR_DEBUG", "0")
    assert parse_args([]).debug is False


def test_parse_args_flag_and_env_var_combined(monkeypatch):
    monkeypatch.setenv("PGTP_EDITOR_DEBUG", "1")
    assert parse_args(["--debug"]).debug is True


def test_parse_args_flag_wins_over_env_var_zero(monkeypatch):
    monkeypatch.setenv("PGTP_EDITOR_DEBUG", "0")
    assert parse_args(["--debug"]).debug is True


def test_parse_args_unknown_arg_still_fails(monkeypatch, capsys):
    monkeypatch.delenv("PGTP_EDITOR_DEBUG", raising=False)
    with pytest.raises(SystemExit):
        parse_args(["--bogus-flag"])


# --- startup file argument: parse_args -------------------------------------


def test_parse_args_no_file_is_none(monkeypatch):
    monkeypatch.delenv("PGTP_EDITOR_DEBUG", raising=False)
    assert parse_args([]).file is None


def test_parse_args_positional_file(monkeypatch):
    monkeypatch.delenv("PGTP_EDITOR_DEBUG", raising=False)
    args = parse_args(["some.pgtp"])
    assert args.file == "some.pgtp"
    assert args.debug is False


def test_parse_args_debug_flag_and_file(monkeypatch):
    monkeypatch.delenv("PGTP_EDITOR_DEBUG", raising=False)
    args = parse_args(["--debug", "x.pgtp"])
    assert args.debug is True
    assert args.file == "x.pgtp"


# --- the `file` argument in main(): --mcp keeps it, the GUI ignores it ------


class _FakeApp:
    """Stand-in for QApplication: records construction, exec() returns 0."""

    def __init__(self, argv):
        self.argv = argv

    @staticmethod
    def instance():
        # pytest-qt's setup/teardown hooks call QApplication.instance();
        # None keeps its _process_events() a no-op.
        return None

    def exec(self):
        return 0


class _FakeMainWindow:
    """Stand-in for MainWindow: records open_project_file / show calls."""

    def __init__(self, *args, **kwargs):
        self.init_kwargs = kwargs
        self.opened = []
        self.shown = False
        #: FQ-010: what the stubbed launcher records, so a test can assert the
        #: default seam fired without entering a modal.
        self.launcher_calls = []

    def show(self):
        self.shown = True

    def open_project_file(self, path):
        self.opened.append(path)


@pytest.fixture
def stub_main(monkeypatch):
    """Neutralise every heavy/modal seam in main() so it runs headless.

    Returns the list of fake MainWindow instances main() constructs. The FQ-010
    launcher is patched out at the module attribute main() resolves it through,
    so no test ever enters a real modal loop; the recorded calls land on each
    fake window's `launcher_calls`.
    """
    from PySide6 import QtWidgets

    import pgtp_editor.ui.launcher_dialog as launcher_mod
    import pgtp_editor.ui.main_window as mw_mod

    # debuglog: no files, no Qt handler.
    monkeypatch.setattr(main_mod.debuglog, "setup", lambda debug: None)
    monkeypatch.setattr(main_mod.debuglog, "install_qt_handler", lambda: None)

    monkeypatch.setattr(QtWidgets, "QApplication", _FakeApp)

    created = []

    def _factory(*args, **kwargs):
        win = _FakeMainWindow(*args, **kwargs)
        created.append(win)
        return win

    monkeypatch.setattr(mw_mod, "MainWindow", _factory)

    def _fake_launcher(window, settings, **kwargs):
        window.launcher_calls.append((settings, kwargs))
        return None

    monkeypatch.setattr(launcher_mod, "show_launcher", _fake_launcher)
    return created


def test_main_never_opens_the_file_argument_in_the_gui(
    monkeypatch, tmp_path, stub_main
):
    """FQ-010: the GUI stopped opening a `.pgtp` passed on the command line
    (the double-click / "Edit with PGTP Editor" path). The argument is parsed
    and then deliberately ignored — no open, and no warning either, because
    ignoring it is now the specified behaviour rather than a failure."""
    pgtp = tmp_path / "proj.pgtp"
    pgtp.write_text("<project/>", encoding="utf-8")
    monkeypatch.setattr(main_mod.sys, "argv", ["pgtp_editor", str(pgtp)])

    rc = main()

    assert rc == 0
    assert len(stub_main) == 1
    window = stub_main[0]
    assert window.shown is True
    assert window.opened == []


def test_main_no_file_arg_does_not_open(monkeypatch, stub_main):
    monkeypatch.setattr(main_mod.sys, "argv", ["pgtp_editor"])

    rc = main()

    assert rc == 0
    assert stub_main[0].opened == []


def test_main_argv_is_injectable(stub_main):
    """`main(argv)` bypasses the real command line — the seam the launcher and
    --mcp tests below drive."""
    assert main([]) == 0
    assert stub_main[0].opened == []


# --- FQ-010: the startup launcher seam --------------------------------------


def test_main_shows_the_launcher_after_the_window(stub_main):
    """It is shown from main(), AFTER window.show(), and never from
    MainWindow.__init__ (49 test files construct one)."""
    order = []
    window_box = {}

    def _launcher(window, settings, **kwargs):
        window_box["window"] = window
        order.append("launcher")
        return None

    assert main([], launcher=_launcher) == 0
    assert order == ["launcher"]
    window = stub_main[0]
    assert window_box["window"] is window
    assert window.shown is True


def test_main_launcher_receives_the_settings_store(stub_main):
    """The suppression flag lives in the SAME QSettings main() already built for
    geometry/theme/toolbar, so the launcher is handed that store."""
    seen = {}
    main([], launcher=lambda window, settings, **kw: seen.setdefault("s", settings))
    from PySide6.QtCore import QSettings

    assert isinstance(seen["s"], QSettings)


def test_main_uses_the_default_launcher_when_none_is_injected(stub_main):
    """With no `launcher=`, main() resolves `launcher_dialog.show_launcher` at
    call time (which is why patching that attribute is a valid test seam)."""
    monkeypatched_calls = stub_main
    assert main([]) == 0
    assert len(monkeypatched_calls[0].launcher_calls) == 1


def test_main_launcher_cancelling_still_returns_the_app_exit_code(stub_main):
    """Escape/close inside the launcher lands in the app: main() ignores the
    return value and goes on to app.exec(). It must NEVER quit instead."""

    def _cancelled(window, settings, **kwargs):
        return None

    assert main([], launcher=_cancelled) == 0


def test_mcp_returns_before_the_launcher_can_be_reached(monkeypatch, tmp_path):
    """FQ-010's second hard constraint: `--mcp` returns before any Qt import, so
    the launcher is STRUCTURALLY unreachable headlessly. Also proves `args.file`
    survived the GUI-branch deletion — it is still what reaches the server as
    the default project."""
    import pgtp_editor.ui.launcher_dialog as launcher_mod

    monkeypatch.setattr(main_mod.debuglog, "setup", lambda debug: None)

    def _boom(*args, **kwargs):
        raise AssertionError("--mcp must never reach the launcher")

    monkeypatch.setattr(launcher_mod, "show_launcher", _boom)

    pgtp = tmp_path / "proj.pgtp"
    pgtp.write_text("<project/>", encoding="utf-8")
    served = []
    monkeypatch.setattr(
        main_mod, "run_mcp_server", lambda path=None: served.append(path) or 0
    )

    assert main(["--mcp", str(pgtp)]) == 0
    assert served == [str(pgtp)]


def test_mcp_early_return_precedes_every_qt_import_in_main_source():
    """Guards the invariant by source order rather than by behaviour: if anyone
    moves a Qt import (or the launcher) above the `--mcp` return, a GUI would
    contend for the stdio the MCP protocol uses."""
    import inspect

    source = inspect.getsource(main_mod.main)
    mcp_return = source.index("return run_mcp_server(args.file)")
    assert source.index("from PySide6") > mcp_return
    assert source.index("from pgtp_editor.ui import launcher_dialog") > mcp_return


# --- `python -m pgtp_editor` (BUG-260812002307) ------------------------------


def test_module_entry_point_delegates_to_main():
    """`python -m pgtp_editor` used to fail outright ("cannot be directly
    executed"): the package had no `__main__`. It has one now, and it is a pure
    delegation — the SAME `main` the documented `python -m pgtp_editor.main`
    form and any console script run, so the two can never diverge."""
    import pgtp_editor.__main__ as module_entry

    assert module_entry.main is main_mod.main


def test_module_entry_point_is_resolvable_by_runpy(monkeypatch):
    """Resolves as an executable module without launching a GUI: `main` is
    stubbed, so `runpy` proves only that `-m pgtp_editor` finds and runs a
    `__main__` whose exit code comes from `main`."""
    import runpy
    import sys

    monkeypatch.setattr(main_mod, "main", lambda *a, **k: 7)
    sys.modules.pop("pgtp_editor.__main__", None)

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("pgtp_editor", run_name="__main__")

    assert excinfo.value.code == 7
    sys.modules.pop("pgtp_editor.__main__", None)


def test_module_entry_point_adds_no_startup_logic():
    """It must stay a delegation: no argument parsing, no logging setup, no Qt
    of its own, or `-m pgtp_editor` and `pgtp_editor.main` drift apart."""
    import inspect

    import pgtp_editor.__main__ as module_entry

    source = inspect.getsource(module_entry)
    for forbidden in ("parse_args", "argparse", "PySide6", "QApplication", "debuglog"):
        assert forbidden not in source


def test_gui_scripts_console_entry_points_at_the_same_main():
    """The installed `pgtp-editor` command (BUG-260812002307's optional extra).
    `gui-scripts`, not `scripts`, so the Windows launcher is `pythonw` and a Qt
    app started from a shortcut drags no console window along. It names the one
    entry point, like `__main__.py` does — three launch forms, one `main`.

    Asserted as a THIRD delegation rather than a string: an entry point that
    points somewhere else is the drift this guards."""
    import tomllib
    from pathlib import Path

    pyproject = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )
    assert pyproject["project"]["gui-scripts"] == {
        "pgtp-editor": "pgtp_editor.main:main"
    }
    module_path, _, attribute = (
        pyproject["project"]["gui-scripts"]["pgtp-editor"].partition(":")
    )
    module = importlib.import_module(module_path)
    assert getattr(module, attribute) is main_mod.main
