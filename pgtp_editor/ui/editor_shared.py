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

# pgtp_editor/ui/editor_shared.py
"""`SharedEditorMixin`: the family-agnostic editor layer FQ-032 forced into
existence -- ONE hint/refusal path and ONE line-wrap toggle, for BOTH families
(§8).

**Why this module exists at all: FQ-032 forced two lifts, and both were real
gaps.** The editing-mode layer (`ui/vim_mode.py`) serves `XmlEditor` and
`CodeEditor` alike, and *"a family-agnostic layer may not be given a private
copy of something one family already implements"*:

1. **Hints and stated refusals.** A Command-mode gesture that cannot run -- `f`
   finding no character, `G` past the end, `:` matching no command -- **must
   state why** (DEC-013 / FQ-023). `CodeEditor` had `report_refusal` /
   `show_hint`; **`XmlEditor` had neither** (only `read_only_edit_attempted`).
   Giving the vim mixin a private hint would have been the app's *second* hint
   path and would have made a refusal look different depending on which tab
   raised it.
2. **Line wrap.** `:set wrap` / `:set nowrap` is the whole of v1's `:set`, and it
   may only reach an option the app **already has**: `XmlEditor` had
   `set_line_wrap_enabled` / `is_line_wrap_enabled` (the editor context menu's
   checkable *Wrap Lines*), while `CodeEditor` set `LineWrapMode.NoWrap` in its
   constructor and offered no toggle. Both families now share this one.

§8's standing discipline (*"one `_EditorGutter`"*, *"one gutter `paintEvent`"*,
*"one lexer"*) applies. The hint code is `CodeEditor`'s and the wrap code is
`XmlEditor`'s, moved rather than rewritten -- signals included, so
`CodeEditor.expansion_refused` and `CodeEditor.hint_shown` mean exactly what they
meant before and every existing host connection is unchanged.

Follows the `GutterBookmarkFoldMixin` / `CompletionPopupHostMixin` idiom: no
``__init__`` of its own, mixed in **before** the Qt base class.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QPlainTextEdit, QToolTip


class SharedEditorMixin:
    """Transient caret hints, stated refusals and line wrap -- one of each."""

    #: Emitted when a gesture REFUSES, carrying the reason fit to show the user
    #: -- never on success. The same "report outward, never reach into
    #: MainWindow" precedent as `DdlObjectEditorPanel.format_refused`; a host
    #: that connects nothing still sees the reason, because `report_refusal`
    #: also shows it as a transient tooltip at the caret (the status bar is
    #: static since FQ-028).
    expansion_refused = Signal(str)

    #: Emitted for every transient caret hint -- a refusal (which also emits
    #: `expansion_refused`) or an answer, e.g. signature help (FQ-030 slice 3).
    #: It exists because `QToolTip` shows nothing at all under the offscreen
    #: platform, so this is the only thing a test can observe; hosts are free to
    #: ignore it, and all of them do.
    hint_shown = Signal(str)

    def report_refusal(self, reason: str) -> None:
        """State why a gesture could not run (FQ-023), never nothing.

        Two channels, and both still earn their place now that a host DOES
        connect the signal (`MainWindow._report_editor_gesture_refusal` files
        it as an Audit `[SQL]` row, since the status bar is static since
        FQ-028): the signal is the durable record, readable after the fact and
        reachable by a test; the caret tooltip is the immediate one, at the
        place the author is looking, for a refusal that answers a keystroke
        they just pressed. A dock row alone would make a Ctrl+Alt+E that
        matched no snippet look like nothing happened; a tooltip alone would
        vanish before it could be re-read. The hosts that connect nothing (Raw
        XML, the PHP tabs) still get the tooltip.
        """
        self.show_hint(reason or "this gesture cannot run here", refusal=True)

    def show_hint(self, text: str, *, refusal: bool = False) -> None:
        """Show `text` as a transient tooltip at the caret -- the ONE hint path.

        Signature help (FQ-030 slice 3) is a query, not an insertion: it has
        nothing to put in the buffer and everything to say, so it says it here,
        through the same channel a refusal uses. `refusal=True` additionally
        emits `expansion_refused`, which is what makes a REFUSAL (and only a
        refusal) reach the Audit surface -- an answered question is not a
        notice and does not belong in a journal.
        """
        if not text:
            return
        if refusal:
            self.expansion_refused.emit(text)
        if self.isVisible():
            # A tooltip anchored to a hidden widget has nowhere to appear, and
            # asking for one under the offscreen platform only produces a Qt
            # warning. `hint_shown` above is the channel that always fires, and
            # is what tests assert on.
            QToolTip.showText(
                self.viewport().mapToGlobal(self.cursorRect().bottomLeft()),
                text,
                self,
            )
        self.hint_shown.emit(text)

    # --- Line wrap (the `:set wrap` / `:set nowrap` option) -----------------
    def set_line_wrap_enabled(self, enabled: bool) -> None:
        """Turn soft wrapping on or off. `XmlEditor`'s context-menu *Wrap Lines*
        entry and FQ-032's `:set wrap` / `:set nowrap` are the two command forms
        of this one toggle."""
        self.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth
            if enabled
            else QPlainTextEdit.LineWrapMode.NoWrap
        )

    def is_line_wrap_enabled(self) -> bool:
        return self.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth
