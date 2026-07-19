# Debug Mode (`--debug` diagnostic logging) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `python -m pgtp_editor.main --debug` (or `PGTP_EDITOR_DEBUG=1`) produces a per-session full-detail diagnostic log (auto-traced calls + seam events + all crash paths); normal mode always keeps a small rotating error log.

**Architecture:** One new module `pgtp_editor/debuglog.py` owns everything: TRACE level, log directory resolution, handler setup/teardown, excepthooks, Qt message forwarding, the `sys.monitoring` auto-tracer with scope/exclusion filtering, and `redacted()`. `main.py` grows argparse + setup ordering (setup BEFORE QApplication). `main_window.py` gets a DEBUG status chip, Help ▸ Open Log Folder (injectable opener seam), and one-line seam logs at existing methods. No existing function is restructured.

**Tech Stack:** Python 3.13 stdlib `logging` + `sys.monitoring` (PROFILER_ID), PySide6 `qInstallMessageHandler`. Tests: pytest + pytest-qt, offscreen. Spec: `docs/superpowers/specs/2026-07-19-pgtp-editor-debug-mode-design.md`.

**Test isolation rule (critical):** `debuglog.setup()` mutates process-global state (root handlers, `sys.excepthook`, `threading.excepthook`, `sys.monitoring` tool slot, Qt handler). Every test that calls `setup()` MUST call `debuglog.teardown()` in a `finally`/fixture, and MUST pass `dir_override=tmp_path`. Never let it leak into the other ~1290 tests.

---

### Task 1: `debuglog` core — TRACE level, `log_dir()`, `setup()`/`teardown()` handlers

**Files:**
- Create: `pgtp_editor/debuglog.py`
- Test: `tests/test_debuglog.py` (repo has no `pgtp_editor/debuglog` subpackage — module sits at package root, so the test mirrors at tests root)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_debuglog.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_debuglog.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pgtp_editor.debuglog'`.

- [ ] **Step 3: Write `pgtp_editor/debuglog.py` (core only — hooks/tracer come in Tasks 2-3)**

```python
"""Diagnostic logging for the app (spec: 2026-07-19-pgtp-editor-debug-mode).

Two modes, both owned by :func:`setup`:

- normal: a small rotating ``errors.log`` (WARNING+) — always on, so a crash
  outside a debug session still leaves evidence.
- debug (``--debug`` / ``PGTP_EDITOR_DEBUG=1``): adds a per-session
  ``debug_YYYYMMDD_HHMMSS.log`` at TRACE level, the sys.monitoring
  auto-tracer over pgtp_editor frames, and full crash-path hooks.

Logging must never crash the app: directory-creation failures fall back to
stderr-only; tracer-slot conflicts degrade to seam+error logging with one
WARNING. Import has no side effects — nothing installs until setup().
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import platform
import sys
from datetime import datetime
from pathlib import Path

TRACE = 5
logging.addLevelName(TRACE, "TRACE")

_log = logging.getLogger(__name__)

# Handlers installed by setup(); tracked for teardown().
_installed_handlers: list[logging.Handler] = []
_active = False
_session_path: Path | None = None


def log_dir() -> Path:
    """Log directory: %LOCALAPPDATA%/MDS/PGTP Editor/logs, or
    ~/.pgtp_editor/logs when LOCALAPPDATA is unset (non-Windows dev)."""
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "MDS" / "PGTP Editor" / "logs"
    return Path.home() / ".pgtp_editor" / "logs"


_FORMAT = "%(asctime)s.%(msecs)03d %(levelname)-5s [%(threadName)s] %(name)s: %(message)s"
_DATEFMT = "%H:%M:%S"


def setup(debug: bool, dir_override: Path | None = None) -> Path | None:
    """Install logging for this process. Returns the debug session file path
    (debug mode) or None. Idempotent: a second call is a no-op."""
    global _active, _session_path
    if _active:
        return _session_path
    _active = True

    target = dir_override if dir_override is not None else log_dir()
    root = logging.getLogger()
    root.setLevel(TRACE if debug else logging.WARNING)
    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        stderr_handler = logging.StreamHandler()
        stderr_handler.setFormatter(formatter)
        root.addHandler(stderr_handler)
        _installed_handlers.append(stderr_handler)
        _log.warning("log dir %s not creatable; logging to stderr only", target)
        return None

    error_handler = logging.handlers.RotatingFileHandler(
        target / "errors.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
        delay=True,
    )
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(formatter)
    root.addHandler(error_handler)
    _installed_handlers.append(error_handler)

    if debug:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        _session_path = target / f"debug_{stamp}.log"
        debug_handler = logging.FileHandler(
            _session_path, encoding="utf-8", delay=True
        )
        debug_handler.setLevel(TRACE)
        debug_handler.setFormatter(formatter)
        root.addHandler(debug_handler)
        _installed_handlers.append(debug_handler)

    logging.captureWarnings(True)
    _write_session_header(debug)
    return _session_path


def _write_session_header(debug: bool) -> None:
    _log.log(
        TRACE if debug else logging.WARNING,
        "session start debug=%s python=%s platform=%s argv=%s",
        debug,
        sys.version.split()[0],
        platform.platform(),
        sys.argv,
    )
    # Qt versions are logged from main() after PySide6 is imported; keeping
    # this header Qt-free lets setup() run before QApplication exists.


def teardown() -> None:
    """Remove everything setup() installed (test isolation)."""
    global _active, _session_path
    root = logging.getLogger()
    for handler in _installed_handlers:
        root.removeHandler(handler)
        handler.close()
    _installed_handlers.clear()
    logging.captureWarnings(False)
    root.setLevel(logging.WARNING)
    _active = False
    _session_path = None
```

