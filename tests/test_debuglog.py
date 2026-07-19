"""Debug-mode logging core: TRACE level, log dir resolution, handler setup."""
import logging

import pytest

from pgtp_editor import debuglog


@pytest.fixture
def clean_logging(tmp_path):
    """Run setup() against a temp dir and always tear global state back down."""
    yield tmp_path
    debuglog.teardown()


def test_trace_level_registered():
    assert debuglog.TRACE == 5
    assert logging.getLevelName(debuglog.TRACE) == "TRACE"


def test_log_dir_uses_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert debuglog.log_dir() == tmp_path / "MDS" / "PGTP Editor" / "logs"


def test_log_dir_falls_back_to_home(monkeypatch, tmp_path):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(debuglog.Path, "home", staticmethod(lambda: tmp_path))
    assert debuglog.log_dir() == tmp_path / ".pgtp_editor" / "logs"


def test_setup_normal_mode_creates_only_error_handler(clean_logging):
    tmp_path = clean_logging
    debuglog.setup(debug=False, dir_override=tmp_path)
    logging.getLogger("pgtp_editor.test").error("boom-normal")
    assert (tmp_path / "errors.log").is_file()
    assert "boom-normal" in (tmp_path / "errors.log").read_text("utf-8")
    assert not list(tmp_path.glob("debug_*.log"))


def test_setup_normal_mode_error_log_skips_info(clean_logging):
    tmp_path = clean_logging
    debuglog.setup(debug=False, dir_override=tmp_path)
    logging.getLogger("pgtp_editor.test").info("quiet")
    text = (tmp_path / "errors.log").read_text("utf-8") if (
        tmp_path / "errors.log"
    ).is_file() else ""
    assert "quiet" not in text


def test_setup_debug_mode_creates_session_file(clean_logging):
    tmp_path = clean_logging
    debuglog.setup(debug=True, dir_override=tmp_path)
    logging.getLogger("pgtp_editor.test").info("hello-debug")
    files = list(tmp_path.glob("debug_*.log"))
    assert len(files) == 1
    assert "hello-debug" in files[0].read_text("utf-8")


def test_setup_returns_session_path_in_debug(clean_logging):
    tmp_path = clean_logging
    path = debuglog.setup(debug=True, dir_override=tmp_path)
    assert path is not None and path.name.startswith("debug_")


def test_setup_is_idempotent(clean_logging):
    tmp_path = clean_logging
    debuglog.setup(debug=True, dir_override=tmp_path)
    debuglog.setup(debug=True, dir_override=tmp_path)   # second call: no-op
    logging.getLogger("pgtp_editor.test").info("once")
    files = list(tmp_path.glob("debug_*.log"))
    assert len(files) == 1
    assert files[0].read_text("utf-8").count("once") == 1


def test_session_header_written(clean_logging):
    tmp_path = clean_logging
    debuglog.setup(debug=True, dir_override=tmp_path)
    text = next(tmp_path.glob("debug_*.log")).read_text("utf-8")
    assert "session start" in text
    assert "python=" in text


import sys
import threading


def _debug_text(tmp_path):
    return next(tmp_path.glob("debug_*.log")).read_text("utf-8")


@pytest.mark.qt_no_exception_capture
def test_sys_excepthook_logs_traceback(clean_logging):
    tmp_path = clean_logging
    debuglog.setup(debug=True, dir_override=tmp_path)
    try:
        raise ValueError("kaboom-main")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    text = _debug_text(tmp_path)
    assert "kaboom-main" in text and "Traceback" in text
    assert "kaboom-main" in (tmp_path / "errors.log").read_text("utf-8")


def test_threading_excepthook_logs(clean_logging):
    tmp_path = clean_logging
    debuglog.setup(debug=True, dir_override=tmp_path)

    def die():
        raise RuntimeError("kaboom-thread")

    t = threading.Thread(target=die, name="victim")
    t.start()
    t.join()
    text = _debug_text(tmp_path)
    assert "kaboom-thread" in text and "victim" in text


def test_teardown_restores_excepthooks(clean_logging):
    tmp_path = clean_logging
    before_sys, before_thread = sys.excepthook, threading.excepthook
    debuglog.setup(debug=True, dir_override=tmp_path)
    assert sys.excepthook is not before_sys
    debuglog.teardown()
    assert sys.excepthook is before_sys
    assert threading.excepthook is before_thread


def test_qt_message_handler_logs_qwarning(clean_logging, qtbot):
    from PySide6.QtCore import qWarning

    tmp_path = clean_logging
    debuglog.setup(debug=True, dir_override=tmp_path)
    debuglog.install_qt_handler()
    qWarning("qt-says-boo")
    assert "qt-says-boo" in _debug_text(tmp_path)


def test_redacted_hides_password():
    from pgtp_editor.db.config import ConnectionParams

    params = ConnectionParams(
        host="127.0.0.1", port="5432", database="d", user="u", password="s3cret"
    )
    text = debuglog.redacted(params)
    assert "s3cret" not in text
    assert "127.0.0.1" in text and "u" in text and "***" in text


