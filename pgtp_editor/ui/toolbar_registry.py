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
menu label changes its id, which would drop that one button from an
already-saved toolbar. Menu labels change rarely and the degradation is
self-healing (the user re-adds it), so the zero-maintenance property wins --
but a *deliberate* rename can carry a `RENAMED_ID_ALIASES` row (below) so the
user's pinned button survives it instead.

Data-only so it can be unit-tested without a QApplication. Keep this module
free of Qt imports.
"""
import re
from collections.abc import Iterable, Sequence

# The commands the toolbar shipped with before BUG-027, as (legacy-id, label).
# Retained for three reasons: they name the vendored icon files
# (`icons.ACTION_ICON_FILES`), they define the default toolbar, and
# already-saved toolbars in QSettings still refer to them by legacy id.
#
# There were SEVEN. `find` is **retired** (FQ-016): with the Edit menu dissolved,
# Find is a permanently visible bar, not a menu action, so it has no menu-path id
# to alias onto and cannot be pinned at all -- owner ruling, verbatim: "Find
# unpinnable is fine." Retiring it here (rather than leaving a dangling alias
# pointing at the vanished `edit.find`) is what stops a default toolbar button
# shipping empty and iconless on a fresh install; `edit-find.svg` stays in the
# Breeze catalog, so a user can still assign that icon to any other command.
#
# `save` is retired the SAME way (FQ-020): `File ▸ Save` and `Ctrl+S` are gone
# and saving is four per-tab entries on the Editor bar's `Deployment` menu, so
# there is no tab-following save command left for this row to alias onto -- and
# the four that exist are tab-gated, so pinning one by default would ship a
# button that blinks out as the user changes tabs. The app therefore ships with
# NO save button; `document-save.svg` stays in the Breeze catalog and remains
# **user-assignable to any command** (FQ-004), exactly as `edit-find.svg` did.
# A user who had pinned Save loses that one button: `resolve_ids` filters the
# now-unresolvable `save`/`file.save` id out on load (see `resolve_ids`), which
# is the correct degradation -- no dead button, no error.
LEGACY_COMMANDS: list[tuple[str, str]] = [
    ("open", "Open"),
    ("undo", "Undo"),
    ("redo", "Redo"),
    ("validate", "Validate"),
    ("generate", "Generate"),
]

# Legacy id -> menu-path id, so a toolbar saved before BUG-027 survives the
# widening instead of silently emptying to the default on first launch.
#
# THREE of these moved with FQ-016's Editor menu bar and are updated here in the
# same commit -- an alias left pointing at a dead menu path makes a DEFAULT
# toolbar button appear empty and iconless (`DEFAULT_TOOLBAR_IDS` derives from
# this table, and `ICON_ID_BY_COMMAND` is its inverse, so a stale entry breaks
# both the button and its vendored SVG):
#   undo/redo:  Edit ▸ Undo/Redo   -> the Editor bar's History ▸ Undo/Redo
#   validate:   Tools ▸ Validate Project -> the Editor bar's Parsing ▸ Validate Project
#
# `save` has NO row any more (FQ-020, same treatment as `find`): `File ▸ Save`
# is deleted and its successors are per-tab, so there is nothing for it to point
# at -- see LEGACY_COMMANDS.
LEGACY_ID_ALIASES: dict[str, str] = {
    "open": "file.open",
    "undo": "history.undo",
    "redo": "history.redo",
    "validate": "parsing.validate-project",
    "generate": "generation.generate-php",
}

# The default toolbar layout: the legacy set, in legacy order (FIVE since FQ-020
# retired `save`; six between FQ-016's retirement of `find` and that -- see
# LEGACY_COMMANDS). It derives from the two tables above, so retiring a row
# shortens it by itself.
DEFAULT_TOOLBAR_IDS: list[str] = [
    LEGACY_ID_ALIASES[cid] for cid, _label in LEGACY_COMMANDS
]

# Menu-path id -> menu-path id, for commands that were RENAMED or MOVED after
# BUG-027 widened toolbar ids to menu paths. A saved toolbar (and a saved FQ-004
# icon assignment) refers to the old path; without a row here the id no longer
# resolves and `resolve_ids` silently drops the user's button.
#
# DELIBERATELY NOT `LEGACY_ID_ALIASES`, and this is a correctness constraint
# rather than tidiness: `ICON_ID_BY_COMMAND` is that dict INVERTED, so a row
# there would make `icon_id_for(<new id>)` return a *menu-path* id where an
# *icon* id is expected -- `icons.load_svg_text` raises `KeyError` for it, which
# `_set_action_icon`'s bare `except Exception` swallows, permanently defeating any
# later default-icon binding for that command instead of crashing. This table is
# consulted by `resolve_ids`/`resolve_icon_assignments` and inverted by nothing.
#
# FQ-022 (§18.7) opened it: `Database ▸ DDL Explorer` became
# `DDL Explorer (Quality)` when it gained a sandbox-scoped sibling, because a
# bare "DDL Explorer" next to it would be ambiguous -- and the label IS the id.
#
# FQ-021 renamed the Editor bar's `Bookmarks` menu to `Navigation`, so all five
# of its members changed id even though their OWN labels did not: the id is the
# whole menu path, and the first segment is the menu title. Five rows, one per
# member, because there is no prefix rewriting here by design -- `resolve_ids`
# does exact lookups, which is what keeps this table auditable.
#
# FQ-021's third leg then MOVED three commands off `Tools` onto that same
# renamed menu, so each changed BOTH its first segment and (for one of them) its
# last: `Prev Difference` was relabelled `Previous Difference` to match
# `Previous Bookmark` two entries above it, and the label is the id's last
# segment. `Apply Changes to Target` gets a row even though FQ-020 had already
# removed it from `Tools` -- a toolbar saved before FQ-020 still names
# `tools.apply-changes-to-target`, and it is a MOVE (the command exists again,
# on `Navigation`), not a deletion.
#
# FQ-020 opened it three more times -- every one a MOVE or RENAME of a command
# that still exists, which is exactly what this table is for (a command that was
# *deleted*, like `file.save`, gets no row: `resolve_ids` drops it, which is the
# intended degradation):
#   Tools ▸ Compare / Merge Two Files… -> Deployment ▸ Compare/Merge pgtp
#   File ▸ Deploy .pgtp                -> Deployment ▸ Deploy .pgtp
#   File ▸ Revert                      -> File ▸ Discard Changes (re-specified)
# BUG-039 opened it twice more: §18.5 D3a's two check gestures MOVED off the
# Database menu onto the Editor bar's `Parsing` menu (Parsing only -- they are
# not on both). Their labels did not change, but the id is the whole menu path,
# so a toolbar saved before the move needs these rows to keep its buttons.
# FQ-027 opened it once more: `File ▸ Show Launcher…` was RENAMED to
# `File ▸ New Session` (one action, not two -- it kept its place in the File
# menu and gained the save-all/close/relaunch teardown). The label is the id's
# last segment, so the rename is an id change like any other, and a toolbar
# saved before it still names `file.show-launcher`.
RENAMED_ID_ALIASES: dict[str, str] = {
    "database.ddl-explorer": "database.ddl-explorer-quality",
    "bookmarks.toggle-bookmark": "navigation.toggle-bookmark",
    "bookmarks.next-bookmark": "navigation.next-bookmark",
    "bookmarks.previous-bookmark": "navigation.previous-bookmark",
    "bookmarks.clear-all-bookmarks": "navigation.clear-all-bookmarks",
    "bookmarks.list-all-bookmarks": "navigation.list-all-bookmarks",
    "tools.next-difference": "navigation.next-difference",
    "tools.prev-difference": "navigation.previous-difference",
    "tools.apply-changes-to-target": "navigation.apply-changes-to-target",
    "tools.compare-merge-two-files": "deployment.compare-merge-pgtp",
    "file.deploy-pgtp": "deployment.deploy-pgtp",
    "file.revert": "file.discard-changes",
    "file.show-launcher": "file.new-session",
    "database.check-object-in-sandbox": "parsing.check-object-in-sandbox",
    # FQ-026's three renames. The label IS the id's last segment, so renaming
    # the menu entry renames the command.
    #
    # **`resolve_ids` applies this table EXACTLY ONCE, not transitively** (see
    # its body: one `RENAMED_ID_ALIASES.get` pass over the already-legacy-mapped
    # ids). So a command renamed twice needs its OLD rows re-pointed at the
    # final id, not a chain -- which is why BUG-039's
    # `database.check-object-without-applying` row below now names
    # `parsing.check-and-rollback` rather than the intermediate
    # `parsing.check-object-without-applying` it was written with. Left as a
    # chain, a toolbar saved before BUG-039 would resolve to an id that no
    # longer exists and `valid_ids` would silently drop the button -- the exact
    # failure this table exists to prevent.
    "database.check-object-without-applying": "parsing.check-and-rollback",
    "parsing.check-object-without-applying": "parsing.check-and-rollback",
    "deployment.run-on-sandbox": "deployment.check-and-commit-to-sandbox",
    "deployment.run-on-quality": "deployment.apply-to-quality",
    # `View ▸ Results` -> `View ▸ Messages`: FQ-028's bottom-dock tab was named
    # the same as the Sandbox SQL Console's query-result grid, which is a
    # different surface entirely. Only the message-log tab is renamed.
    "view.results": "view.messages",
    "view.activity-log-results-panel": "view.activity-log-messages-panel",
    # BUG-058: §18.8's `Project Status…` MOVED from the Database menu to `File`,
    # directly under `Project Settings…`. Its label did not change, but the id is
    # the whole menu path, so a toolbar saved before the move needs this row to
    # keep its button. A MOVE, so it gets a row (unlike the deletions above).
    "database.project-status": "file.project-status",
    # `database.deploy-this-edit` gets NO row: FQ-026 DELETES the picker, and a
    # deletion degrades through `resolve_ids` dropping the unresolvable id (the
    # `file.save` precedent). A row here would point a saved button at a
    # command that does not exist, which `valid_ids` would drop anyway -- while
    # making the table claim the command merely moved.
}

# Menu-path id -> icon id (the `icons.ACTION_ICON_FILES` key). Only the legacy
# set has vendored SVG defaults; every other command is icon-less by design -- an
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
    id first and then any renamed/moved menu path onto its current one, so a
    toolbar saved by an older build still restores.

    Two tables, applied in that order: a legacy id maps into the menu-path id
    space, and `RENAMED_ID_ALIASES` then moves within it (see its comment for why
    the two must not be one dict)."""
    mapped = [LEGACY_ID_ALIASES.get(cid, cid) for cid in (ids or [])]
    mapped = [RENAMED_ID_ALIASES.get(cid, cid) for cid in mapped]
    return valid_ids(mapped, known)