Note: the session-start header uses WARNING level in normal mode deliberately — the spec wants the header at the top of *every* log session, and `errors.log` only accepts WARNING+. Tasks 2-3 extend `setup()`/`teardown()` with hooks and the tracer.

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_debuglog.py -q`
Expected: PASS (9 passed).

- [ ] **Step 5: Run the FULL suite to prove no leakage**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q`
Expected: same pass count as baseline + 9 new, 0 failures. If any unrelated test now writes log files or shows handler noise, the teardown fixture has a gap — fix it before committing.

- [ ] **Step 6: Commit**

```powershell
git add pgtp_editor/debuglog.py tests/test_debuglog.py
git commit -m "feat: debuglog core (TRACE level, log dir, error/session handlers)"
```

---

### Task 2: Crash-path hooks — excepthooks + Qt message handler + `redacted()`

**Files:**
- Modify: `pgtp_editor/debuglog.py`
- Test: `tests/test_debuglog.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_debuglog.py`:

```python
import sys
import threading


def _debug_text(tmp_path):
    return next(tmp_path.glob("debug_*.log")).read_text("utf-8")


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
```

(`qtbot` in the Qt test guarantees a QApplication exists offscreen; `install_qt_handler` is separate from `setup()` because `main.py` calls setup before Qt is up, then installs the Qt handler after.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_debuglog.py -q`
Expected: new tests FAIL (`AttributeError: ... has no attribute 'install_qt_handler'` / hooks not replaced / `redacted` missing).

- [ ] **Step 3: Implement in `debuglog.py`**

Add module state and functions; wire into `setup()`/`teardown()`:

```python
import threading

_orig_sys_excepthook = None
_orig_threading_excepthook = None
_qt_handler_installed = False


def _log_uncaught(exc_type, exc, tb) -> None:
    _log.error(
        "uncaught exception", exc_info=(exc_type, exc, tb)
    )


def _sys_hook(exc_type, exc, tb) -> None:
    _log_uncaught(exc_type, exc, tb)
    if _orig_sys_excepthook is not None:
        _orig_sys_excepthook(exc_type, exc, tb)


def _threading_hook(args) -> None:
    _log.error(
        "uncaught exception in thread %r",
        args.thread.name if args.thread else "?",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )
    if _orig_threading_excepthook is not None:
        _orig_threading_excepthook(args)


def _install_excepthooks() -> None:
    global _orig_sys_excepthook, _orig_threading_excepthook
    _orig_sys_excepthook = sys.excepthook
    _orig_threading_excepthook = threading.excepthook
    sys.excepthook = _sys_hook
    threading.excepthook = _threading_hook


def install_qt_handler() -> None:
    """Forward Qt's own messages into logging. Called from main() after
    PySide6 is importable (setup() itself must stay Qt-free)."""
    global _qt_handler_installed
    if _qt_handler_installed:
        return
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def handler(msg_type, context, message):
        logging.getLogger("qt").log(levels.get(msg_type, logging.WARNING), "%s", message)

    qInstallMessageHandler(handler)
    _qt_handler_installed = True


def redacted(params) -> str:
    """One-line rendering of ConnectionParams with the password blanked.
    THE seam-log formatter for connection info — never log params directly."""
    return (
        f"host={params.host} port={params.port} "
        f"database={params.database} user={params.user} password=***"
    )
```

In `setup()`, after handler installation add `_install_excepthooks()`. In `teardown()` restore:

```python
    global _orig_sys_excepthook, _orig_threading_excepthook, _qt_handler_installed
    if _orig_sys_excepthook is not None:
        sys.excepthook = _orig_sys_excepthook
        _orig_sys_excepthook = None
    if _orig_threading_excepthook is not None:
        threading.excepthook = _orig_threading_excepthook
        _orig_threading_excepthook = None
    if _qt_handler_installed:
        from PySide6.QtCore import qInstallMessageHandler

        qInstallMessageHandler(None)
        _qt_handler_installed = False
```

(PySide6 routes unhandled slot exceptions through `sys.excepthook`, so the Qt-slot crash path is covered by `_sys_hook` — no extra hook needed.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_debuglog.py -q`
Expected: PASS (14 passed).

- [ ] **Step 5: Commit**

```powershell
git add pgtp_editor/debuglog.py tests/test_debuglog.py
git commit -m "feat: crash-path hooks (sys/threading/Qt) + password redaction"
```

---

### Task 3: Auto-tracer (`sys.monitoring`)

**Files:**
- Modify: `pgtp_editor/debuglog.py`
- Test: `tests/test_debuglog.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_debuglog.py`:

```python
def test_exclusion_predicate():
    assert debuglog.is_excluded("pgtp_editor.ui.xml_editor", "XmlEditor.paintEvent")
    assert debuglog.is_excluded(
        "pgtp_editor.ui.xml_editor", "_EditorGutter.paintEvent"
    )
    assert debuglog.is_excluded("pgtp_editor.model.line_index", "anything_at_all")
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_debuglog.py -q`
Expected: new tests FAIL (`is_excluded`/`tracer_active` missing; no TRACE lines).

- [ ] **Step 3: Implement the tracer in `debuglog.py`**

```python
_PACKAGE_DIR = str(Path(__file__).resolve().parent)   # .../pgtp_editor
_TOOL_ID = sys.monitoring.PROFILER_ID
_tracer_installed = False
_depth = threading.local()

# (module suffix, qualname prefix) pairs silenced as flooding hot paths.
# "" qualname prefix = the whole module. Extend as flooding is observed.
_EXCLUSIONS: list[tuple[str, str]] = [
    ("ui.xml_editor", "XmlEditor.paintEvent"),
    ("ui.xml_editor", "_EditorGutter."),
    ("ui.xml_editor", "XmlEditor._draw_"),
    ("ui.xml_editor", "XmlEditor.line_number_area"),
    ("ui.xml_editor", "XmlEditor.blockCount"),
    ("ui.xml_editor", "XmlEditor.updateRequest"),
    ("ui.xml_editor", "XmlEditor.eventFilter"),
    ("ui.xml_editor", "XmlHighlighter."),
    ("model.line_index", ""),
]


def is_excluded(module: str, qualname: str) -> bool:
    """True when (module, qualname) matches the hot-path exclusion list."""
    for mod_suffix, qual_prefix in _EXCLUSIONS:
        if module.endswith(mod_suffix) and qualname.startswith(qual_prefix):
            return True
    return False


def tracer_active() -> bool:
    return _tracer_installed


def _short_module(filename: str) -> str:
    rel = Path(filename).resolve().relative_to(_PACKAGE_DIR)
    return str(rel.with_suffix("")).replace("\\", ".").replace("/", ".")


def _trace_scope(code):
    """Module name for traced code, or None (=> DISABLE) when out of scope."""
    filename = code.co_filename
    if not filename.startswith(_PACKAGE_DIR):
        return None
    module = _short_module(filename)
    if is_excluded(module, code.co_qualname):
        return None
    return module


def _bump(delta: int) -> int:
    depth = getattr(_depth, "value", 0)
    if delta > 0:
        _depth.value = depth + delta
        return depth
    _depth.value = max(0, depth + delta)
    return _depth.value


_trace_log = logging.getLogger("trace")


def _on_start(code, _offset):
    module = _trace_scope(code)
    if module is None:
        return sys.monitoring.DISABLE
    indent = "  " * _bump(+1)
    _trace_log.log(
        TRACE, "%s> %s.%s :%d", indent, module, code.co_qualname, code.co_firstlineno
    )
    return None


def _on_return(code, _offset, _retval):
    module = _trace_scope(code)
    if module is None:
        return sys.monitoring.DISABLE
    indent = "  " * _bump(-1)
    _trace_log.log(TRACE, "%s< %s.%s", indent, module, code.co_qualname)
    return None


def _on_raise(code, _offset, exc):
    module = _trace_scope(code)
    if module is None:
        return sys.monitoring.DISABLE
    indent = "  " * getattr(_depth, "value", 0)
    _trace_log.log(TRACE, "%s! %s.%s %r", indent, module, code.co_qualname, exc)
    return None


def _install_tracer() -> None:
    global _tracer_installed
    mon = sys.monitoring
    try:
        mon.use_tool_id(_TOOL_ID, "pgtp_editor_debug")
    except ValueError:
        _log.warning("sys.monitoring profiler slot busy; call tracing disabled")
        return
    mon.register_callback(_TOOL_ID, mon.events.PY_START, _on_start)
    mon.register_callback(_TOOL_ID, mon.events.PY_RETURN, _on_return)
    mon.register_callback(_TOOL_ID, mon.events.RAISE, _on_raise)
    mon.set_events(
        _TOOL_ID,
        mon.events.PY_START | mon.events.PY_RETURN | mon.events.RAISE,
    )
    _tracer_installed = True


def _uninstall_tracer() -> None:
    global _tracer_installed
    if not _tracer_installed:
        return
    mon = sys.monitoring
    mon.set_events(_TOOL_ID, 0)
    for event in (mon.events.PY_START, mon.events.PY_RETURN, mon.events.RAISE):
        mon.register_callback(_TOOL_ID, event, None)
    mon.free_tool_id(_TOOL_ID)
    _tracer_installed = False
```

Wire: `setup(debug=True)` calls `_install_tracer()` last; `teardown()` calls `_uninstall_tracer()` first. IMPORTANT implementation notes for the executor:
- `sys.monitoring.DISABLE` returned from a callback disables that event *for that code object* — this is what keeps steady-state overhead near zero for stdlib/Qt frames. `RAISE` events do **not** honor per-code DISABLE the same way as local events in all point versions — if returning DISABLE from `_on_raise` raises a `ValueError` on 3.13, drop the return there (just return None for out-of-scope) and note it in a comment.
- `_short_module` may raise `ValueError` on `relative_to` for same-drive-different-case paths on Windows; `Path(...).resolve()` on both sides (done above for `_PACKAGE_DIR`) prevents it. If a stray non-resolving path appears, treat as out-of-scope (wrap in try/except returning None).
- After `pytest` runs with `-p no:cacheprovider` or coverage tools that use `sys.monitoring`, the PROFILER_ID slot can be occupied — the graceful `ValueError` path above covers it; `test_tracer_*` tests would then fail, so run them WITHOUT coverage plugins (default repo config has none).

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_debuglog.py -q`
Expected: PASS (20 passed).

- [ ] **Step 5: Full suite (leak check again — the tracer MUST not survive teardown)**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q`
Expected: baseline + 20, 0 failures, no visible slowdown.

- [ ] **Step 6: Commit**

```powershell
git add pgtp_editor/debuglog.py tests/test_debuglog.py
git commit -m "feat: sys.monitoring auto-tracer with scope + hot-path exclusions"
```

---

### Task 4: `main.py` — argparse, env var, setup ordering

**Files:**
- Modify: `pgtp_editor/main.py`
- Test: `tests/test_main.py` (create if absent; check first — if a main test exists, extend it)

- [ ] **Step 1: Write the failing tests**

```python
"""--debug activation: CLI flag, env var, setup ordering seam."""
from pgtp_editor.main import parse_args


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_main.py -q`
Expected: FAIL — `ImportError: cannot import name 'parse_args'`.

- [ ] **Step 3: Rewrite `pgtp_editor/main.py`**

```python
import argparse
import logging
import os
import sys

from pgtp_editor import debuglog


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="pgtp_editor")
    parser.add_argument(
        "--debug",
        action="store_true",
        default=os.environ.get("PGTP_EDITOR_DEBUG", "") not in ("", "0"),
        help="write a full-detail diagnostic log for this session",
    )
    return parser.parse_args(argv)


def main():
    args = parse_args(sys.argv[1:])
    session_path = debuglog.setup(debug=args.debug)

    # Qt imports AFTER setup so even import-time crashes are logged.
    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import qVersion
    from PySide6.QtWidgets import QApplication

    debuglog.install_qt_handler()
    logging.getLogger(__name__).log(
        debuglog.TRACE if args.debug else logging.WARNING,
        "qt versions pyside=%s qt=%s", pyside_version, qVersion(),
    )

    app = QApplication(sys.argv)

    from pgtp_editor.ui.main_window import MainWindow

    window = MainWindow(debug_log_path=session_path)
    window.show()
    if session_path is not None:
        print(f"DEBUG logging -> {session_path}", file=sys.stderr)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

`MainWindow(debug_log_path=...)` requires Task 5's constructor parameter — implement Tasks 4 and 5 back-to-back, running only `tests/test_main.py` between them (full suite after Task 5).

- [ ] **Step 4: Run the new tests**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_main.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit (combined with Task 5 if the constructor change is required to keep the suite green — otherwise commit now)**

```powershell
git add pgtp_editor/main.py tests/test_main.py
git commit -m "feat: --debug flag + env var; debuglog setup before Qt"
```

---

### Task 5: MainWindow — DEBUG chip, Help ▸ Open Log Folder, startup message

**Files:**
- Modify: `pgtp_editor/ui/main_window.py`
- Test: `tests/ui/test_main_window_debug.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
"""Debug-mode UI surface: status chip, Help > Open Log Folder."""
from pgtp_editor.ui.main_window import MainWindow


def _help_action(window, text):
    help_menu = [m for m in window.menuBar().findChildren(type(window.menuBar()))]
    for action in window.menuBar().actions():
        if action.text() == "Help":
            for sub in action.menu().actions():
                if sub.text() == text:
                    return sub
    return None


def test_no_debug_chip_by_default(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window._debug_label is None


def test_debug_chip_when_path_given(qtbot, tmp_path):
    log = tmp_path / "debug_x.log"
    window = MainWindow(debug_log_path=log)
    qtbot.addWidget(window)
    assert window._debug_label is not None
    assert window._debug_label.text() == "DEBUG"


def test_open_log_folder_uses_opener_seam(qtbot, tmp_path, monkeypatch):
    opened = []
    window = MainWindow()
    qtbot.addWidget(window)
    window._open_log_folder(opener=lambda url: opened.append(url))
    assert len(opened) == 1


def test_help_menu_has_open_log_folder(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    action = _help_action(window, "Open Log Folder")
    assert action is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui/test_main_window_debug.py -q`
Expected: FAIL — `TypeError: MainWindow.__init__() got an unexpected keyword argument` / missing attributes.

- [ ] **Step 3: Implement in `main_window.py`**

(a) Constructor: add keyword-only parameter `debug_log_path=None`; store `self._debug_log_path = debug_log_path`; initialize `self._debug_label = None`. After the existing status-bar setup (near the `_mode_label` permanent widget at line ~275), add:

```python
        if self._debug_log_path is not None:
            self._debug_label = QLabel("DEBUG")
            self._debug_label.setStyleSheet(
                "QLabel { color: white; background: #b33; padding: 1px 6px;"
                " border-radius: 3px; font-weight: bold; }"
            )
            self.statusBar().addPermanentWidget(self._debug_label)
            self.statusBar().showMessage(
                f"Debug logging: {self._debug_log_path}", 10000
            )
```

(`QLabel` is already imported by main_window; verify, else extend the import.)

(b) In `_build_help_menu` (line ~2048), after the Manual action and before About:

```python
        logs_action = menu.addAction("Open Log Folder")
        logs_action.triggered.connect(self._open_log_folder)
```

(c) Add the method (near the other Help handlers):

```python
    def _open_log_folder(self, checked=False, opener=None) -> None:
        """Open the diagnostic log directory in the system file browser.
        ``opener`` is an injectable seam so tests never spawn Explorer."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from pgtp_editor import debuglog

        target = debuglog.log_dir()
        target.mkdir(parents=True, exist_ok=True)
        open_fn = opener if opener is not None else QDesktopServices.openUrl
        open_fn(QUrl.fromLocalFile(str(target)))
```

(`triggered` passes `checked` as first positional arg — keep the signature as shown.)

- [ ] **Step 4: Run the tests + the main-window regression files**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui/test_main_window_debug.py tests/ui/test_main_window.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add pgtp_editor/ui/main_window.py tests/ui/test_main_window_debug.py pgtp_editor/main.py tests/test_main.py
git commit -m "feat: DEBUG status chip + Help > Open Log Folder + --debug wiring"
```

---

### Task 6: Seam logs

**Files:**
- Modify: `pgtp_editor/ui/main_window.py` (most seams), `pgtp_editor/generation/runner.py`, `pgtp_editor/db/introspect.py`
- Test: `tests/ui/test_main_window_debug.py` (seam smoke), `tests/db/test_introspect.py` (redaction use)

Each seam is ONE added `logging` line at an existing method — no restructuring. Add `import logging` + `_log = logging.getLogger(__name__)` at module top where missing.

- [ ] **Step 1: Write the failing seam smoke tests**

Append to `tests/ui/test_main_window_debug.py`:

```python
import logging


def test_open_project_file_logs_seam(qtbot, tmp_path, caplog):
    window = MainWindow()
    qtbot.addWidget(window)
    project = tmp_path / "p.pgtp"
    project.write_text(
        '<?xml version="1.0" encoding="UTF-8"?><Project/>', encoding="utf-8"
    )
    with caplog.at_level(logging.INFO, logger="pgtp_editor.ui.main_window"):
        window.open_project_file(project)
    assert any("file: open" in r.message for r in caplog.records)


def test_save_logs_seam(qtbot, tmp_path, caplog):
    window = MainWindow()
    qtbot.addWidget(window)
    project = tmp_path / "p.pgtp"
    project.write_text(
        '<?xml version="1.0" encoding="UTF-8"?><Project/>', encoding="utf-8"
    )
    window.open_project_file(project)
    with caplog.at_level(logging.INFO, logger="pgtp_editor.ui.main_window"):
        window._write_project_text(project)
    assert any("file: save" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run to verify they fail**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui/test_main_window_debug.py -q`
Expected: the two new tests FAIL (no log records).

- [ ] **Step 3: Add the seam lines**

In `main_window.py` (exact wording so tests match — `_log.info(...)` at the START of each listed method unless stated):

| Method (line as of merge 206e01a) | Line to add |
|---|---|
| `open_project_file` (~712) | `_log.info("file: open %s", path)` |
| `_write_project_text` (~1138) | `_log.info("file: save %s", path)` |
| `_close_project` | `_log.info("file: close")` |
| revert handler (`_revert_project` or equivalent — locate by "Revert") | `_log.info("file: revert %s", path)` |
| `_run_db_check` (~1790) | `_log.info("db: check %s started %s", direction, debuglog.redacted(params))` — placed where `params` is resolved; import `from pgtp_editor import debuglog` |
| DB check result callback | `_log.info("db: check %s finished", direction)` |
| `_on_db_rename_requested` | `_log.info("db: rename %s -> %s", old, new)` (use the method's real variable names) |
| `_generate_php` (~1965) | `_log.info("generate: started")`, and where the runner result returns, `_log.info("generate: rc=%s", rc)` (adapt to the actual callback variable) |
| undo/redo (`_undo`/`_redo`) | `_log.info("history: undo")` / `_log.info("history: redo")` |
| schema enrich completion (locate the enrich-finished handler) | `_log.info("schema: enriched %s", path)` |

In `generation/runner.py`: log the full command list + cwd at INFO before spawn, and the return code after.
In `db/introspect.py`: in `fetch_schema`/`test_connection`, log start at INFO **using `debuglog.redacted(params)`** — never the raw params — and the duration + table count on completion.

The executor adapts variable names to the real code at each site (read the method before editing); the log MESSAGE prefixes above are fixed (tests grep them).

- [ ] **Step 4: Run the seam tests + regressions, then full suite**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui/test_main_window_debug.py tests/ui/test_main_window.py tests/db -q`
Then: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q`
Expected: all green (baseline + all new tests).

- [ ] **Step 5: Commit**

```powershell
git add -A
git commit -m "feat: seam logs at file/db/generation/history/schema boundaries"
```

---

### Task 7: Manual note + feature-tester gate

**Files:**
- Modify: `pgtp_editor/resources/manual.md`

- [ ] **Step 1: Add a "Troubleshooting" section to the manual**

Append (or extend an existing troubleshooting section if present) in `manual.md`:

```markdown
## Troubleshooting: debug mode

Launch the editor with `python -m pgtp_editor.main --debug` (or set the
environment variable `PGTP_EDITOR_DEBUG=1`) to record a full diagnostic log
of the session. A red **DEBUG** badge appears in the status bar and the log
file path is shown at startup. Even without debug mode, errors are always
recorded to a small `errors.log`. **Help ▸ Open Log Folder** opens the folder
containing both logs — attach the newest `debug_*.log` when reporting a
problem.
```

Run the manual tests: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui/test_manual_resource.py tests/ui/test_manual_panel.py -q` — expected PASS.

- [ ] **Step 2: Manual smoke of the real app**

Run: `python -m pgtp_editor.main --debug` from the worktree; open a `.pgtp`; confirm the DEBUG chip, then close. Open the newest `debug_*.log`: verify the session header, seam lines for the open, and TRACE call lines are present, and that the file size for a short session is sane (< a few MB — if it flooded, extend `_EXCLUSIONS` for the offending qualnames and add them to `test_exclusion_predicate`).

- [ ] **Step 3: Dispatch the feature-tester agent (project testing policy)**

Per CLAUDE.md, run the `feature-tester` agent with: feature name "Debug mode (--debug diagnostic logging)", spec `docs/superpowers/specs/2026-07-19-pgtp-editor-debug-mode-design.md`, plan (this file), changed files (`pgtp_editor/debuglog.py`, `pgtp_editor/main.py`, `pgtp_editor/ui/main_window.py`, `pgtp_editor/generation/runner.py`, `pgtp_editor/db/introspect.py`, `pgtp_editor/resources/manual.md`). It appends the green run to `docs/TEST_LOG.md`; commit that with the feature.

- [ ] **Step 4: Final commit**

```powershell
git add pgtp_editor/resources/manual.md docs/TEST_LOG.md
git commit -m "docs: manual troubleshooting section for --debug; test log entry"
```

---

## Verification (whole plan)

`$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q` — baseline (1299 on main checkout with samples / 1267+32skip in a worktree) plus ~30 new tests, 0 failures. Manual smoke per Task 7 Step 2 done. Then two-stage review and `--no-ff` merge per the standing workflow.

## Self-review notes

- **Spec coverage:** §1 activation/files → Tasks 1+4+5; §2 always-on capture → Tasks 1-2; §2 auto-trace → Task 3; §2 seam logs + redaction → Tasks 2+6; §3 format → Task 1 `_FORMAT`; §4 module boundaries → matches; §5 failure safety → Task 1 (dir fallback) + Task 3 (tool-slot fallback); §6 testing → every listed test present; §7 delivery → Task 7 + workflow.
- **Known judgment points for the executor:** exact seam variable names (Task 6 table says adapt, message prefixes fixed); RAISE/DISABLE nuance and Windows path-case in Task 3 notes; `QLabel` import check in Task 5.
- **Type consistency:** `setup(debug, dir_override) -> Path | None`; `MainWindow(debug_log_path: Path | None)`; `redacted(params) -> str`; `is_excluded(module, qualname) -> bool` — used identically across tasks.
