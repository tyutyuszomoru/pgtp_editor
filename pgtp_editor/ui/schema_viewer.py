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

"""SchemaViewerWindow: a read-only, non-modal window that shows schema text.

Phase 1 of Schema Settings Labeling. Hosts a read-only ``XmlEditor`` so the
generated XSD / stored labels JSON get the same syntax highlighting and folding
as the Raw XML editor. Intentionally non-modal (a top-level ``QMainWindow`` shown
via ``show()``, never ``exec()``); MainWindow holds a reference so it is not
garbage-collected and reuses/refreshes the same window on subsequent opens.
"""
from __future__ import annotations

from PySide6.QtWidgets import QMainWindow

from pgtp_editor.ui.xml_editor import XmlEditor


class SchemaViewerWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.editor = XmlEditor(self)
        self.editor.setReadOnly(True)
        self.setCentralWidget(self.editor)
        self.resize(800, 600)

    def set_title(self, title: str) -> None:
        self.setWindowTitle(title)

    def set_content(self, text: str) -> None:
        self.editor.setPlainText(text)