# -- per-command icon assignments (FQ-004) ----------------------------------
#
# A user may pick a Breeze icon for ANY toolbar button, overriding the legacy
# default where there is one. The assignment is keyed by the same stable
# menu-path command id `toolbarIds` uses, and persisted in a sibling QSettings
# key (`ICON_ASSIGNMENTS_SETTINGS_KEY`). Absence of an assignment means "use
# the default" -- which is what makes an older saved toolbar, with no
# assignments at all, behave exactly as before.

ICON_ASSIGNMENTS_SETTINGS_KEY = "toolbarIconIds"

_ASSIGNMENT_SEPARATOR = "="


def serialize_icon_assignments(assignments: dict[str, str] | None) -> list[str]:
    """`{command_id: icon_id}` as a flat, QSettings-friendly list of
    ``"command_id=icon_id"`` strings, sorted for a stable stored order."""
    return [
        f"{command_id}{_ASSIGNMENT_SEPARATOR}{icon_id}"
        for command_id, icon_id in sorted((assignments or {}).items())
        if command_id and icon_id
    ]


def parse_icon_assignments(value) -> dict[str, str]:
    """The inverse of `serialize_icon_assignments`, tolerant of what QSettings
    hands back: a list of ``"command_id=icon_id"`` strings, a single such
    string, an already-parsed dict, or None/garbage (-> empty)."""
    if isinstance(value, dict):
        return {
            str(k): str(v) for k, v in value.items() if str(k) and str(v)
        }
    if isinstance(value, str):
        value = [value]
    result: dict[str, str] = {}
    for raw in value or []:
        if not isinstance(raw, str) or _ASSIGNMENT_SEPARATOR not in raw:
            continue
        command_id, _, icon_id = raw.partition(_ASSIGNMENT_SEPARATOR)
        command_id, icon_id = command_id.strip(), icon_id.strip()
        if command_id and icon_id:
            result[command_id] = icon_id
    return result