def test_setup_oserror_falls_back_to_stderr_but_keeps_hooks(clean_logging):
    """A failed log-dir mkdir must not disable crash capture."""
    tmp_path = clean_logging
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("file, not dir", encoding="utf-8")
    before_sys = sys.excepthook
    result = debuglog.setup(debug=True, dir_override=blocker / "logs")
    assert result is None
    root = logging.getLogger()
    assert any(
        type(h) is logging.StreamHandler for h in root.handlers
    )
    assert sys.excepthook is not before_sys
    debuglog.teardown()
    assert sys.excepthook is before_sys


def test_main_thread_renders_as_gui(clean_logging):
    tmp_path = clean_logging
    debuglog.setup(debug=True, dir_override=tmp_path)
    logging.getLogger("pgtp_editor.test").info("who-am-i")
    line = next(
        l for l in _debug_text(tmp_path).splitlines() if "who-am-i" in l
    )
    assert "[gui]" in line


def test_worker_thread_keeps_its_name(clean_logging):
    tmp_path = clean_logging
    debuglog.setup(debug=True, dir_override=tmp_path)

    def work():
        logging.getLogger("pgtp_editor.test").info("from-worker")

    t = threading.Thread(target=work, name="pool-7")
    t.start()
    t.join()
    line = next(
        l for l in _debug_text(tmp_path).splitlines() if "from-worker" in l
    )
    assert "[pool-7]" in line


def test_logger_name_drops_package_prefix(clean_logging):
    tmp_path = clean_logging
    debuglog.setup(debug=True, dir_override=tmp_path)
    logging.getLogger("pgtp_editor.ui.test").info("named")
    line = next(l for l in _debug_text(tmp_path).splitlines() if "named" in l)
    assert " ui.test: " in line
    assert "pgtp_editor.ui.test" not in line


def test_session_header_has_version_and_logdir(clean_logging):
    tmp_path = clean_logging
    debuglog.setup(debug=True, dir_override=tmp_path)
    text = _debug_text(tmp_path)
    assert "app=" in text
    assert f"logdir={tmp_path}" in text


def test_exclusion_predicate():
    assert debuglog.is_excluded("pgtp_editor.ui.xml_editor", "XmlEditor.paintEvent")
    assert debuglog.is_excluded(
        "pgtp_editor.ui.xml_editor", "_EditorGutter.paintEvent"
    )
    assert debuglog.is_excluded("pgtp_editor.model.line_index", "anything_at_all")
    assert debuglog.is_excluded(
        "pgtp_editor.ui.xml_editor", "XmlSyntaxHighlighter.highlightBlock"
    )
    assert debuglog.is_excluded(
        "pgtp_editor.ui.xml_editor", "XmlEditor._update_matching_tag_highlight"
    )
    assert not debuglog.is_excluded(
        "pgtp_editor.ui.main_window", "MainWindow.open_project_file"
    )


def test_tracer_logs_traced_package_calls(clean_logging):
    tmp_path = clean_logging
    debuglog.setup(debug=True, dir_override=tmp_path)
    # a real, cheap pgtp_editor function:
    from pgtp_editor.schema_learning.settings_index import attribute_kind

    attribute_kind({"kind": "setting"})
    for h in logging.getLogger().handlers:
        h.flush()
    text = _debug_text(tmp_path)
    assert "> schema_learning.settings_index.attribute_kind" in text
    assert "< schema_learning.settings_index.attribute_kind" in text


def test_tracer_ignores_non_package_code(clean_logging):
    tmp_path = clean_logging
    debuglog.setup(debug=True, dir_override=tmp_path)
    import json

    json.dumps({"x": 1})
    for h in logging.getLogger().handlers:
        h.flush()
    assert "json." not in _debug_text(tmp_path)


def test_tracer_logs_raises(clean_logging):
    tmp_path = clean_logging
    debuglog.setup(debug=True, dir_override=tmp_path)
    from pgtp_editor.ui.xml_editor import insert_attribute

    try:
        insert_attribute(None, 0, "x")   # TypeError inside a traced frame
    except TypeError:
        pass
    for h in logging.getLogger().handlers:
        h.flush()
    assert "! ui.xml_editor.insert_attribute" in _debug_text(tmp_path)


def test_tracer_depth_recovers_after_exception(clean_logging):
    """PY_UNWIND must decrement depth: a propagated exception must not
    permanently indent all subsequent trace lines on that thread."""
    tmp_path = clean_logging
    debuglog.setup(debug=True, dir_override=tmp_path)
    from pgtp_editor.schema_learning.settings_index import attribute_kind
    from pgtp_editor.ui.xml_editor import insert_attribute

    try:
        insert_attribute(None, 0, "x")   # TypeError unwinds the frame
    except TypeError:
        pass
    attribute_kind({"kind": "setting"})
    for h in logging.getLogger().handlers:
        h.flush()
    line = next(
        l
        for l in _debug_text(tmp_path).splitlines()
        if "> schema_learning.settings_index.attribute_kind" in l
    )
    # Depth back at base: the '>' marker directly follows "trace: ".
    assert "trace: > schema_learning.settings_index.attribute_kind" in line


def test_tracer_not_installed_in_normal_mode(clean_logging):
    tmp_path = clean_logging
    debuglog.setup(debug=False, dir_override=tmp_path)
    assert not debuglog.tracer_active()


def test_teardown_uninstalls_tracer(clean_logging):
    tmp_path = clean_logging
    debuglog.setup(debug=True, dir_override=tmp_path)
    assert debuglog.tracer_active()
    debuglog.teardown()
    assert not debuglog.tracer_active()
