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

# pgtp_editor/db/bookmark_store.py
"""Project-local bookmark persistence (§8 + §18.2, FQ-013): the store behind
*"bookmarks survive a document reload and an app restart -- but only when a
project is open"*.

**Wired.** `MainWindow` restores through `load_editor_bookmarks` when a
document loads (the one moment `GutterBookmarkFoldMixin` wipes its set) and
writes through `store_editor_bookmarks` on a 400 ms debounce after a
user-chosen change, plus a synchronous flush on project transition and in
`closeEvent`. The gate is `DdlProjectController.folder` -- the capability fact
"a project is open" -- so projectless editing is bit-for-bit unchanged: no
debounce is started and nothing is written. Only three editors have a
project-relative identity and therefore persist: the Raw XML editor, DDL
object tabs and PHP file tabs. The XSD editors cannot -- their files live in
app-level schema storage, outside any project -- and the DDL Explorer buffer,
draft fragment tabs and the `Edit code...` dialog have no file identity at all.

**The gate is a capability, not an intent.** Persistence exists exactly when a
§18.2 project folder is open (`DdlProjectController._folder`) -- never on the
launcher's *mode*. Conflating the two would put the feature on the wrong side of
the app's absent-on-capability-not-intent rule. With no project open there is no
root to key paths against, so behaviour is unchanged: session-only, wiped by
`setPlainText`, no file written anywhere. This module simply cannot be called
without a project directory.

**Why a sibling file and not a `ProjectSettings` key.** Bookmarks live in
`<project>/.ddlproject/bookmarks.json`, next to `settings.json` but *not inside
it*. `ProjectSettings` is the project's **shared** configuration -- connections,
git settings, and the `deployed` map the deploy manifest is built from -- read
and written by several controllers. Personal caret furniture does not belong in
that schema, and folding it in would mean every gutter click dirties the one
file the deploy pipeline depends on. A separate file also means a corrupt
bookmark store can never cost the user their project settings.

**Keying is project-relative, with POSIX separators**, following
`routine_ddl_paths`' recomputable-path discipline (`db/ddl_project.py`): a
project that is moved, cloned, or opened from a different mount (§18.3's sshfs
share) keeps its bookmarks, and a store written on Windows reads on Linux. A
file outside the project folder has no key at all -- `relative_key` returns
`None`, and the caller leaves that editor session-only. That is also the answer
for the identity-less editors (the read-only DDL Explorer buffer, FQ-006 draft
fragments, the `Edit code…` modal): no project file, no key, no persistence.

**On-disk shape** -- one JSON object, `indent=2`/`sort_keys` like
`save_settings`, so it stays human-diffable:

    {
      "version": 1,
      "files": {
        "ddl/public.foo.sql": [3, 41],
        "working_copy/app.pgtp": [0]
      }
    }

Values are **0-based block numbers**, exactly what the gutter mixin holds,
sorted and de-duplicated. The `version` field is cheap insurance: a future
content-anchored format bumps it, and *this* reader treats any version it does
not know as "no bookmarks" rather than guessing at foreign data.

**Empty sets remove their key** rather than storing `[]` -- an editor with no
bookmarks is indistinguishable from an editor never bookmarked, so recording it
would only accumulate keys for every file ever opened. When the last key goes,
the file is truncated to an empty `files` map if it already exists, and is *not*
created if it does not: a project nobody bookmarked in carries no store at all.

**Stale lines: restore in range, drop out of range.** `load_editor_bookmarks`
takes the document's block count and silently discards stored lines beyond it,
matching the mixin's existing defensive posture (§8: *"out-of-range block
numbers are ignored defensively"*). **No content anchoring in v1** -- storing
each line's text and re-finding it after an outside edit was considered and
**deferred, not rejected**: duplicate and moved matches make it a feature with
its own ambiguity, and it gets its own decision plus a `version` bump.

**Reads never raise, because a raise here would land in a gutter click.** A
missing file, unreadable file, malformed JSON, wrong top-level type, unknown
`version`, or a garbage entry all degrade to "no bookmarks" for the affected
scope. Writes are idempotent -- the same mapping written twice produces
byte-identical output -- and go through
`db/ddl_project.py::_ensure_gitignored(project_dir, ".ddlproject/")`, which is
idempotent and *already* covers this file via `save_settings`; calling it adds no
second entry, and it guarantees coverage even if bookmarks are written before
the project's first settings save. Bookmarks are personal, not shared: they must
never reach the repo.

Qt-free and DB-free, like `db/ddl_project.py`: plain JSON on plain files.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

# `_ensure_gitignored` is reached across the module boundary on purpose: it is
# the project's one gitignore mechanism (idempotent, exact-line/directory-form
# match), and duplicating it here would be a second implementation of the rule
# that keeps private project state out of the repo.
from .ddl_project import SETTINGS_DIRNAME, _ensure_gitignored

#: The bookmark store's filename -- a sibling of `settings.json` inside the
#: project's already-gitignored `.ddlproject/` directory, never a key in it.
BOOKMARKS_FILENAME = "bookmarks.json"

#: On-disk schema version. A reader that meets an unknown version reports "no
#: bookmarks" instead of guessing (content anchoring would bump this).
BOOKMARKS_VERSION = 1


def bookmarks_path(project_dir: Path | str) -> Path:
    """The bookmark store's path for `project_dir`."""
    return Path(project_dir) / SETTINGS_DIRNAME / BOOKMARKS_FILENAME


