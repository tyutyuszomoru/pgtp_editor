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

"""Pure, Qt-light identity rules for customizable toolbar commands
(Sub-project E; widened by BUG-027).

BUG-027: the toolbar used to be a closed universe of seven hardcoded commands,
so Customize Toolbar could only ever offer those seven. The available set is
now **every menu command**, enumerated by walking the real menu bar
(`MainWindow._all_menu_commands`) -- so this module no longer holds the command
list at all. What stays here is the pure part: how a menu path becomes a stable
id, which legacy ids map onto which new ones, and which commands carry an icon.

Ids are derived from the menu path (``File > Save As...`` -> ``file.save-as``)
rather than hand-assigned. That means a newly added menu action becomes
toolbar-available with no bookkeeping here; the tradeoff is that *renaming* a
menu label changes its id, which drops that one button from an already-saved
toolbar. Menu labels change rarely and the degradation is self-healing (the
user re-adds it), so the zero-maintenance property wins.

Data-only so it can be unit-tested without a QApplication. Keep this module
free of Qt imports.
"""
import re
from collections.abc import Iterable, Sequence

# The seven commands the toolbar shipped with before BUG-027, as
# (legacy-id, label). Retained for three reasons: they name the vendored icon
# files (`icons.ACTION_ICON_FILES`), they define the default toolbar, and
# already-saved toolbars in QSettings still refer to them by legacy id.
LEGACY_COMMANDS: list[tuple[str, str]] = [
    ("open", "Open"),
    ("save", "Save"),
    ("undo", "Undo"),
    ("redo", "Redo"),
    ("find", "Find"),
    ("validate", "Validate"),
    ("generate", "Generate"),
]

# Legacy id -> menu-path id, so a toolbar saved before BUG-027 survives the
# widening instead of silently emptying to the default on first launch.
LEGACY_ID_ALIASES: dict[str, str] = {
    "open": "file.open",
    "save": "file.save",
    "undo": "edit.undo",
    "redo": "edit.redo",
    "find": "edit.find",
    "validate": "tools.validate-project",
    "generate": "generation.generate-php",
}

# The default toolbar layout: the legacy seven, in legacy order.
DEFAULT_TOOLBAR_IDS: list[str] = [
    LEGACY_ID_ALIASES[cid] for cid, _label in LEGACY_COMMANDS
]

# Menu-path id -> icon id (the `icons.ACTION_ICON_FILES` key). Only the legacy
# seven have vendored SVGs; every other command is icon-less by design -- an
# icon must never be a precondition for putting a command on the toolbar.
ICON_ID_BY_COMMAND: dict[str, str] = {
    command_id: legacy_id for legacy_id, command_id in LEGACY_ID_ALIASES.items()
}

_TRAILING_ELLIPSIS_RE = re.compile(r"(\.\.\.|…)\s*$")
_NON_SLUG_RE = re.compile(r"[^a-z0-9]+")


def normalize_label(text: str) -> str:
    """A menu label with its `&` mnemonic markers and trailing ellipsis
    removed -- what the user actually reads."""
    return _TRAILING_ELLIPSIS_RE.sub("", (text or "").replace("&", "")).strip()


def slugify(text: str) -> str:
    """One menu-path segment as an id fragment: lowercase, punctuation runs
    collapsed to single hyphens (`Generate PHP...` -> `generate-php`)."""
    return _NON_SLUG_RE.sub("-", normalize_label(text).lower()).strip("-")


def command_id_for(path: Sequence[str]) -> str:
    """Stable id for a menu action from its full path of labels, outermost
    first: `["File", "Save As..."]` -> `"file.save-as"`. Empty segments are
    dropped so a stray separator title can't produce a leading dot."""
    return ".".join(part for part in (slugify(seg) for seg in path) if part)


def menu_path_label(path: Sequence[str]) -> str:
    """Human label for the Customize dialog's Available list, showing where
    the command lives: `File > Save As...` -> `"File › Save As"`."""
    return " › ".join(
        part for part in (normalize_label(seg) for seg in path) if part
    )


def valid_ids(ids: Iterable[str] | None, known: Iterable[str]) -> list[str]:
    """Filter `ids` to those present in `known`, preserving order and dropping
    unknowns and duplicates (keeping the first occurrence)."""
    known_set = set(known)
    seen: set[str] = set()
    result: list[str] = []
    for cid in ids or []:
        if cid in known_set and cid not in seen:
            seen.add(cid)
            result.append(cid)
    return result


def resolve_ids(ids: Iterable[str] | None, known: Iterable[str]) -> list[str]:
    """`valid_ids`, but mapping any legacy (pre-BUG-027) id onto its menu-path
    id first, so a toolbar saved by an older build still restores."""
    mapped = [LEGACY_ID_ALIASES.get(cid, cid) for cid in (ids or [])]
    return valid_ids(mapped, known)
