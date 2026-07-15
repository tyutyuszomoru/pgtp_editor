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