def relative_key(project_dir: Path | str, file_path: Path | str) -> str | None:
    """`file_path`'s store key: its path relative to `project_dir`, with POSIX
    `/` separators -- or `None` if it is not inside the project (an editor with
    no project-relative identity stays session-only).

    Both paths are resolved first, so a symlinked or `..`-laden path still
    keys the same as its canonical form -- the property that makes a moved or
    cloned project keep its bookmarks.
    """
    try:
        root = Path(project_dir).resolve()
        target = Path(file_path).resolve()
        relative = target.relative_to(root)
    except (OSError, ValueError):
        return None
    if not relative.parts:
        return None
    return relative.as_posix()


def load_bookmarks(project_dir: Path | str) -> dict[str, list[int]]:
    """The whole store as `{project-relative key: sorted block numbers}`.

    Never raises: a missing/unreadable file, malformed JSON, an unexpected
    top-level shape, or an unknown `version` all yield `{}`. Individual
    unusable entries are dropped without discarding the rest.
    """
    path = bookmarks_path(project_dir)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict) or raw.get("version") != BOOKMARKS_VERSION:
        return {}
    files = raw.get("files")
    if not isinstance(files, dict):
        return {}

    result: dict[str, list[int]] = {}
    for key, lines in files.items():
        if not isinstance(key, str) or not key:
            continue
        cleaned = _clean_lines(lines)
        if cleaned:
            result[key] = cleaned
    return result


def save_bookmarks(
    project_dir: Path | str, bookmarks: Mapping[str, Iterable[int]]
) -> None:
    """Write the whole store. Keys mapping to an empty set are dropped (see the
    module docstring); if nothing is left, the file is emptied when it exists
    and not created when it does not.

    Idempotent: the same mapping produces byte-identical output.
    """
    project_dir = Path(project_dir)
    path = bookmarks_path(project_dir)
    files = {
        key: lines
        for key, raw in bookmarks.items()
        if isinstance(key, str) and key and (lines := _clean_lines(raw))
    }
    if not files and not path.exists():
        return
    payload = {"version": BOOKMARKS_VERSION, "files": files}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _ensure_gitignored(project_dir, f"{SETTINGS_DIRNAME}/")


def load_editor_bookmarks(
    project_dir: Path | str, file_path: Path | str, block_count: int
) -> set[int]:
    """One editor's restorable bookmarks: every stored block number for
    `file_path` that is still **within** a document of `block_count` blocks.
    Out-of-range lines are dropped silently (v1 has no content anchoring), and
    an unkeyable path or an absent entry yields an empty set."""
    key = relative_key(project_dir, file_path)
    if key is None or block_count <= 0:
        return set()
    return {line for line in load_bookmarks(project_dir).get(key, ()) if line < block_count}


def store_editor_bookmarks(
    project_dir: Path | str, file_path: Path | str, lines: Iterable[int]
) -> None:
    """Replace one editor's stored bookmarks, leaving every other key alone --
    the read-modify-write the host calls on a quiet trigger (a 400 ms debounce,
    or a synchronous flush on project transition and app close), never inside
    the hot `toggle_bookmark` gesture, which must not do disk I/O.

    An empty `lines` removes the key. A path with no project-relative identity
    is a no-op, so a caller may call this unconditionally.
    """
    key = relative_key(project_dir, file_path)
    if key is None:
        return
    stored = load_bookmarks(project_dir)
    cleaned = _clean_lines(lines)
    if cleaned:
        stored[key] = cleaned
    else:
        stored.pop(key, None)
    save_bookmarks(project_dir, stored)


def prune_missing_files(project_dir: Path | str) -> None:
    """Drop keys whose file no longer exists in the project -- the same posture
    `resolve_ids` takes toward unknown toolbar ids (§7). Safe to call on any
    project; a no-op when nothing is stale."""
    project_dir = Path(project_dir)
    stored = load_bookmarks(project_dir)
    kept = {key: lines for key, lines in stored.items() if (project_dir / key).exists()}
    if kept != stored:
        save_bookmarks(project_dir, kept)


def _clean_lines(raw: object) -> list[int]:
    """Sorted, de-duplicated, non-negative block numbers from whatever was
    stored or handed in -- garbage entries are dropped, never raised on.
    `bool` is excluded explicitly: it is an `int` subclass, and `True` is not a
    line number."""
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Iterable):
        return []
    return sorted(
        {
            line
            for line in raw
            if isinstance(line, int) and not isinstance(line, bool) and line >= 0
        }
    )
