"""XmlEditor: a QPlainTextEdit-based editor for raw .pgtp XML text.

Built as a PySide6 port of QCodeEditor's approach (see pgtp_editor/ui/about.py
for the OSS credit). Composed of three cooperating pieces: XmlSyntaxHighlighter
(syntax coloring with unclosed-quote propagation), _EditorGutter (line numbers
and fold markers), and folding/auto-indent/auto-close behavior implemented
directly as XmlEditor methods, since those need direct QTextCursor/QTextBlock
access.
"""
from __future__ import annotations

from PySide6.QtWidgets import QPlainTextEdit


class XmlEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    def setPlainText(self, text: str) -> None:
        super().setPlainText(text)
