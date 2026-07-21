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


_RE_PHPGEN_ROOT_KEY = "re_phpgen_root"
DEFAULT_RE_PHPGEN_ROOT = r"C:\Users\BotondZalai-RuzsicsP\Software dev\re_phpgen"


def load_re_phpgen_root(base_dir: Path | None = None) -> str:
    """Stored re_phpgen repo root, falling back to the machine default."""
    path = generator_config_path(base_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return DEFAULT_RE_PHPGEN_ROOT
    value = data.get(_RE_PHPGEN_ROOT_KEY) if isinstance(data, dict) else None
    return value if isinstance(value, str) and value else DEFAULT_RE_PHPGEN_ROOT


def save_re_phpgen_root(root: str, base_dir: Path | None = None) -> None:
    config_path = generator_config_path(base_dir)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    try:
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    except (OSError, ValueError, TypeError):
        data = {}
    data[_RE_PHPGEN_ROOT_KEY] = root
    config_path.write_text(json.dumps(data), encoding="utf-8")
