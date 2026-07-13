# pgtp_editor/ui/find_replace_bar.py
"""FindReplaceBar: a modeless find/replace bar shown below the XmlEditor
inside the Raw XML tab. Operates on an injected editor via a small, explicit
interface (toPlainText / textCursor / setTextCursor / setFocus / document /
replace_current_selection) so it stays decoupled from MainWindow. Find All is
delegated to an injected callback."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pgtp_editor.ui import search


class FindReplaceBar(QWidget):
    def __init__(self, editor, on_find_all: Callable[[str], None] | None = None, parent=None):
        super().__init__(parent)
        self._editor = editor
        self._on_find_all = on_find_all or (lambda term: None)

        self._find_field = QLineEdit()
        self._find_field.setPlaceholderText("Find")
        self._find_next_button = QPushButton("Find Next")
        self._find_all_button = QPushButton("Find All")

        self._replace_field = QLineEdit()
        self._replace_field.setPlaceholderText("Replace with")
        self._replace_button = QPushButton("Replace")
        self._replace_all_button = QPushButton("Replace All")

        find_row = QHBoxLayout()
        find_row.addWidget(self._find_field)
        find_row.addWidget(self._find_next_button)
        find_row.addWidget(self._find_all_button)

        self._replace_row_widget = QWidget()
        replace_row = QHBoxLayout(self._replace_row_widget)
        replace_row.setContentsMargins(0, 0, 0, 0)
        replace_row.addWidget(self._replace_field)
        replace_row.addWidget(self._replace_button)
        replace_row.addWidget(self._replace_all_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addLayout(find_row)
        layout.addWidget(self._replace_row_widget)

        self._find_next_button.clicked.connect(self.find_next)
        self._find_all_button.clicked.connect(self.find_all)
        self._replace_button.clicked.connect(self.replace)
        self._replace_all_button.clicked.connect(self.replace_all)
        self._find_field.returnPressed.connect(self.find_next)

        self.hide()

    def set_on_find_all(self, callback: Callable[[str], None]) -> None:
        self._on_find_all = callback

    # -- show / hide --------------------------------------------------------

    def show_find(self) -> None:
        self._replace_row_widget.hide()
        self._prefill_from_selection()
        self.show()
        self._find_field.setFocus()
        self._find_field.selectAll()

    def show_replace(self) -> None:
        self._replace_row_widget.show()
        self._prefill_from_selection()
        self.show()
        self._find_field.setFocus()
        self._find_field.selectAll()

    def _prefill_from_selection(self) -> None:
        selected = self._editor.textCursor().selectedText()
        if selected:
            self._find_field.setText(selected)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self._editor.setFocus()
            return
        super().keyPressEvent(event)

    # -- operations ---------------------------------------------------------

    def find_next(self) -> None:
        term = self._find_field.text()
        if not term:
            return
        text = self._editor.toPlainText()
        cursor = self._editor.textCursor()
        from_pos = max(cursor.selectionEnd(), cursor.position())
        index = search.find_next(text, term, from_pos, wrap=True)
        if index is None:
            return
        self._select_span(index, len(term))

    def find_all(self) -> None:
        term = self._find_field.text()
        if not term:
            return
        self._on_find_all(term)

    def replace(self) -> None:
        term = self._find_field.text()
        if not term:
            return
        cursor = self._editor.textCursor()
        selected = cursor.selectedText()
        if selected and selected.lower() == term.lower():
            self._editor.replace_current_selection(self._replace_field.text())
        self.find_next()

    def replace_all(self) -> None:
        term = self._find_field.text()
        if not term:
            return
        replacement = self._replace_field.text()
        text = self._editor.toPlainText()
        matches = search.find_all_matches(text, term)
        if not matches:
            return
        cursor = QTextCursor(self._editor.document())
        cursor.beginEditBlock()
        for match in reversed(matches):
            cursor.setPosition(match.start)
            cursor.setPosition(match.start + len(term), QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(replacement)
        cursor.endEditBlock()

    def _select_span(self, index: int, length: int) -> None:
        cursor = self._editor.textCursor()
        cursor.setPosition(index)
        cursor.setPosition(index + length, QTextCursor.MoveMode.KeepAnchor)
        self._editor.setTextCursor(cursor)
        self._editor.ensureCursorVisible()
