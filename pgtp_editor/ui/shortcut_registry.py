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

# pgtp_editor/ui/shortcut_registry.py
"""Pure, Qt-free rules for user-rebindable keyboard shortcuts (FQ-012).

The sibling of `toolbar_registry.py`, and deliberately its twin: FQ-012
enumerates the **same** command universe Customize Toolbar does (the menu bar,
walked by `ToolbarController.collect_menu_commands()`, with ids from
`command_id_for()`), so this module holds only the part that is *about
shortcuts* and reuses that module's identity tables verbatim rather than
growing a second copy of them.

Three things live here, all data-only so they unit-test without a
QApplication -- keep this module free of Qt imports:

1. **Normalization.** `normalize_sequence` maps every spelling of a chord onto
   one canonical string, so `"ctrl+shift+s"`, `"Shift+Ctrl+S"` and Qt's own
   `"Ctrl+Shift+S"` compare equal. Without it every rule below is defeated by
   a difference in capitalization.
2. **What may not be bound, and why** (`RESERVED_SEQUENCES`,
   `RESERVED_COMMAND_IDS`, `RESERVED_BINDINGS`) -- transcribed from §27 of the
   consolidated spec, each row carrying the reason the user is shown.
3. **The conflict rule** (`detect_conflicts`, `assign_shortcut`,
   `resolve_bindings`) -- see below.

**Why a conflict is a hard error and not a matter of taste.** Qt resolves two
enabled shortcuts matching one key press by firing **neither** of them (only
`activatedAmbiguously`). The codebase already has this written down at the one
place it bit us -- `find_replace_bar.install_focus_shortcuts`: *"Qt does not
prefer a narrower context over a wider one: two enabled shortcuts matching the
same key press are ambiguous, and neither fires."* So a double binding does not
degrade to "the first one wins"; it silently deletes **both** commands from the
keyboard. That is the silent-wrong class this project refuses, which is why:

- **Assigning a key that another editable command holds STEALS it** --
  `assign_shortcut` clears the loser's binding in the same operation and names
  it, so the map can never *hold* a duplicate, not even transiently (FQ-012
  settled decision 2: "warn + reassign (steal), user's choice" -- the dialog
  shows `conflict_message` first, the steal happens only if the user proceeds).
- **Assigning a key that a NON-editable occupant holds is REFUSED, not
  stolen.** The dialog owns only the menu-bar QActions; it cannot clear a
  window-scoped `QShortcut`, a per-tab focus shortcut or a widget's own
  `keyPressEvent`. Stealing what you cannot clear would produce exactly the
  ambiguity above, so those sequences are refused as targets outright.

**Persistence** mirrors FQ-004's `toolbarIconIds` shape exactly
(`serialize_icon_assignments` / `parse_icon_assignments` /
`resolve_icon_assignments`): a flat list of ``"command_id=Ctrl+G"`` strings
under a sibling key in the same `QSettings("MDS", "PGTP Editor")` scope, pruned
on load against the commands that still exist. **One deliberate difference:**
an *empty* value is meaningful here and is preserved -- ``"file.close="`` means
"the user cleared this command's binding", which is a different state from "no
override, keep the default" (the icon map has no such state, so it drops empty
values). Absence still means "use the captured default", which is what makes a
settings file written before FQ-012 behave exactly as before.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from pgtp_editor.ui.toolbar_registry import (
    LEGACY_ID_ALIASES,
    RENAMED_ID_ALIASES,
)

SHORTCUT_OVERRIDES_SETTINGS_KEY = "shortcutOverrides"

_ASSIGNMENT_SEPARATOR = "="

# -- normalization -----------------------------------------------------------
#
# The canonical modifier order is Ctrl, Alt, Shift, Meta -- Qt's own order for
# the common case (`QKeySequence("ctrl+shift+alt+x").toString()` is
# `"Ctrl+Alt+Shift+X"`), though Qt is not fully consistent about it
# (`"meta+ctrl+g"` round-trips as `"Meta+Ctrl+G"`). Since every comparison in
# this module normalizes BOTH sides, what matters is that the form is stable,
# not that it matches Qt byte-for-byte.

_MODIFIERS: dict[str, str] = {
    "ctrl": "Ctrl",
    "control": "Ctrl",
    "alt": "Alt",
    "opt": "Alt",
    "option": "Alt",
    "shift": "Shift",
    "meta": "Meta",
    "cmd": "Meta",
    "command": "Meta",
    "super": "Meta",
    "win": "Meta",
}

_MODIFIER_ORDER = ("Ctrl", "Alt", "Shift", "Meta")

# Spellings Qt itself produces or accepts for one physical key. `Esc`/`Escape`
# and `Return`/`Enter` are the two that actually differ in practice:
# `QKeySequence("esc").toString()` is `"Esc"` while a hand-written spec row
# says `Escape`, and `Ctrl+Enter` and `Ctrl+Return` are *different* sequences
# to Qt but the same intent to a user reading §27.
_KEY_ALIASES: dict[str, str] = {
    "esc": "Escape",
    "escape": "Escape",
    "enter": "Return",
    "return": "Return",
    "del": "Delete",
    "delete": "Delete",
    "ins": "Insert",
    "insert": "Insert",
    "pgup": "PgUp",
    "pageup": "PgUp",
    "pgdown": "PgDown",
    "pgdn": "PgDown",
    "pagedown": "PgDown",
    "space": "Space",
    "backspace": "Backspace",
    "tab": "Tab",
    "home": "Home",
    "end": "End",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
}


def _normalize_key(token: str) -> str:
    """One non-modifier key token in canonical spelling."""
    lowered = token.lower()
    if lowered in _KEY_ALIASES:
        return _KEY_ALIASES[lowered]
    if len(lowered) == 1:
        return lowered.upper()
    if lowered.startswith("f") and lowered[1:].isdigit():
        return "F" + str(int(lowered[1:]))
    return token[:1].upper() + token[1:]


def _normalize_chord(text: str) -> str:
    parts = [part.strip() for part in text.split("+")]
    parts = [part for part in parts if part]
    if not parts:
        return ""
    # The LAST token is always the key, even when it names a modifier
    # (`"Ctrl+Shift"` is a real, if useless, sequence); everything before it is
    # a modifier, and anything there that is not one is passed through in place
    # rather than silently dropped.
    *lead, key = parts
    modifiers: list[str] = []
    extras: list[str] = []
    for part in lead:
        canonical_modifier = _MODIFIERS.get(part.lower())
        if canonical_modifier is None:
            extras.append(_normalize_key(part))
        elif canonical_modifier not in modifiers:
            modifiers.append(canonical_modifier)
    ordered = [mod for mod in _MODIFIER_ORDER if mod in modifiers]
    return "+".join(ordered + extras + [_normalize_key(key)])


def normalize_sequence(text: str | None) -> str:
    """A key sequence in this module's one canonical spelling, or `""`.

    Empty/None/whitespace mean **unbound**, which is a legitimate state (the
    loser of a steal, and any command that never had a default). Multi-chord
    sequences (Qt's comma form, `"Ctrl+K, Ctrl+C"`) are normalized chord by
    chord; nothing in the app uses one today.
    """
    if not text:
        return ""
    chords = [
        _normalize_chord(chunk) for chunk in str(text).split(",")
    ]
    return ", ".join(chord for chord in chords if chord)


# -- what §27 pins -----------------------------------------------------------
#
# Transcribed from CONSOLIDATED_SPEC.md §27 (Consolidated keyboard shortcuts).
# Two distinct kinds of "reserved", which must not be merged:
#
#   RESERVED_SEQUENCES  -- a key that may never be the TARGET of a rebinding,
#                          because something the dialog does not own already
#                          answers to it (or because the spec pins it as
#                          deliberately dead). Refused, never stolen.
#   RESERVED_COMMAND_IDS -- a menu command whose OWN binding may not be moved.
#
# `F1` is in both: nothing else may take it, and Manual may not leave it.


RESERVED_SEQUENCES: dict[str, str] = {
    # §27, FQ-020: stated as deliberately unbound app-wide, not merely omitted
    # -- "no write, no message, no status-bar hint". The one carve-out is
    # `CodeEditorDialog`'s OK/Cancel pair, which is a modal's own key handling
    # and not a menu action, so it is equally unavailable as a target here.
    "Ctrl+S": "deliberately unbound app-wide — every save is a named "
              "Deployment menu click (§27)",
    "Ctrl+Shift+S": "deliberately unbound app-wide — every save is a named "
                    "Deployment menu click (§27)",
    # §27: window-scoped QShortcuts for the project snapshot history, with the
    # Edit-XSD / DDL-object-tab carve-out routing them to the text editor. Not
    # menu actions, so the dialog cannot clear them.
    "Ctrl+Z": "project history Undo — a window-scoped shortcut, not a menu "
              "action (§27)",
    "Ctrl+Y": "project history Redo — a window-scoped shortcut, not a menu "
              "action (§27)",
    "Ctrl+Shift+Z": "project history Redo, the second chord — answered inside "
                    "every XML editor's own key handling, so a command moved "
                    "here would only work while no editor has focus (§27)",
    # §27/§15, FQ-016/FQ-017: six per-tab `WidgetWithChildrenShortcut` pairs
    # (`find_replace_bar.install_focus_shortcuts`) plus the caption panel's own
    # pair. A window-level menu action on either key would be *ambiguous*
    # against them and Qt would fire neither.
    "Ctrl+F": "focuses the current tab's Find field — a per-tab shortcut at "
              "six sites (§27)",
    "Ctrl+R": "focuses the current tab's Replace field — a per-tab shortcut "
              "at six sites (§27)",
    "Escape": "returns focus to the document (§27)",
    # §27: window-level QActions with NO menu entry, so the menu walk cannot
    # enumerate them and this dialog has no row to move them from.
    "F3": "Find Next — a window-level command with no menu entry (§27)",
    "Ctrl+L": "Go To XSD — a window-level command with no menu entry (§27)",
    "Ctrl+Alt+F": "Format Selection — a context-menu command plus a shortcut "
                  "inside the Sandbox SQL Console and the DDL object tabs; "
                  "there is no menu-bar action to move (§27)",
    # FQ-030's four editor gestures. Two are handled inside `CodeEditor`'s own
    # key handling and two inside the SQL panels', so none of them is a QAction
    # the menu walk could enumerate — exactly the situation Ctrl+Alt+F is in,
    # and they are recorded here for the same reason: a menu command retargeted
    # onto one of these keys would fight a widget that already answers to it.
    "Ctrl+Alt+E": "Expand Snippet, in the SQL editors (FQ-030)",
    "Ctrl+Alt+C": "Expand SELECT into its column list, in the SQL editors "
                  "(FQ-030)",
    "Ctrl+Alt+J": "Write the JOIN a foreign key implies, in the SQL editors "
                  "(FQ-030)",
    "Ctrl+Shift+Space": "Signature help for the call at the caret, in the SQL "
                        "editors (FQ-030)",
    "Ctrl+Return": "Run, on the Sandbox SQL Console tab (§27)",
    "Ctrl+Space": "the completion popup, in three editor contexts (§27)",
    "Ctrl+G": "Go to line, in the caption grid (§27)",
    # §27/§26, FQ-016: the Edit menu's Cut/Copy/Paste/Delete were deleted as
    # never-implemented stubs and "Ctrl+C/X/V remain Qt built-ins" -- handled
    # inside the widgets. A window-level shortcut on one of them would take
    # precedence over the widget and break copy/cut/paste everywhere.
    "Ctrl+C": "Copy — a Qt built-in inside every editor widget (§26/§27)",
    "Ctrl+X": "Cut — a Qt built-in inside every editor widget (§26/§27)",
    "Ctrl+V": "Paste — a Qt built-in inside every editor widget (§26/§27)",
    # §27: Manual. Universal convention, and `Help ▸ Manual` is the one menu
    # entry §7 pins as never filtered out of any launch mode.
    "F1": "Manual — pinned (§27)",
}

RESERVED_COMMAND_IDS: dict[str, str] = {
    "help.manual": "Manual is pinned to F1 (§27) and is the one command no "
                   "launch mode may hide (§7)",
}


@dataclass(frozen=True)
class ReservedBinding:
    """A row the dialog shows read-only and greyed (FQ-012 settled decision 1:
    *"show as read-only 'reserved' rows"* -- the user gets to SEE that the key
    exists and why it is locked, which is more honest than a silently
    incomplete list)."""

    sequence: str
    reason: str


RESERVED_BINDINGS: tuple[ReservedBinding, ...] = tuple(
    ReservedBinding(sequence=sequence, reason=reason)
    for sequence, reason in RESERVED_SEQUENCES.items()
)


@dataclass(frozen=True)
class CommandBinding:
    """One editable row, as the host injects it.

    `command_id`/`label` are exactly what `command_id_for()` /
    `menu_path_label()` produce for the menu walk; `default_sequence` is the
    binding captured off the QAction **before** any override was applied, which
    is what makes "reset to default" and "restore all defaults" possible at all.
    """

    command_id: str
    label: str
    default_sequence: str = ""


def reserved_reason(sequence: str | None) -> str | None:
    """Why `sequence` may not be assigned to anything, or None if it is free."""
    return RESERVED_SEQUENCES.get(normalize_sequence(sequence))


def is_rebindable(command_id: str) -> bool:
    """Whether this command's own binding may be moved at all."""
    return command_id not in RESERVED_COMMAND_IDS


# -- the conflict rule -------------------------------------------------------


def detect_conflicts(bindings: Mapping[str, str] | None) -> dict[str, list[str]]:
    """`{sequence: [command_id, ...]}` for every sequence claimed by more than
    one command -- i.e. every sequence Qt would answer with **nothing**.

    Unbound commands are not conflicts with each other. Command ids are sorted
    so the report is stable.
    """
    by_sequence: dict[str, list[str]] = {}
    for command_id, sequence in (bindings or {}).items():
        normalized = normalize_sequence(sequence)
        if not normalized:
            continue
        by_sequence.setdefault(normalized, []).append(command_id)
    return {
        sequence: sorted(ids)
        for sequence, ids in by_sequence.items()
        if len(ids) > 1
    }


def commands_holding(
    bindings: Mapping[str, str] | None,
    sequence: str | None,
    exclude: str | None = None,
) -> list[str]:
    """The command ids currently bound to `sequence`, ignoring `exclude`
    (the command about to be assigned it). Sorted, so callers render a stable
    warning."""
    normalized = normalize_sequence(sequence)
    if not normalized:
        return []
    return sorted(
        command_id
        for command_id, held in (bindings or {}).items()
        if command_id != exclude and normalize_sequence(held) == normalized
    )


def refusal_for(command_id: str, sequence: str | None) -> str | None:
    """Why this assignment cannot be made at all, or None if it can.

    A refusal is not a conflict: a conflict is resolvable by stealing, a
    refusal is not (see the module docstring -- the dialog owns menu QActions
    and nothing else).
    """
    if command_id in RESERVED_COMMAND_IDS:
        return (
            f"{command_id} cannot be rebound: "
            f"{RESERVED_COMMAND_IDS[command_id]}."
        )
    normalized = normalize_sequence(sequence)
    if not normalized:
        return None
    reason = RESERVED_SEQUENCES.get(normalized)
    if reason is not None:
        return f"{normalized} is reserved: {reason}."
    return None


def assign_shortcut(
    bindings: Mapping[str, str] | None,
    command_id: str,
    sequence: str | None,
) -> tuple[dict[str, str], list[str]]:
    """Bind `sequence` to `command_id`, **stealing** it from any command that
    holds it, and return `(new_bindings, stolen_command_ids)`.

    The steal is what keeps the returned map conflict-free by construction: a
    key never ends up on two commands, so Qt is never asked to resolve an
    ambiguity it would answer by firing neither. Losers are left *unbound*
    (`""`), not deleted -- the row stays, it simply has no key.

    Raises `ValueError` for a refused assignment (`refusal_for`); the dialog
    checks first and never lets the user reach this.
    """
    refusal = refusal_for(command_id, sequence)
    if refusal is not None:
        raise ValueError(refusal)
    result = {cid: normalize_sequence(seq) for cid, seq in (bindings or {}).items()}
    normalized = normalize_sequence(sequence)
    stolen = commands_holding(result, normalized, exclude=command_id)
    for loser in stolen:
        result[loser] = ""
    result[command_id] = normalized
    return result, stolen


def default_bindings(commands: Iterable[CommandBinding]) -> dict[str, str]:
    """`{command_id: default_sequence}` for the injected command list."""
    return {
        command.command_id: normalize_sequence(command.default_sequence)
        for command in commands
    }


def resolve_bindings(
    commands: Sequence[CommandBinding],
    overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """The bindings the app should actually install: each command's captured
    default, with the user's overrides applied on top -- **conflict-free**.

    This is the "what does this mapping mean" logic, kept Qt-free so the wiring
    pass is a loop over the result calling `QAction.setShortcut()`.

    Overrides are applied through `assign_shortcut`, in sorted command-id order
    so the outcome is deterministic, which means an override always **wins over
    a default** it collides with and the defaulting command is left unbound.
    That is the same steal the dialog performed when the override was made;
    re-deriving it here is what stops a hand-edited or half-pruned settings
    file from installing an ambiguous pair.
    """
    bindings = default_bindings(commands)
    known = set(bindings)
    for command_id in sorted((overrides or {}).keys()):
        if command_id not in known:
            continue
        if refusal_for(command_id, overrides[command_id]) is not None:
            continue
        bindings, _stolen = assign_shortcut(
            bindings, command_id, overrides[command_id]
        )
    return bindings


def overrides_for(
    commands: Sequence[CommandBinding],
    bindings: Mapping[str, str] | None,
) -> dict[str, str]:
    """The minimal override map to persist: only the commands whose binding
    differs from their captured default.

    A command back on its default is **absent**, not stored as itself -- which
    is what lets a later build change a default and have every un-customized
    command follow it.
    """
    defaults = default_bindings(commands)
    result: dict[str, str] = {}
    for command_id, default in defaults.items():
        current = normalize_sequence((bindings or {}).get(command_id, default))
        if current != default:
            result[command_id] = current
    return result


# -- persistence (the FQ-004 `toolbarIconIds` shape) -------------------------


def serialize_shortcut_overrides(
    overrides: Mapping[str, str] | None,
) -> list[str]:
    """`{command_id: sequence}` as a flat, QSettings-friendly list of
    ``"command_id=Ctrl+G"`` strings, sorted for a stable stored order.

    An empty sequence is kept (``"file.close="``) -- see the module docstring:
    "the user cleared this binding" is a real state and losing it would
    resurrect the default on the next launch.
    """
    return [
        f"{command_id}{_ASSIGNMENT_SEPARATOR}{normalize_sequence(sequence)}"
        for command_id, sequence in sorted((overrides or {}).items())
        if command_id
    ]


def parse_shortcut_overrides(value) -> dict[str, str]:
    """The inverse of `serialize_shortcut_overrides`, tolerant of what
    QSettings hands back: a list of ``"command_id=Ctrl+G"`` strings, a single
    such string, an already-parsed dict, or None/garbage (-> empty)."""
    if isinstance(value, dict):
        return {
            str(k): normalize_sequence(v) for k, v in value.items() if str(k)
        }
    if isinstance(value, str):
        value = [value]
    result: dict[str, str] = {}
    for raw in value or []:
        if not isinstance(raw, str) or _ASSIGNMENT_SEPARATOR not in raw:
            continue
        command_id, _, sequence = raw.partition(_ASSIGNMENT_SEPARATOR)
        command_id = command_id.strip()
        if command_id:
            result[command_id] = normalize_sequence(sequence)
    return result


def resolve_shortcut_overrides(
    overrides: Mapping[str, str] | None,
    known_commands: Iterable[str],
) -> dict[str, str]:
    """Filter a loaded override map to what may still be applied, the way
    `resolve_icon_assignments` filters saved icon assignments.

    Legacy (pre-BUG-027) command ids map onto their menu-path id first, then
    any `RENAMED_ID_ALIASES` row, so an override made against a command's old
    menu path survives the rename. Dropped: overrides for a command that no
    longer exists, for a command that may not be rebound, and for a sequence
    §27 reserves -- the last one because a settings file is editable by hand
    and a hand-written `Ctrl+F` would install the ambiguity this whole module
    exists to prevent.
    """
    known = set(known_commands)
    result: dict[str, str] = {}
    for command_id, sequence in (overrides or {}).items():
        mapped = LEGACY_ID_ALIASES.get(command_id, command_id)
        mapped = RENAMED_ID_ALIASES.get(mapped, mapped)
        if mapped not in known:
            continue
        if refusal_for(mapped, sequence) is not None:
            continue
        result[mapped] = normalize_sequence(sequence)
    return result
