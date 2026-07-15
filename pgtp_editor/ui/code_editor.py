"""CodeEditor + CodeEditorDialog: a small dedicated editor for event-handler
JS/PHP code, opened as a modal-capable dialog from the XML editor / tree.

Composed of a QPlainTextEdit subclass (``CodeEditor``) with per-language
syntax highlighting and bracket/quote conveniences, and a hosting dialog
(``CodeEditorDialog``) with OK/Cancel and Ctrl+S / Ctrl+W shortcuts.

The auto-close behavior mirrors XmlEditor's approach: the editor tracks the
closer characters it itself inserted (as QTextCursors so their positions
self-adjust) so that "type-through" only skips over a closer this editor
auto-inserted, never an arbitrary pre-existing one.
"""
from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QKeyEvent,
    QKeySequence,
    QShortcut,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QPlainTextEdit,
    QVBoxLayout,
)

# Keyword lists kept as Qt-free module constants (unit-tested for existence /
# non-triviality); the highlighter consumes them below.
_JS_KEYWORDS = frozenset(
    """
    break case catch class const continue debugger default delete do else
    export extends finally for function if import in instanceof let new
    return super switch this throw try typeof var void while with yield
    async await of null true false undefined
    """.split()
)

_PHP_KEYWORDS = frozenset(
    """
    abstract and array as break callable case catch class clone const continue
    declare default do echo else elseif empty enddeclare endfor endforeach endif
    endswitch endwhile extends final finally fn for foreach function global goto
    if implements include include_once instanceof insteadof interface isset list
    namespace new or print private protected public require require_once return
    static switch throw trait try unset use var while xor yield
    null true false
    """.split()
)

# Opener -> closer pairs for auto-close / selection-wrap.
_BRACKET_PAIRS = {"(": ")", "[": "]", "{": "}"}
_QUOTES = {"'", '"'}
_CLOSERS = set(_BRACKET_PAIRS.values())


def enclosing_bracket_span(text: str, pos: int) -> tuple[int, int] | None:
    """Return the inner ``[start, end)`` span (INNER-EXCLUSIVE of the brackets
    themselves) of the innermost balanced bracket pair ``() [] {}`` that
    encloses ``pos``, or ``None`` when ``pos`` is not inside any balanced pair.

    "Inner-exclusive" means the returned span covers only the characters
    strictly between the matching open and close brackets, not the brackets.
    e.g. for ``a(b[c]d)e`` with ``pos`` on ``c`` the span is the single ``c``;
    with ``pos`` on ``b`` (inside ``()`` but outside ``[]``) the span is
    ``b[c]d``.

    ``pos`` is treated as a caret position (between characters). A pair
    encloses ``pos`` when its open bracket is strictly before ``pos`` and its
    close bracket is at or after ``pos``. Unbalanced text (a closer with no
    matching opener, or an opener never closed before ``pos``) yields ``None``.
    Mismatched types (``(`` closed by ``]``) do not form a pair.
    """
    stack: list[tuple[str, int]] = []  # (opener char, index of the char after it)
    for i, ch in enumerate(text):
        if ch in _BRACKET_PAIRS:
            stack.append((ch, i))
        elif ch in _CLOSERS:
            if not stack:
                # Closer with no opener: unbalanced up to here.
                if i >= pos:
                    return None
                continue
            opener, opener_index = stack[-1]
            if _BRACKET_PAIRS[opener] != ch:
                # Mismatched pair type.
                return None
            stack.pop()
            inner_start = opener_index + 1
            inner_end = i
            # This pair encloses the caret when the opener is strictly before
            # pos and the closer is at or after pos.
            if opener_index < pos <= i:
                return (inner_start, inner_end)
    return None


