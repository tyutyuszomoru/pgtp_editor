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

# pgtp_editor/lint/config.py
"""Per-user persistence of the PHP **linter** executable path (spec §22).

§22 asks for "the same pattern as `generation/config.py`'s `executable_path`
(§19): a new `lint_executable_path` key". Taken literally: this module reuses
`generation.config.generator_config_path` -- the SAME `generator_config.json`
in the SAME AppData directory, with the SAME injectable `base_dir` override --
and only adds a key. It does not invent a second config file, a second AppData
folder or a second load/save idiom; a user who has already located their tools
should find them all in one place, and a test that passes `tmp_path` should
redirect all of them at once.

`save_*` preserves every other key already in the file (`executable_path`,
`re_phpgen_root`), so locating the linter can never wipe the generator path --
the two features share one JSON object and a clobbering write would silently
un-configure §19.

`load_lint_executable_path` tolerates an absent / unreadable / malformed /
key-missing file by returning None and never raising: an unconfigured linter is
an ordinary state (§22 is advisory-only), not an error worth an exception.
"""
from __future__ import annotations

import json
from pathlib import Path

from pgtp_editor.generation.config import generator_config_path

_LINT_EXECUTABLE_KEY = "lint_executable_path"


def lint_config_path(base_dir: Path | None = None) -> Path:
    """The backing file -- deliberately the very same one §19 writes."""
    return generator_config_path(base_dir)


def load_lint_executable_path(base_dir: Path | None = None) -> str | None:
    """Return the stored linter path, or None if it cannot be determined
    (file absent / unreadable / not valid JSON / key missing)."""
    path = lint_config_path(base_dir)
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
    value = data.get(_LINT_EXECUTABLE_KEY)
    return value if isinstance(value, str) and value else None


def save_lint_executable_path(path: str, base_dir: Path | None = None) -> None:
    """Persist `path` under `lint_executable_path`, creating the directory and
    preserving any other keys already present in the file."""
    config_path = lint_config_path(base_dir)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {}
    try:
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    except (OSError, ValueError, TypeError):
        data = {}

    data[_LINT_EXECUTABLE_KEY] = path
    config_path.write_text(json.dumps(data), encoding="utf-8")
