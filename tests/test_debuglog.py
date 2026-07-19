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
