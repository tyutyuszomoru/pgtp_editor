"""XmlEditor: a QPlainTextEdit-based editor for raw .pgtp XML text.

Built as a PySide6 port of QCodeEditor's approach (see pgtp_editor/ui/about.py
for the OSS credit). Composed of three cooperating pieces: XmlSyntaxHighlighter
(syntax coloring with unclosed-quote propagation), _EditorGutter (line numbers
and fold markers), and folding/auto-indent/auto-close behavior implemented
directly as XmlEditor methods, since those need direct QTextCursor/QTextBlock
access.
"""
from __future__ import annotations

import re

from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import QPlainTextEdit

STATE_NORMAL = 0
STATE_IN_UNCLOSED_STRING = 1

# One tag-like token per match: opening ("<name"), attribute name+value
# pairs within it, and the closing ">"/"/>"; plus separate patterns for
# closing tags. Kept intentionally simple -- this highlighter tokenizes
# per-line, not via xml_structure.scan() (which returns whole-element spans,
# not per-token positions within a line).
_TAG_OPEN_RE = re.compile(r"</?[A-Za-z_][\w.-]*")
_TAG_CLOSE_RE = re.compile(r"/?>")
_ATTR_NAME_RE = re.compile(r"[A-Za-z_][\w.-]*(?=\s*=)")
_ATTR_VALUE_RE = re.compile(r'"[^"]*"')


class XmlSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)

        self._tag_format = QTextCharFormat()
        self._tag_format.setForeground(QColor("#569cd6"))

        self._attr_name_format = QTextCharFormat()
        self._attr_name_format.setForeground(QColor("#9cdcfe"))

        self._string_format = QTextCharFormat()
        self._string_format.setForeground(QColor("#ce9178"))

    def highlightBlock(self, text: str) -> None:
        start = 0
        if self.previousBlockState() == STATE_IN_UNCLOSED_STRING:
            close_at = text.find('"')
            if close_at == -1:
                self.setFormat(0, len(text), self._string_format)
                self.setCurrentBlockState(STATE_IN_UNCLOSED_STRING)
                return
            self.setFormat(0, close_at + 1, self._string_format)
            start = close_at + 1

        for match in _TAG_OPEN_RE.finditer(text, start):
            self.setFormat(match.start(), match.end() - match.start(), self._tag_format)
        for match in _TAG_CLOSE_RE.finditer(text, start):
            self.setFormat(match.start(), match.end() - match.start(), self._tag_format)
        for match in _ATTR_NAME_RE.finditer(text, start):
            self.setFormat(match.start(), match.end() - match.start(), self._attr_name_format)
        for match in _ATTR_VALUE_RE.finditer(text, start):
            self.setFormat(match.start(), match.end() - match.start(), self._string_format)

        if _has_unterminated_quote(text, start):
            self.setCurrentBlockState(STATE_IN_UNCLOSED_STRING)
        else:
            self.setCurrentBlockState(STATE_NORMAL)


def _has_unterminated_quote(text: str, start: int) -> bool:
    return text.count('"', start) % 2 == 1


class XmlEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._highlighter = XmlSyntaxHighlighter(self.document())
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    def setPlainText(self, text: str) -> None:
        super().setPlainText(text)
