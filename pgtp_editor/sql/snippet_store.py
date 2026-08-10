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

# pgtp_editor/sql/snippet_store.py
"""The snippet store's FORMAT and rules -- Qt-free, path-agnostic (FQ-030).

This module is the whole of the store except *where the file is*: it reads and
writes the JSON, states what a corrupt file means, and owns the import
collision rule. Resolving the on-disk location needs app knowledge (the
per-user app-data directory, and the test override for it), so that one job
lives in `ui/snippet_controller.py` and nothing else about the store does.
`pgtp_editor/sql/` stays importable without PySide6 (§5's dependency rule,
asserted by `tests/sql/test_package_purity.py`).

WHERE IT LIVES AND WHY (DEC-001, answered 2026-08-10)
-----------------------------------------------------
ONE per-user store, in the application's own per-user folder -- **not** in the
`.pgtp` artifact and **not** per project. The owner's reasoning, which this
format is shaped by: a snippet is a *typing shortcut*, not a property of the
schema; the project is a **movable artifact** and personal state stays out of
it, crossing between people only by an **explicit** gesture. So there is
exactly one store, its precedence is trivial (it simply *is* the set in force),
and sharing is export/import -- never silent embedding and never an auto-merge
of two stores, which DEC-001 explicitly rejected.

THE FILE HOLDS THE WHOLE SET, NOT A DIFF
----------------------------------------
`snippets.json` lists every snippet in force, shipped defaults included. The
alternative -- store only the user's additions and overlay them on
`DEFAULT_SNIPPETS` -- cannot express *deleting* a shipped snippet without a
second "tombstone" concept, and it makes the file lie to the human who opens
it: the owner asked for a store "editable by the users", and a file that shows
three of the eleven snippets actually in force is not editable in any useful
sense. What you see in the file is what the editor expands.

The cost is that the shipped set is frozen into a user's file the day they
first save: later default snippets do not appear for them. That is the right
trade for a typing shortcut (and `defaults_missing_from` lets the editor point
it out), whereas silently re-adding a default the user deleted is not.

`origin_of` classifies each entry against the shipped set so the editor can
show which rows are ours and which are theirs.

A CORRUPT FILE IS NEVER SILENTLY DISCARDED
------------------------------------------
`load_snippets` never raises and never returns "empty" for a broken file. It
returns a `LoadedSnippets` carrying the shipped defaults **plus an `error`**,
and the caller's contract (see `ui/snippet_controller.py`) is that a store
which failed to load is **read-only**: the app runs on the defaults and says
why, but it must not write over a file it could not understand -- the user's
snippets may be one typo away from being fine, and overwriting is the one
failure they could not undo.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pgtp_editor.sql.templates import DEFAULT_SNIPPETS, Snippet

__all__ = [
    "SNIPPETS_FILENAME",
    "STORE_VERSION",
    "LoadedSnippets",
    "ImportPlan",
    "ORIGIN_DEFAULT",
    "ORIGIN_MODIFIED_DEFAULT",
    "ORIGIN_USER",
    "origin_of",
    "defaults_missing_from",
    "serialize_snippets",
    "parse_snippets",
    "load_snippets",
    "save_snippets",
    "plan_import",
    "apply_import",
]

#: The store's file name. Deliberately the same file that export writes and
#: import reads, so "send your snippets to a colleague" can also be done by
#: mailing this file directly -- the gesture in the app is a convenience over a
#: format that is already shareable, not a private encoding.
SNIPPETS_FILENAME = "snippets.json"

#: Bumped only if the on-disk shape changes incompatibly. Readers accept a
#: missing or unknown version rather than refusing -- a hand-edited file that
#: forgot the key is exactly the case the format exists to tolerate.
STORE_VERSION = 1

_SNIPPETS_KEY = "snippets"
_VERSION_KEY = "version"

#: What `origin_of` answers.
ORIGIN_DEFAULT = "default"           # byte-identical to a shipped snippet
ORIGIN_MODIFIED_DEFAULT = "modified"  # a shipped prefix, edited by the user
ORIGIN_USER = "user"                  # a prefix we never shipped


@dataclass(frozen=True)
class LoadedSnippets:
    """The outcome of reading the store.

    `snippets` is always usable -- the shipped defaults when there was nothing
    to read or nothing readable. `error` is a human sentence when the file
    existed but could not be understood (and is the caller's signal to go
    read-only); `from_file` says the returned set actually came from disk.
    """

    snippets: tuple[Snippet, ...] = DEFAULT_SNIPPETS
    error: str | None = None
    from_file: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class ImportPlan:
    """What importing `incoming` over `current` would do.

    `added` are prefixes not present today; `colliding` are prefixes that
    already exist. Splitting them is the whole point: the collision rule below
    is a QUESTION for the user, not a decision this module makes.
    """

    added: tuple[Snippet, ...] = ()
    colliding: tuple[Snippet, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.added and not self.colliding


def _key(prefix: str) -> str:
    """Prefixes are compared case-insensitively -- `find_snippet` matches that
    way, so `CASE` and `case` are the same snippet and must collide."""
    return (prefix or "").strip().lower()


# --- classification --------------------------------------------------------


def origin_of(snippet: Snippet, defaults: Iterable[Snippet] = DEFAULT_SNIPPETS) -> str:
    """Whether `snippet` is one of ours, one of ours edited, or the user's own.

    The editor shows this so "which of these did I write?" is answerable at a
    glance -- the store holds the whole set, so nothing else distinguishes a
    shipped row from a hand-written one.
    """
    for default in defaults:
        if _key(default.prefix) == _key(snippet.prefix):
            if (
                default.title == snippet.title
                and default.template == snippet.template
            ):
                return ORIGIN_DEFAULT
            return ORIGIN_MODIFIED_DEFAULT
    return ORIGIN_USER


def defaults_missing_from(
    snippets: Iterable[Snippet], defaults: Iterable[Snippet] = DEFAULT_SNIPPETS
) -> tuple[Snippet, ...]:
    """Shipped snippets the given set does not contain.

    Because the file holds the whole set, a default is missing either because
    the user deleted it or because it was added to the app after their file was
    written. The editor offers to restore them; it never restores one by itself.
    """
    have = {_key(s.prefix) for s in snippets}
    return tuple(d for d in defaults if _key(d.prefix) not in have)


# --- format ----------------------------------------------------------------


def serialize_snippets(snippets: Iterable[Snippet]) -> str:
    """The store's JSON text: indented, key-ordered, newline-terminated.

    Formatted for a human to open in a text editor, because the owner's ruling
    says the store is user-editable. `ensure_ascii=False` keeps a comment or
    message in the user's own language readable in the file.
    """
    payload = {
        _VERSION_KEY: STORE_VERSION,
        _SNIPPETS_KEY: [
            {
                "prefix": s.prefix,
                "title": s.title,
                "template": s.template,
            }
            for s in snippets
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def parse_snippets(text: str) -> LoadedSnippets:
    """Parse store JSON. Never raises; a bad file comes back as an `error`.

    Tolerant where tolerance is safe (unknown top-level keys, a missing
    `version`, a missing `title`) and strict where it is not: a row without a
    usable `prefix` or `template` is not a snippet, and an empty list is a
    legitimate answer ("I deleted them all") rather than an error.
    """
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        return LoadedSnippets(error=f"not valid JSON ({exc})")

    if isinstance(data, list):
        # A bare list is what a hand-written file most plausibly looks like.
        rows = data
    elif isinstance(data, dict):
        rows = data.get(_SNIPPETS_KEY)
        if rows is None:
            return LoadedSnippets(error=f'no "{_SNIPPETS_KEY}" list in the file')
    else:
        return LoadedSnippets(error="the file is not a JSON object or list")

    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return LoadedSnippets(error=f'"{_SNIPPETS_KEY}" is not a list')

    parsed: list[Snippet] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            return LoadedSnippets(error=f"entry {index + 1} is not an object")
        prefix = row.get("prefix")
        template = row.get("template")
        if not isinstance(prefix, str) or not prefix.strip():
            return LoadedSnippets(error=f"entry {index + 1} has no trigger word")
        if not isinstance(template, str):
            return LoadedSnippets(
                error=f"entry {index + 1} ({prefix}) has no body"
            )
        if _key(prefix) in seen:
            return LoadedSnippets(
                error=f"the trigger word {prefix!r} appears more than once"
            )
        seen.add(_key(prefix))
        title = row.get("title")
        parsed.append(
            Snippet(
                prefix.strip(),
                title if isinstance(title, str) else "",
                template,
            )
        )

    return LoadedSnippets(snippets=tuple(parsed), from_file=True)


# --- file I/O --------------------------------------------------------------


def load_snippets(path: Path) -> LoadedSnippets:
    """Read the store at `path`. Missing file -> the shipped defaults, no error.

    "Missing" is the normal state of a fresh install and is not a problem worth
    reporting. Anything else that goes wrong is reported and leaves the
    defaults in force -- see the module docstring on why a failed load must
    never lead to a write.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return LoadedSnippets()
    except (OSError, UnicodeDecodeError) as exc:
        return LoadedSnippets(error=f"could not be read ({exc})")
    if not text.strip():
        # An empty file is indistinguishable from a truncated write; treat it
        # as "nothing stored yet" rather than "you have no snippets".
        return LoadedSnippets()
    return parse_snippets(text)


