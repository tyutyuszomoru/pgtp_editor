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

# pgtp_editor/version.py
"""The **one importable app version** (`FQ-260810164455`).

**`pyproject.toml`'s `[project] version` line is the single literal.** Nothing
else in the tree may spell the app's version out; this module's whole reason to
exist is that there is exactly one place to edit on a release bump. `docs/
installer.iss` already scans that same literal line at compile time (and
`#pragma error`s if it cannot find it), so the installer and this module read the
*same* fact by two mechanisms rather than two facts.

**Bump rule: edit `pyproject.toml` only.** `version.py` and the installer follow.

**FIVE version numbers exist in this project and only one of them is this one.**
They are listed here because three of them now render in the same About box, and
`0.4.0` sitting two lines from `22.8` with neither labelled is exactly how they
got conflated once already:

* `pyproject.toml` `[project] version` — **the app release. This module.**
* `mcp/server.py` `SERVER_VERSION` — the MCP tool surface, **intentionally
  decoupled by owner ruling.** Do not "fix" it into this module; it versions a
  protocol surface that moves on its own schedule.
* `schema_learning/storage.py` `CURATED_BUNDLED_VERSION` — the curated schema's
  *content*.
* `about.py`'s `22.8` — the **vendor** `.pgtp` project-format version this editor
  targets. Not ours at all.
* `db/schema_snapshot.py` `SNAPSHOT_VERSION` — the snapshot *payload format*, an
  on-disk compatibility integer.

Resolution order, and why it is this order rather than the reverse
------------------------------------------------------------------
1. **`pyproject.toml`, when it sits beside the installed package** — i.e. a
   source or editable checkout, which is every development run.
2. **`importlib.metadata.version("pgtp-editor")`** — a real installed wheel, and
   a frozen build (see below).
3. `UNKNOWN_VERSION`.

Package metadata is a **snapshot of the pyproject literal taken at install
time**, so in an editable checkout it goes stale the moment the literal is bumped
without a reinstall — measured, not hypothetical: this repo's own venv reported
`0.3.0` while `pyproject.toml` said `0.4.0`. Asking metadata first would
therefore have shipped a *wrong* version in the one environment where the answer
is checkable, which is worse than the drift the feature exists to kill. Reading
the literal when the literal is reachable, and the install-time snapshot of it
only when it is not, always yields the fresher copy of the **same single value** —
and it is still **no second literal anywhere**.

The frozen (PyInstaller) case — the one genuine ambiguity, decided
-----------------------------------------------------------------
A frozen build ships neither `pyproject.toml` nor, by default, package metadata,
so branch 1 and branch 2 would *both* miss and the About box would read
"unknown". A hardcoded literal default was rejected: it is precisely the second
copy this feature exists to remove, and it would drift silently and look right
while doing it. Instead the build is made to satisfy branch 2:
`optimized_build.py` passes PyInstaller `--copy-metadata pgtp-editor`, so the
distribution's metadata travels into the bundle and the frozen app resolves its
version through the same `importlib.metadata` path an installed wheel does.
`UNKNOWN_VERSION` is what remains for the genuinely unanswerable case — an
honest "I do not know" rather than a plausible lie.
"""
from __future__ import annotations

import re
from pathlib import Path

__all__ = ["UNKNOWN_VERSION", "DISTRIBUTION_NAME", "app_version", "__version__"]

#: What a version that cannot be determined reads as. Deliberately **not** a
#: version number: a sentinel cannot be mistaken for a release, and cannot drift.
UNKNOWN_VERSION = "unknown"

#: The distribution name in `pyproject.toml` (`[project] name`). Hyphenated —
#: the import package is `pgtp_editor`, the distribution is `pgtp-editor`.
DISTRIBUTION_NAME = "pgtp-editor"

_PROJECT_TABLE = re.compile(r"^\[project\]\s*$", re.MULTILINE)
_NEXT_TABLE = re.compile(r"^\[", re.MULTILINE)
_VERSION_LINE = re.compile(r"^version\s*=\s*[\"']([^\"']+)[\"']", re.MULTILINE)
_NAME_LINE = re.compile(r"^name\s*=\s*[\"']([^\"']+)[\"']", re.MULTILINE)


def _project_table(text: str) -> str | None:
    """The `[project]` table's body, so a `version =` belonging to some other
    table can never be mistaken for the app's."""
    start = _PROJECT_TABLE.search(text)
    if start is None:
        return None
    body = text[start.end() :]
    following = _NEXT_TABLE.search(body)
    return body if following is None else body[: following.start()]


def _pyproject_path() -> Path:
    """Where the checkout's `pyproject.toml` sits relative to this file:
    `<root>/pyproject.toml` next to `<root>/pgtp_editor/version.py`. Only that
    one location is consulted — walking upward could pick up an unrelated
    project's file in a nested layout."""
    return Path(__file__).resolve().parent.parent / "pyproject.toml"


def _pyproject_version() -> str | None:
    """The literal, read straight out of `[project] version` — the same line
    `installer.iss` scans. Returns None when the file is absent (installed wheel,
    frozen bundle) or does not describe *this* distribution."""
    path = _pyproject_path()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    table = _project_table(text)
    if table is None:
        return None
    name = _NAME_LINE.search(table)
    if name is None or name.group(1).strip() != DISTRIBUTION_NAME:
        # Some other project's pyproject.toml happens to sit there. Reading its
        # version would be worse than not answering.
        return None
    found = _VERSION_LINE.search(table)
    if found is None:
        return None
    return found.group(1).strip() or None


def _metadata_version() -> str | None:
    """The install-time snapshot of the literal. Answers for a real installed
    wheel and — thanks to `--copy-metadata` in `optimized_build.py` — for the
    frozen app."""
    try:
        from importlib.metadata import version as _distribution_version
    except ImportError:  # pragma: no cover - stdlib since 3.8
        return None
    try:
        found = _distribution_version(DISTRIBUTION_NAME)
    except Exception:
        # `PackageNotFoundError` is the expected miss; anything else here (a
        # broken dist-info) is equally a "cannot answer".
        return None
    return (found or "").strip() or None


def app_version() -> str:
    """The app's version, resolved fresh. Never empty."""
    return _pyproject_version() or _metadata_version() or UNKNOWN_VERSION


#: Resolved once at import time, as a `__version__` is expected to be. Call
#: :func:`app_version` instead if a re-read matters (it does not at runtime — the
#: literal cannot change while the app runs).
__version__ = app_version()