class _CodeHighlighter(QSyntaxHighlighter):
    """Per-language keyword / string / comment / number highlighter.

    Block comments (``/* ... */``) span lines, tracked via block state.
    """

    _STATE_NORMAL = 0
    _STATE_IN_BLOCK_COMMENT = 1

    def __init__(self, document, language: str):
        super().__init__(document)
        self._language = language
        self._keywords = _JS_KEYWORDS if language == "js" else _PHP_KEYWORDS

        self._keyword_format = QTextCharFormat()
        self._keyword_format.setForeground(QColor("#569cd6"))

        self._string_format = QTextCharFormat()
        self._string_format.setForeground(QColor("#ce9178"))

        self._comment_format = QTextCharFormat()
        self._comment_format.setForeground(QColor("#6a9955"))

        self._number_format = QTextCharFormat()
        self._number_format.setForeground(QColor("#b5cea8"))

        self._variable_format = QTextCharFormat()
        self._variable_format.setForeground(QColor("#9cdcfe"))

        self._keyword_re = re.compile(r"\b[A-Za-z_]\w*\b")
        self._number_re = re.compile(r"\b\d+(?:\.\d+)?\b")
        self._string_re = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"")
        self._variable_re = re.compile(r"\$[A-Za-z_]\w*")
        # Line comment: '//' always; '#' additionally for PHP.
        self._line_comment_re = (
            re.compile(r"(//|#).*") if language == "php" else re.compile(r"//.*")
        )

    def highlightBlock(self, text: str) -> None:
        # Continuation of a block comment from a previous line.
        start = 0
        if self.previousBlockState() == self._STATE_IN_BLOCK_COMMENT:
            end = text.find("*/")
            if end == -1:
                self.setFormat(0, len(text), self._comment_format)
                self.setCurrentBlockState(self._STATE_IN_BLOCK_COMMENT)
                return
            self.setFormat(0, end + 2, self._comment_format)
            start = end + 2

        self.setCurrentBlockState(self._STATE_NORMAL)

        # Numbers.
        for m in self._number_re.finditer(text, start):
            self.setFormat(m.start(), m.end() - m.start(), self._number_format)

        # Keywords / identifiers.
        for m in self._keyword_re.finditer(text, start):
            if m.group() in self._keywords:
                self.setFormat(m.start(), m.end() - m.start(), self._keyword_format)

        # PHP variables ($foo).
        if self._language == "php":
            for m in self._variable_re.finditer(text, start):
                self.setFormat(m.start(), m.end() - m.start(), self._variable_format)

        # Strings (override keyword/number formats inside them).
        for m in self._string_re.finditer(text, start):
            self.setFormat(m.start(), m.end() - m.start(), self._string_format)

        # Line comments (override everything to their right).
        line_comment = self._line_comment_re.search(text, start)
        if line_comment is not None:
            self.setFormat(
                line_comment.start(),
                len(text) - line_comment.start(),
                self._comment_format,
            )

        # Block comment opening on this line.
        block_open = text.find("/*", start)
        if block_open != -1 and (line_comment is None or block_open < line_comment.start()):
            block_close = text.find("*/", block_open + 2)
            if block_close == -1:
                self.setFormat(block_open, len(text) - block_open, self._comment_format)
                self.setCurrentBlockState(self._STATE_IN_BLOCK_COMMENT)
            else:
                self.setFormat(block_open, block_close + 2 - block_open, self._comment_format)