def save_snippets(path: Path, snippets: Iterable[Snippet]) -> None:
    """Write the whole set to `path`, creating the directory. Raises `OSError`.

    Deliberately NOT silent about failure, unlike `load_snippets`: a save the
    user asked for and that did not happen is something they must be told.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_snippets(snippets), encoding="utf-8")


# --- import ----------------------------------------------------------------


def plan_import(
    current: Iterable[Snippet], incoming: Iterable[Snippet]
) -> ImportPlan:
    """Split `incoming` into new prefixes and prefixes that already exist.

    THE COLLISION RULE (FQ-030): **new snippets are added, colliding ones are
    never overwritten without the user saying so.** Import is the one gesture
    where "no silent merge" is easiest to violate -- a file from a colleague
    that quietly redefined `case` would change what the user's own typing does,
    with nothing on screen to say it happened. So the split is computed here
    and the answer for the colliding half is asked, not assumed; `apply_import`
    takes that answer as an argument and has no default.

    Duplicated prefixes *within* `incoming` keep the first occurrence, matching
    `find_snippet`'s first-match lookup.
    """
    have = {_key(s.prefix) for s in current}
    added: list[Snippet] = []
    colliding: list[Snippet] = []
    seen: set[str] = set()
    for snippet in incoming:
        key = _key(snippet.prefix)
        if key in seen:
            continue
        seen.add(key)
        (colliding if key in have else added).append(snippet)
    return ImportPlan(tuple(added), tuple(colliding))


def apply_import(
    current: Iterable[Snippet],
    incoming: Iterable[Snippet],
    *,
    overwrite: bool,
) -> tuple[Snippet, ...]:
    """The set that results from importing `incoming` into `current`.

    `overwrite` is the user's answer to the collision question and has no
    default on purpose. False keeps every existing snippet exactly as it is and
    appends only the new ones; True replaces colliding entries **in place**, so
    the user's ordering survives an import. Nothing is ever removed.
    """
    plan = plan_import(current, incoming)
    replacements = {_key(s.prefix): s for s in plan.colliding} if overwrite else {}
    result = [replacements.get(_key(s.prefix), s) for s in current]
    result.extend(plan.added)
    return tuple(result)