def resolve_icon_assignments(
    assignments: dict[str, str] | None,
    known_commands: Iterable[str],
    known_icons: Iterable[str],
) -> dict[str, str]:
    """Filter a loaded assignment map to what still exists, the way
    `resolve_ids` filters saved toolbar ids.

    Legacy (pre-BUG-027) command ids are mapped onto their menu-path id first,
    then any RENAMED_ID_ALIASES row is applied, so an assignment made against a
    command's old menu path survives the rename; an assignment whose command no
    longer exists, or whose icon is no longer vendored, is dropped.
    """
    known_command_set = set(known_commands)
    known_icon_set = set(known_icons)
    result: dict[str, str] = {}
    for command_id, icon_id in (assignments or {}).items():
        mapped = LEGACY_ID_ALIASES.get(command_id, command_id)
        mapped = RENAMED_ID_ALIASES.get(mapped, mapped)
        if mapped in known_command_set and icon_id in known_icon_set:
            result[mapped] = icon_id
    return result


def icon_id_for(command_id: str, assignments: dict[str, str] | None = None):
    """The icon a toolbar button should show: the user's assignment if there
    is one, else the legacy default from `ICON_ID_BY_COMMAND`, else None.

    Note the two id spaces: an assignment holds a *catalog* icon id (an SVG
    filename stem, e.g. ``document-save-as``) while a legacy default holds a
    legacy action id (``save``). `icons.load_svg_text` accepts either.
    """
    assigned = (assignments or {}).get(command_id)
    if assigned:
        return assigned
    return ICON_ID_BY_COMMAND.get(command_id)
