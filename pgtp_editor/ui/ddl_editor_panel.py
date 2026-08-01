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

from PySide6.QtWidgets import QVBoxLayout, QWidget

from pgtp_editor.ui.code_editor import CodeEditor
from pgtp_editor.ui.find_replace_bar import FindReplaceBar


class EditorPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.editor = CodeEditor(language="sql")
        # Read-only by design (§18.1): phase-2 inline write-back, if ever
        # built, is a separate, diff-gated feature — this tab never edits.
        self.editor.setReadOnly(True)
        self.find_replace_bar = FindReplaceBar(self.editor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.editor)
        layout.addWidget(self.find_replace_bar)

    def set_ddl_text(self, text: str) -> None:
        """Replace the synthesized buffer (a fresh `build_ddl_text` result)."""
        self.editor.setPlainText(text)

    def navigate_to_line(self, line: int) -> None:
        """Jump to `line` (1-based) — BrowserPanel's `navigate_requested`
        target, delegating to CodeEditor's shared navigation API (§8)."""
        self.editor.navigate_to_line(line)
        self.editor.setFocus()
