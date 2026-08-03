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

# pgtp_editor/ui/ddl_editor_panel.py
"""EditorPanel: the CenterStage "DDL Explorer" tab (spec §18.1).

Hosts the ONE synthesized routine/trigger buffer (`db/ddl_buffer.py::
build_ddl_text`) in the existing `CodeEditor` under its "sql" language mode,
with its own `FindReplaceBar` instance — the same per-tab document-routing
precedent as the Edit XSD tab (§7/§15). The buffer is read-only, DB-sourced,
live/synthesized: the checked-out, editable form lives in `ddl/*.sql` files
(§18.2), edited in a separate tab type. `BrowserPanel.navigate_requested`
(ui/ddl_buffer_panel.py) jumps here via `navigate_to_line`.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from pgtp_editor.ui.code_editor import CodeEditor
from pgtp_editor.ui.ddl_buffer_panel import resolve_edit_target
from pgtp_editor.ui.find_replace_bar import FindReplaceBar


def _fold_regions_for_spans(spans) -> list[tuple[int, int, int]]:
    """Translate `DdlObjectSpan`s into the shared fold base's
    ``(start_block, first_contained_block, last_contained_block)`` triples
    (0-based block numbers) -- the DDL-object foldable-region provider (§18.1).

    A span's `start_line` is the object's 1-based BANNER line and `end_line`
    the last line of its source. The fold is triggered on the banner block and
    contains the body only, so the banner stays visible when collapsed. Spans
    with no body (`end_line <= start_line`) contribute no region.
    """
    regions: list[tuple[int, int, int]] = []
    for span in spans:
        if span.end_line <= span.start_line:
            continue  # nothing below the banner to fold
        regions.append((span.start_line - 1, span.start_line, span.end_line - 1))
    return regions


class EditorPanel(QWidget):
    #: Right-click inside an object's span ▸ Edit <schema>.<name>(<argtypes>)…
    #: (spec §18.5, D1 entry point 2). Same payload shape as
    #: `BrowserPanel.edit_requested` -- the object's `DdlObjectRef` and its
    #: current source text.
    edit_requested = Signal(object, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.editor = CodeEditor(language="sql")
        # Read-only by design (§18.1): phase-2 inline write-back, if ever
        # built, is a separate, diff-gated feature — this tab never edits.
        self.editor.setReadOnly(True)
        self.find_replace_bar = FindReplaceBar(self.editor)

        # Retained so right-click ▸ Edit… (§18.5, D1 entry point 2) can find
        # which object the click landed inside; the schema that produced them
        # resolves the click to a `DdlObjectRef` + live source text (shared
        # helper with BrowserPanel's tree, `ddl_buffer_panel.resolve_edit_target`).
        self._spans = []
        self._schema = None
        self.editor.installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.editor)
        layout.addWidget(self.find_replace_bar)

    def set_ddl_text(self, text: str, spans=None, schema=None) -> None:
        """Replace the synthesized buffer (a fresh `build_ddl_text` result).

        `spans` is that call's `DdlObjectSpan` list; it drives the shared fold
        base's foldable regions (§18.1) -- ONE region per DDL object body, from
        the object's banner line (`start_line`) through its `end_line`, so
        folding an object collapses its source under its banner. Passing None
        (or an empty list) simply leaves nothing foldable. `schema` is the
        `DatabaseSchema` that produced `spans`, retained (with the spans) so
        a later right-click can resolve the clicked object (§18.5)."""
        self.editor.setPlainText(text)
        spans = spans or []
        self.editor.set_fold_regions(_fold_regions_for_spans(spans))
        self._spans = spans
        self._schema = schema

    def navigate_to_line(self, line: int) -> None:
        """Jump to `line` (1-based) — BrowserPanel's `navigate_requested`
        target, delegating to CodeEditor's shared navigation API (§8)."""
        self.editor.navigate_to_line(line)
        self.editor.setFocus()

    def _span_at_line(self, line: int):
        """The `DdlObjectSpan` whose `start_line..end_line` contains the
        1-based `line`, or None outside any object's body."""
        for span in self._spans:
            if span.start_line <= line <= span.end_line:
                return span
        return None

    def eventFilter(self, obj, event) -> bool:
        if obj is self.editor and event.type() == QEvent.Type.ContextMenu:
            menu = self._build_context_menu_at(event.pos())
            menu.exec(event.globalPos())
            return True
        return super().eventFilter(obj, event)

    def _build_context_menu_at(self, local_pos):
        """Build (but do not exec) the context menu for a click at
        `local_pos` (editor-widget coordinates) -- split out from
        `eventFilter` so tests can inspect it directly instead of ever
        driving a real modal `QMenu.exec` (the `xml_editor.py`
        `_build_context_menu` precedent)."""
        # event.pos() is delivered in the editor's own coordinates, but
        # cursorForPosition expects viewport coordinates (xml_editor.py's
        # contextMenuEvent precedent) -- move the caret to the clicked
        # position FIRST, so the resolved span reflects the click rather than
        # a stale caret (§18.5, D1).
        viewport_pos = self.editor.viewport().mapFrom(self.editor, local_pos)
        cursor = self.editor.cursorForPosition(viewport_pos)
        self.editor.setTextCursor(cursor)
        line = cursor.blockNumber() + 1
        span = self._span_at_line(line)
        menu = self.editor.createStandardContextMenu()
        if span is not None and self._schema is not None:
            resolved = resolve_edit_target(self._schema, span)
            if resolved is not None:
                ref, source = resolved
                menu.addSeparator()
                menu.addAction(
                    f"Edit {ref.qualified}…",
                    lambda: self.edit_requested.emit(ref, source),
                )
        return menu
