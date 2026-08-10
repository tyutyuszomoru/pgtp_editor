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
    # §27: undo and redo. Two DIFFERENT operations (DEC-014), so two rows with
    # two reasons -- never one "the undo/redo chords" statement. Each is a
    # window-scoped QShortcut *plus* every editing surface's own key handling,
    # so neither is a menu action the dialog could clear. The project-wide twin
    # on the History menu is a DIFFERENT command with a different scope
    # (BUG-064) and it IS rebindable, which each reason names so the user is
    # not left thinking this row is the one that moves it.
    "Ctrl+Z": "undo in the surface that has focus — a window-scoped shortcut "
              "plus every editor's own key handling, not a menu action. The "
              "project-wide command is History ▸ Undo Project Edit, which IS "
              "rebindable (§27)",
    "Ctrl+Y": "redo in the surface that has focus — bound by this app on every "
              "platform (DEC-015), as a window-scoped shortcut plus every "
              "editor's own key handling, not a menu action. The project-wide "
              "command is History ▸ Redo Project Edit, which IS rebindable "
              "(§27)",
    # DEC-015 freed this chord from redo: redo is `Ctrl+Y` and nothing else,
    # everywhere. The reservation SURVIVES the change of meaning, and for a
    # sharper reason than before -- Qt's compiled binding table carries
    # Ctrl+Shift+Z as native `StandardKey.Redo` under `KB_Win | KB_X11`, so
    # every editing surface must actively intercept it to keep Qt's redo from
    # firing (BUG-056 measured this on both schemes). A command moved here
    # would therefore be swallowed by whichever editor has focus.
    "Ctrl+Shift+Z": "Select ▸ Shrink Selection, answered inside every text "
                    "editor's own key handling — no longer a redo chord "
                    "(DEC-015), and still intercepted there so Qt's native redo "
                    "cannot fire, so a command moved here would be swallowed by "
                    "the focused editor (FQ-034, §27)",
    # Qt's legacy Windows-scheme undo/redo pair: `Alt+Backspace` = Undo,
    # `Alt+Shift+Backspace` = Redo, both carrying `KB_Win` **only** in the
    # compiled binding table (BUG-056 read it out of `libQt6Gui`). So Qt answers
    # them inside every QPlainTextEdit on Windows and not at all on X11.
    #
    # **DECIDED — SUPPRESSED ON BOTH PLATFORMS (the call DEC-014 left open).**
    # Owner rule (2026-08-10): *"Keybindings must be the same on both systems"*
    # — a chord means the same thing on Windows and Linux, or it is not bound at
    # all. That rules out the status quo, because leaving these to Qt is exactly
    # where the asymmetry comes from. Two legal outcomes remained: bind them
    # explicitly everywhere, or suppress them everywhere. **Suppress.** They are
    # legacy Windows-only spellings with no discoverability in this app — in no
    # menu, no manual page, no shortcut table — so binding them on Linux would be
    # *inventing* a keybinding rather than honouring a convention, and DEC-015
    # already settled one chord per operation. Suppressing costs a chord nobody
    # looks for; leaving it costs two different keyboards on the owner's two
    # machines.
    #
    # They are therefore in `EDITOR_CHORDS` below as `SUPPRESSED`:
    # every editing surface intercepts them and runs nothing, which is what makes
    # "dead" true on Windows too rather than only on Linux. They stay reserved
    # here for the consequence of that: a menu command retargeted onto one would
    # be swallowed by whichever editor has focus (BUG-050's defect).
    "Alt+Backspace": "deliberately dead app-wide — Qt binds it as native Undo "
                     "on the Windows keyboard scheme only, so every editor "
                     "suppresses it to keep the keyboard identical on both "
                     "platforms (§27)",
    "Alt+Shift+Backspace": "deliberately dead app-wide — Qt binds it as native "
                           "Redo on the Windows keyboard scheme only, so every "
                           "editor suppresses it to keep the keyboard identical "
                           "on both platforms (§27)",
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
    # The reason names ALL FIVE hosts (FQ-033 added the three `XmlEditor` ones,
    # and this string went on listing two). It is what the Customize Shortcuts
    # dialog shows the user when it refuses the key, so an incomplete list here
    # is a wrong answer to a direct question -- and `docs/KEYBINDINGS.md` and
    # `ui/format_settings.py` both already say five.
    "Ctrl+Alt+F": "Format Selection — a context-menu command plus a shortcut on "
                  "five editing surfaces: the Sandbox SQL Console, the DDL "
                  "object tabs, and the Raw XML, Edit XSD and draft fragment "
                  "tabs; there is no menu-bar action to move (§27)",
    # BUG-062. The same shape as `Ctrl+Alt+F` above, and reserved for the same
    # reason: the chord's ONE keyboard host is a widget-scoped `QShortcut` (on
    # the DDL Explorer's read-only viewing pane, `ddl_editor_panel.py`), so the
    # menu walk cannot enumerate it and there is no row for the dialog to move.
    # The command's menu-bar form (Database ▸ Reload DDL) and its two
    # context-menu forms carry NO shortcut, per DEC-012's one-keyboard-host rule.
    # A rebinding pointed here would be swallowed by whichever Explorer buffer
    # has focus.
    "Ctrl+Shift+R": "Reload DDL — a shortcut scoped to the DDL Explorer's "
                    "viewing pane, where the caret says WHICH Explorer to "
                    "re-introspect; the menu-bar and context-menu forms of the "
                    "command carry no shortcut (§18.1)",
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
    #
    # `Ctrl+C` and `Ctrl+V` have a SECOND host, and the reason text says so
    # because it is what the Customize Shortcuts dialog shows the user when it
    # refuses the key: the caption grid binds both to real slots
    # (`caption_management_panel.py`). `Ctrl+X` deliberately does NOT get the
    # same sentence -- nothing in the app hosts a Cut shortcut, so "a Qt
    # built-in" is the whole truth there and symmetry would make it a lie.
    # Two operations, two reasons (DEC-014): never one merged "the clipboard
    # chords" statement.
    "Ctrl+C": "Copy — Qt's built-in inside every editor widget, and a shortcut "
              "on the Caption Management grid (§26/§27)",
    "Ctrl+X": "Cut — a Qt built-in inside every editor widget (§26/§27)",
    "Ctrl+V": "Paste — Qt's built-in inside every editor widget, and a shortcut "
              "on the Caption Management grid; the Raw XML editor also refuses "
              "it with the read-only hint in Caption Mode (§26/§27)",
    # The older spellings of the same three clipboard operations. Qt binds them
    # as `StandardKey.Copy` / `.Paste` / `.Cut` on **both** keyboard schemes
    # (measured 2026-08-10), so unlike `Ctrl+Shift+Ins` / `F16` / `F18` / `F20`
    # they are not a platform split and need no bind-or-suppress ruling -- but
    # they were free targets in Customize Shortcuts, which is a live hole:
    # putting a menu command on `Shift+Ins` would kill paste-by-`Shift+Ins` in
    # every editor on every platform. Reserving them is the pure widening of the
    # stance three rows above.
    "Ctrl+Insert": "Copy — Qt's older spelling of the chord, a built-in inside "
                   "every editor widget on both keyboard schemes (§26/§27)",
    "Shift+Insert": "Paste — Qt's older spelling of the chord, a built-in "
                    "inside every editor widget on both keyboard schemes; the "
                    "Raw XML editor also refuses it with the read-only hint in "
                    "Caption Mode (§26/§27)",
    "Shift+Delete": "Cut — Qt's older spelling of the chord, a built-in inside "
                    "every editor widget on both keyboard schemes (§26/§27)",
    # The X11-only clipboard spelling, and the OPPOSITE case to `Alt+Backspace`
    # above -- the analogy must not be applied mechanically. Qt lists this chord
    # under `StandardKey.Paste` on the Linux/KDE scheme and not on the Windows
    # one, so it pastes on Linux today and does nothing on Windows. Suppressing
    # it would therefore *remove a working gesture* on the platform this project
    # is developed on, where `Alt+Backspace` was dead there to begin with.
    #
    # **DECIDED (owner, 2026-08-10) -- BOUND EXPLICITLY ON BOTH PLATFORMS**,
    # unconditionally and with no `sys.platform` test: redundant on X11, new on
    # Windows. Exactly the shape DEC-015 used for `Ctrl+Y`. It is in
    # `EDITOR_CHORDS` below as `PASTE`, answered at all six editing surfaces,
    # and in `EDITOR_PASTE_CHORDS` so the read-only surfaces raise the same hint
    # for it as for `Ctrl+V`.
    "Ctrl+Shift+Insert": "Paste — bound by this app on every platform "
                         "(DEC-015), inside every editing surface's own key "
                         "handling; Qt itself binds it on the Linux/KDE "
                         "keyboard scheme only (§26/§27)",
    # The three readline/Emacs line-editing chords Qt answers on the KDE scheme
    # and not on the Windows one: `StandardKey.Delete` gains `Ctrl+D` there,
    # `DeleteEndOfLine` is `Ctrl+K` and `DeleteCompleteLine` is `Ctrl+U`, and the
    # Windows scheme binds NONE of them.
    #
    # **DECIDED (owner, 2026-08-10) -- BOUND ON BOTH PLATFORMS, IMPLEMENTED BY
    # THIS APP**, at all six editing surfaces, so Windows gains three gestures it
    # never had. The owner was offered reserve-only as a cheaper floor and
    # rejected it: reserve-only protects the customize dialog while leaving the
    # editing behaviour split, i.e. a stated rule half-applied, and a
    # half-applied rule is what the next sweep re-files. These are **letter
    # chords on keys every keyboard has**, live on Linux and reachable from
    # muscle memory, so the physically-absent-keys carve-out below cannot reach
    # them and the uniformity rule applies in full.
    #
    # The accepted cost, recorded so nobody "simplifies" it back: the app now
    # owns these primitives' edge cases forever, where before it got Qt's for
    # free. They are settled in ONE place, `code_editor.apply_editor_operation`,
    # which every surface calls -- see its docstring for each answer.
    "Ctrl+D": "Delete the character after the caret — implemented by this app "
              "at all six editing surfaces so the gesture is the same on every "
              "platform (DEC-015); Qt binds it on the Linux/KDE keyboard "
              "scheme only (§27)",
    "Ctrl+K": "Delete from the caret to the end of the line — implemented by "
              "this app at all six editing surfaces so the gesture is the same "
              "on every platform (DEC-015); Qt binds it on the Linux/KDE "
              "keyboard scheme only (§27)",
    "Ctrl+U": "Delete the whole line — implemented by this app at all six "
              "editing surfaces so the gesture is the same on every platform "
              "(DEC-015); Qt binds it on the Linux/KDE keyboard scheme only, "
              "and it is destructive, so it is one undo step (§27)",
    # §27: Manual. Universal convention, and `Help ▸ Manual` is the one menu
    # entry §7 pins as never filtered out of any launch mode.
    "F1": "Manual — pinned (§27)",
}

