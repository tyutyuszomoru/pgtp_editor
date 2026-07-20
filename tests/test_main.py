"""--debug activation: CLI flag, env var, setup ordering seam.

Also covers the startup-file argument (the Windows "Edit with PGTP Editor"
right-click verb passes the clicked .pgtp path as argv[1]).
"""
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


# --- startup file argument: main() -----------------------------------------


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

    def show(self):
        self.shown = True

    def open_project_file(self, path):
        self.opened.append(path)


@pytest.fixture
def stub_main(monkeypatch):
    """Neutralise every heavy/modal seam in main() so it runs headless.

    Returns the (single) fake MainWindow instance main() constructs so tests
    can assert on open_project_file calls.
    """
    from PySide6 import QtWidgets

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
    return created


def test_main_opens_existing_file(monkeypatch, tmp_path, stub_main):
    pgtp = tmp_path / "proj.pgtp"
    pgtp.write_text("<project/>", encoding="utf-8")
    monkeypatch.setattr(main_mod.sys, "argv", ["pgtp_editor", str(pgtp)])

    rc = main()

    assert rc == 0
    assert len(stub_main) == 1
    window = stub_main[0]
    assert window.shown is True
    assert window.opened == [str(pgtp)]


def test_main_missing_file_is_ignored_with_warning(
    monkeypatch, tmp_path, stub_main, caplog
):
    missing = tmp_path / "nope.pgtp"  # never created
    monkeypatch.setattr(main_mod.sys, "argv", ["pgtp_editor", str(missing)])

    import logging

    with caplog.at_level(logging.WARNING, logger="pgtp_editor.main"):
        rc = main()

    assert rc == 0
    assert stub_main[0].opened == []
    assert any("startup file not found" in r.message for r in caplog.records)


def test_main_no_file_arg_does_not_open(monkeypatch, stub_main):
    monkeypatch.setattr(main_mod.sys, "argv", ["pgtp_editor"])

    rc = main()

    assert rc == 0
    assert stub_main[0].opened == []


def test_main_directory_path_is_ignored(monkeypatch, tmp_path, stub_main):
    # A directory is not a file: os.path.isfile is False, so no open.
    monkeypatch.setattr(main_mod.sys, "argv", ["pgtp_editor", str(tmp_path)])

    rc = main()

    assert rc == 0
    assert stub_main[0].opened == []
