# pgtp_editor/generation/config.py
"""Per-user persistence of the PHP Generator executable path.

Mirrors pgtp_editor/schema_learning/storage.py: a `base_dir` override (used by
tests with a tmp_path) falls back to the OS AppData location. Stored as a small
JSON object {"executable_path": "..."}; load tolerates an absent, unreadable,
malformed, or key-missing file by returning None (never raises).
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QStandardPaths

_CONFIG_FILENAME = "generator_config.json"
_EXECUTABLE_KEY = "executable_path"


def _app_data_dir() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))


def generator_config_path(base_dir: Path | None = None) -> Path:
    return (base_dir or _app_data_dir()) / _CONFIG_FILENAME


def load_executable_path(base_dir: Path | None = None) -> str | None:
    """Return the stored executable path, or None if it cannot be determined
    (file absent / unreadable / not valid JSON / key missing)."""
    path = generator_config_path(base_dir)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get(_EXECUTABLE_KEY)
    return value if isinstance(value, str) else None


def save_executable_path(path: str, base_dir: Path | None = None) -> None:
    """Persist `path` under the executable key, creating the directory and
    preserving any other keys already present in the file."""
    config_path = generator_config_path(base_dir)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {}
    try:
        existing = config_path.read_text(encoding="utf-8")
        loaded = json.loads(existing)
        if isinstance(loaded, dict):
            data = loaded
    except (OSError, ValueError, TypeError):
        data = {}

    data[_EXECUTABLE_KEY] = path
    config_path.write_text(json.dumps(data), encoding="utf-8")