# -- the chords every editing surface must answer (DEC-014) -------------------
#
# **This table is deliberately NOT called `EDITOR_UNDO_REDO_CHORDS` any more**
# (renamed 2026-08-10, with `classify_undo_redo_chord` -> `classify_editor_chord`).
# The owner's X11-chord rulings put a paste chord and three line-editing chords
# into it, and the alternative -- a SECOND table with a second matcher -- was
# rejected for the reason DEC-014 exists: a surface would then have two calls to
# make, and the whole class of bug this machinery prevents (BUG-048, BUG-049,
# BUG-053, BUG-056) is a surface that forgot one. **One table, one matcher, one
# call site per surface** keeps "every intercepted chord is reserved" checkable
# in one place and makes a newly added chord automatically answered at all six
# surfaces. The names are wider; the invariant is unchanged.
#
# DEC-014's invariant, verbatim: *"For every chord `RESERVED_SEQUENCES` reserves
# because an editor answers it, every editing surface states its answer."* This
# table IS that set, sourced from the reservations above rather than written out
# again as a literal triple somewhere in the widget code -- so a surface, the
# dialog's greyed row and the reason the user reads all come from one place.
#
# It maps chord -> **operation**, never chord -> True, and that generalizes
# without change to the six operations it now holds. `Ctrl+Z` and `Ctrl+Y` are
# different operations, and DEC-014 forbids a bare "is this an undo/redo chord"
# boolean for a stated reason: a caller that trusts one and re-derives the
# operation itself is how a redo becomes an undo, silently, with the chord still
# claimed so nothing looks broken.
#
# Two of the answers are not an editing operation at all, and neither is a
# placeholder -- in both cases the interception is *itself* load-bearing, because
# Qt would otherwise answer the chord and the app's keyboard would differ per
# platform:
#
#   `CLAIMED_NOT_UNDO_REDO` -- `Ctrl+Shift+Z`. Reserved, intercepted, and since
#       FQ-034 it ANSWERS `Select ▸ Shrink Selection` (one shared implementation,
#       `code_editor.apply_shrink_structural_selection`). Qt binds it as native
#       Redo under `KB_Win | KB_X11`, so DEC-015's "redo is always Ctrl+Y" is true
#       only while every surface refuses it -- which is also exactly why shrink's
#       `QAction` carries NO `setShortcut`: a window action would be starved by
#       the `ShortcutOverride` the surfaces must accept.
#   `SUPPRESSED` -- `Alt+Backspace` / `Alt+Shift+Backspace`. Deliberately dead
#       app-wide (see their rows above). Qt binds them `KB_Win` only, so
#       suppressing them is what makes the keyboard identical on both systems,
#       per the owner's rule that a chord means the same thing on Windows and
#       Linux or is not bound at all.
#
# Four answers MUTATE the buffer -- `PASTE`, `DELETE_CHARACTER`,
# `DELETE_TO_END_OF_LINE`, `DELETE_LINE` -- and they are the owner's 2026-08-10
# X11-chord rulings: Qt binds all four on the Linux/KDE scheme only, and rather
# than suppress working, reachable gestures the app implements them itself on both
# platforms. Their single implementation is `code_editor.apply_editor_operation`;
# a read-only surface still answers them, by stating a refusal instead of editing.
#
# **The rule for adding a row here:** a chord Qt answers on one platform's scheme
# and not the other must be either bound by this app on both or suppressed on
# both -- never left to Qt. The test suite cannot check this (the offscreen
# platform runs Qt's *Windows* scheme, so a Linux-only dead key is invisible to
# it); reason from the binding table.
#
# **THE ONE STATED EXCEPTION -- physically-absent keys (owner, 2026-08-10).** The
# uniformity rule *does not reach keys no keyboard in use actually has*, so
# `F14` (Qt's KDE-scheme Undo) and `F16`/`F18`/`F20` (the Sun/HP Copy/Paste/Cut
# keys) deliberately have **no row here and no reservation**. This is a stated
# carve-out with a stated trigger for its own review, not an oversight:
#
#   **`F14`'s undo-routing bypass is KNOWINGLY ACCEPTED AS UNREACHABLE.** On the
#   KDE scheme `F14` runs `QPlainTextEdit`'s *native* undo inside every editing
#   surface -- no re-emission into the project's snapshot history, no read-only
#   refusal in Caption Mode, no journal line. That is exactly the defect BUG-056
#   fixed for `Ctrl+Shift+Z`, and it is accepted here only because no reachable
#   key fires it. **If a keyboard with an `F13`...`F20` block ever comes into use
#   this is a live defect again, and the carve-out is what must be revisited --
#   not the rule.** Do not re-file it as a defect while the carve-out stands, and
#   do not "tidy" a suppression row in for it: adding one would state that the
#   rule reaches absent keys, which the owner ruled it does not.
#
# The Qt-side matcher that consumes this lives in `ui/code_editor.py`
# (`classify_editor_chord`) -- this module stays Qt-free.
UNDO = "undo"
REDO = "redo"
CLAIMED_NOT_UNDO_REDO = "claimed"
SUPPRESSED = "suppressed"
PASTE = "paste"
DELETE_CHARACTER = "delete-character"
DELETE_TO_END_OF_LINE = "delete-to-end-of-line"
DELETE_LINE = "delete-line"

