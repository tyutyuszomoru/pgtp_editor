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
import threading
from datetime import datetime
from pathlib import Path

TRACE = 5
logging.addLevelName(TRACE, "TRACE")

_log = logging.getLogger(__name__)

# Handlers installed by setup(); tracked for teardown().
_installed_handlers: list[logging.Handler] = []
_active = False
_session_path: Path | None = None

_orig_sys_excepthook = None
_orig_threading_excepthook = None
_qt_handler_installed = False


def log_dir() -> Path:
    """Log directory: %LOCALAPPDATA%/MDS/PGTP Editor/logs, or
    ~/.pgtp_editor/logs when LOCALAPPDATA is unset (non-Windows dev)."""
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "MDS" / "PGTP Editor" / "logs"
    return Path.home() / ".pgtp_editor" / "logs"


_FORMAT = "%(asctime)s.%(msecs)03d %(levelname)-5s [%(threadName)s] %(name)s: %(message)s"
_DATEFMT = "%H:%M:%S"


class _SpecFormatter(logging.Formatter):
    """Spec §3 rendering: main thread shortened to ``gui``; logger names
    lose the redundant ``pgtp_editor.`` prefix."""

    def __init__(self) -> None:
        super().__init__(_FORMAT, datefmt=_DATEFMT)
        self._main_ident = threading.main_thread().ident

    def format(self, record: logging.LogRecord) -> str:
        if record.thread == self._main_ident:
            record.threadName = "gui"
        record.name = record.name.removeprefix("pgtp_editor.")
        return super().format(record)


def setup(debug: bool, dir_override: Path | None = None) -> Path | None:
    """Install logging for this process. Returns the debug session file path
    (debug mode) or None. Idempotent: a second call is a no-op.

    A failed log-dir mkdir degrades to a stderr-only handler but still
    installs the crash-path hooks — logging problems must never disable
    crash capture."""
    global _active, _session_path
    if _active:
        return _session_path
    _active = True

    target = dir_override if dir_override is not None else log_dir()
    root = logging.getLogger()
    root.setLevel(TRACE if debug else logging.WARNING)
    formatter = _SpecFormatter()

    stderr_only = False
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        stderr_only = True
        stderr_handler = logging.StreamHandler()
        stderr_handler.setFormatter(formatter)
        root.addHandler(stderr_handler)
        _installed_handlers.append(stderr_handler)
        _log.warning("log dir %s not creatable; logging to stderr only", target)

    if not stderr_only:
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
    _write_session_header(debug, target)
    _install_excepthooks()
    if debug:
        _install_tracer()
    return _session_path


def _app_version() -> str:
    try:
        from importlib.metadata import version

        return version("pgtp_editor")
    except Exception:
        return "unknown"


def _write_session_header(debug: bool, target: Path) -> None:
    _log.log(
        TRACE if debug else logging.WARNING,
        "session start debug=%s app=%s python=%s platform=%s logdir=%s argv=%s",
        debug,
        _app_version(),
        sys.version.split()[0],
        platform.platform(),
        target,
        sys.argv,
    )
    # Qt versions and the settings file path are logged from main() after
    # PySide6 is imported; keeping this header Qt-free lets setup() run
    # before QApplication exists.


def teardown() -> None:
    """Remove everything setup() installed (test isolation)."""
    global _active, _session_path
    global _orig_sys_excepthook, _orig_threading_excepthook, _qt_handler_installed
    _uninstall_tracer()
    root = logging.getLogger()
    for handler in _installed_handlers:
        root.removeHandler(handler)
        handler.close()
    _installed_handlers.clear()
    logging.captureWarnings(False)
    root.setLevel(logging.WARNING)
    _active = False
    _session_path = None

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


# ---------------------------------------------------------------------------
# sys.monitoring auto-tracer
# ---------------------------------------------------------------------------
# _PACKAGE_DIR is resolved once so filename comparisons and relative_to() are
# both against fully-resolved, same-case paths (Windows path-case trap).
_PACKAGE_DIR = Path(__file__).resolve().parent
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
    ("ui.xml_editor", "XmlSyntaxHighlighter."),
    ("ui.xml_editor", "XmlEditor._update_matching_tag_highlight"),
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


def _short_module(filename: str) -> str | None:
    try:
        rel = Path(filename).resolve().relative_to(_PACKAGE_DIR)
    except ValueError:
        # Not under the package dir (or a Windows same-drive/different-case
        # path relative_to() can't reconcile) -- treat as out of scope.
        return None
    return str(rel.with_suffix("")).replace("\\", ".").replace("/", ".")


def _trace_scope(code):
    """Module name for traced code, or None (=> DISABLE) when out of scope."""
    filename = code.co_filename
    if not filename.startswith(str(_PACKAGE_DIR)):
        return None
    module = _short_module(filename)
    if module is None:
        return None
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
        # Returning DISABLE from RAISE is not honored uniformly across
        # point releases (can raise ValueError there) -- just decline to
        # log for out-of-scope code instead of trying to disable the event.
        return None
    indent = "  " * getattr(_depth, "value", 0)
    _trace_log.log(TRACE, "%s! %s.%s %r", indent, module, code.co_qualname, exc)
    return None


def _on_unwind(code, _offset, _exc):
    # PY_RETURN never fires for a frame unwound by an exception; without
    # this, every propagated exception would permanently inflate the
    # per-thread depth. Log nothing -- the RAISE '!' line already marks it.
    # PY_UNWIND is a non-local event: returning DISABLE is not allowed
    # (raises ValueError), so out-of-scope code just returns None.
    if _trace_scope(code) is None:
        return None
    _bump(-1)
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
    mon.register_callback(_TOOL_ID, mon.events.PY_UNWIND, _on_unwind)
    mon.set_events(
        _TOOL_ID,
        mon.events.PY_START
        | mon.events.PY_RETURN
        | mon.events.RAISE
        | mon.events.PY_UNWIND,
    )
    _tracer_installed = True


def _uninstall_tracer() -> None:
    global _tracer_installed
    if not _tracer_installed:
        return
    mon = sys.monitoring
    mon.set_events(_TOOL_ID, 0)
    for event in (
        mon.events.PY_START,
        mon.events.PY_RETURN,
        mon.events.RAISE,
        mon.events.PY_UNWIND,
    ):
        mon.register_callback(_TOOL_ID, event, None)
    mon.free_tool_id(_TOOL_ID)
    _tracer_installed = False
