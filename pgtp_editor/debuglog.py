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