#: The operations that CHANGE the buffer, so a surface knows a stated refusal is
#: owed when its buffer is read-only. Derived from nothing -- named here once, and
#: consumed through `code_editor.is_mutating_editor_operation`.
MUTATING_EDITOR_OPERATIONS: frozenset[str] = frozenset(
    {PASTE, DELETE_CHARACTER, DELETE_TO_END_OF_LINE, DELETE_LINE}
)

EDITOR_CHORDS: dict[str, str] = {
    "Ctrl+Z": UNDO,
    "Ctrl+Y": REDO,
    "Ctrl+Shift+Z": CLAIMED_NOT_UNDO_REDO,
    "Alt+Backspace": SUPPRESSED,
    "Alt+Shift+Backspace": SUPPRESSED,
    "Ctrl+Shift+Insert": PASTE,
    "Ctrl+D": DELETE_CHARACTER,
    "Ctrl+K": DELETE_TO_END_OF_LINE,
    "Ctrl+U": DELETE_LINE,
}


# -- the paste chords this app owns (DEC-015) --------------------------------
#
# Read-only editing surfaces flash a *"this editor is read-only"* hint when a
# keystroke would have modified the document, and paste is one such keystroke.
# `XmlEditor` used to ask `event.matches(QKeySequence.StandardKey.Paste)`, which
# is Qt's per-scheme table and therefore a different set of keys on Windows and
# on Linux -- the hint fired for `Ctrl+Shift+Ins` and `F18` on one platform and
# not the other. This table is the app's own answer instead, spelled out, so the
# behaviour is identical on both.
#
# It was originally exactly Qt's Windows-scheme `StandardKey.Paste` set (the
# subset native on BOTH schemes), so nothing that used to raise the hint on
# Windows stopped doing so. `Ctrl+Shift+Insert` has since JOINED it, and for the
# reason this table exists rather than in spite of it: the owner ruled (2026-08-10)
# that the app binds that chord as paste on both platforms, so it is now one of
# the app's own paste chords and a read-only surface owes it the same hint as
# `Ctrl+V`. The remaining KDE-only spelling, the `F18` Paste key, is still absent
# -- the physically-absent-keys carve-out (see `EDITOR_CHORDS`) leaves it to Qt.
EDITOR_PASTE_CHORDS: tuple[str, ...] = (
    "Ctrl+V",
    "Ctrl+Shift+Insert",
    "Shift+Insert",
    "Paste",
)


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
