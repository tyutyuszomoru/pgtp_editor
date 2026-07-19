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