class CodeEditor(QPlainTextEdit):
    """QPlainTextEdit tuned for editing a single event-handler body in one
    language ("js" | "php")."""

    def __init__(self, language: str, parent=None):
        super().__init__(parent)
        self._language = language

        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFixedPitch(True)
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self._highlighter = _CodeHighlighter(self.document(), language)

        # Closer characters this editor auto-inserted, tracked as QTextCursors
        # so their positions self-adjust across later edits. Consulted by the
        # type-through logic so a typed closer only skips over a closer THIS
        # editor inserted, never an arbitrary pre-existing one.
        self._auto_closed_cursors: list[QTextCursor] = []


    def select_enclosing_brackets(self) -> None:
        """Ctrl+Shift+B: select the inner span of the innermost bracket pair
        enclosing the caret, caret-at-start (consistent with XmlEditor)."""
        text = self.toPlainText()
        pos = self.textCursor().position()
        span = enclosing_bracket_span(text, pos)
        if span is None:
            return
        start, end = span
        cursor = self.textCursor()
        # Anchor at END, move caret to START with KeepAnchor: the whole span is
        # selected but selectionStart() == the caret position (caret-at-start).
        cursor.setPosition(end)
        cursor.setPosition(start, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        # Ctrl+Shift+B: bracket-select. Handled here (in addition to the
        # QShortcut) so the behavior is reliably reachable when a key event is
        # delivered directly to the editor, e.g. under the offscreen platform
        # in tests where QShortcut activation is not guaranteed.
        if (
            event.key() == Qt.Key.Key_B
            and event.modifiers()
            == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        ):
            self.select_enclosing_brackets()
            return

        char = event.text()
        cursor = self.textCursor()

        # Selection-wrap: a non-empty selection + an opener/quote wraps the
        # selection (keeping it selected) rather than replacing it.
        if cursor.hasSelection() and (char in _BRACKET_PAIRS or char in _QUOTES):
            self._wrap_selection(cursor, char)
            return

        # Auto-close an opener or quote: insert the pair, caret between.
        if char in _BRACKET_PAIRS or char in _QUOTES:
            closer = _BRACKET_PAIRS[char] if char in _BRACKET_PAIRS else char
            cursor.insertText(char + closer)
            closer_position = cursor.position() - 1
            tracked = QTextCursor(self.document())
            tracked.setPosition(closer_position)
            self._auto_closed_cursors.append(tracked)
            cursor.movePosition(QTextCursor.MoveOperation.Left)
            self.setTextCursor(cursor)
            return

        # Type-through a closer this editor itself inserted.
        if char in _CLOSERS or char in _QUOTES:
            if self._type_through_closer(char):
                return

        super().keyPressEvent(event)

    def _wrap_selection(self, cursor: QTextCursor, char: str) -> None:
        closer = _BRACKET_PAIRS[char] if char in _BRACKET_PAIRS else char
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        selected = cursor.selectedText()
        cursor.beginEditBlock()
        cursor.insertText(char + selected + closer)
        cursor.endEditBlock()
        # Reselect the original text (now shifted right by one for the opener).
        new_cursor = self.textCursor()
        new_cursor.setPosition(start + 1)
        new_cursor.setPosition(end + 1, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(new_cursor)

    def _type_through_closer(self, char: str) -> bool:
        cursor = self.textCursor()
        position = cursor.position()
        if self._character_after_cursor(cursor) != char:
            return False
        if not self._consume_auto_closed_at(position):
            return False
        cursor.movePosition(QTextCursor.MoveOperation.Right)
        self.setTextCursor(cursor)
        return True

    def _consume_auto_closed_at(self, position: int) -> bool:
        """If a tracked auto-inserted closer sits at ``position``, drop it from
        tracking and return True. Also prunes stale entries whose tracked
        position no longer holds the same character."""
        found = False
        still_tracked: list[QTextCursor] = []
        for tracked in self._auto_closed_cursors:
            if tracked.isNull():
                continue
            after = self._character_after_cursor(tracked)
            if after not in _CLOSERS and after not in _QUOTES:
                continue  # stale
            if not found and tracked.position() == position:
                found = True
                continue  # consume
            still_tracked.append(tracked)
        self._auto_closed_cursors = still_tracked
        return found

    def _character_after_cursor(self, cursor: QTextCursor) -> str:
        probe = QTextCursor(self.document())
        probe.setPosition(cursor.position())
        probe.movePosition(
            QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor
        )
        return probe.selectedText()


class CodeEditorDialog(QDialog):
    """Modal-capable dialog hosting a CodeEditor plus OK/Cancel.

    Built so tests drive ``set_code``/``code``/``save``/``cancel`` and the
    shortcuts' slots directly -- ``.exec()`` is never required.
    """

    saved = Signal(str)
    cancelled = Signal()

    def __init__(self, language: str, handler_name: str = "", title: str | None = None, parent=None):
        super().__init__(parent)
        self._language = language
        if title is None:
            name = handler_name or "Event handler"
            title = f"{name} ({language})"
        self.setWindowTitle(title)

        self._editor = CodeEditor(language, self)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        button_box.accepted.connect(self.save)
        button_box.rejected.connect(self.cancel)

        layout = QVBoxLayout(self)
        layout.addWidget(self._editor)
        layout.addWidget(button_box)

        save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self, self.save)
        save_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        cancel_shortcut = QShortcut(QKeySequence("Ctrl+W"), self, self.cancel)
        cancel_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)

        # Open at 80% of the host (XML editor) window so there's room to work.
        self.setMinimumSize(480, 320)
        if parent is not None:
            reference = parent.window()
            if reference is not None:
                ref_size = reference.size()
                if ref_size.width() > 0 and ref_size.height() > 0:
                    self.resize(
                        int(ref_size.width() * 0.8),
                        int(ref_size.height() * 0.8),
                    )

    def keyPressEvent(self, event: QKeyEvent) -> None:
        # Ctrl+S / Ctrl+W handled here in addition to the WindowShortcut
        # QShortcuts above, so save/cancel are reliably reachable when a key
        # event is delivered to the dialog directly (e.g. under the offscreen
        # platform in tests, where QShortcut activation is not guaranteed).
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_S:
                self.save()
                return
            if event.key() == Qt.Key.Key_W:
                self.cancel()
                return
        super().keyPressEvent(event)

    def set_code(self, text: str) -> None:
        self._editor.setPlainText(text)

    def code(self) -> str:
        return self._editor.toPlainText()

    def save(self) -> None:
        self.saved.emit(self.code())
        self.accept()

    def cancel(self) -> None:
        self.cancelled.emit()
        self.reject()
