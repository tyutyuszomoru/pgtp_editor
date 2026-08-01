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

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QKeyEvent,
    QKeySequence,
    QPalette,
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

from pgtp_editor.ui.editor_gutter import GutterBookmarkFoldMixin

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

# SQL / plpgsql (spec §18.1: the DDL Explorer's synthesized buffer). Stored
# lowercase; SQL keyword matching is case-insensitive (pg_get_functiondef
# emits uppercase CREATE OR REPLACE FUNCTION..., hand-written bodies vary).
_SQL_KEYWORDS = frozenset(
    """
    add all alter and any array as asc begin between by call cascade case cast
    check column commit constraint create cross declare default delete
    desc distinct do drop else elsif end except execute exists exception fetch
    for foreign from full function grant group having if immutable in index
    inner insert instead into is join key language leakproof left like limit
    loop not null of offset on or order out outer perform primary procedure
    raise references replace restrict return returning returns revoke right
    rollback row rows security select sequence set stable strict table then to
    trigger truncate union unique update using values view volatile when where
    while with
    true false
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
        if language == "js":
            self._keywords = _JS_KEYWORDS
        elif language == "sql":
            self._keywords = _SQL_KEYWORDS
        else:
            self._keywords = _PHP_KEYWORDS

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
        if language == "sql":
            # SQL strings escape a quote by doubling it (''), not backslash;
            # double-quoted text is an identifier, left unstyled.
            self._string_re = re.compile(r"'(?:''|[^'])*'")
        else:
            self._string_re = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"")
        self._variable_re = re.compile(r"\$[A-Za-z_]\w*")
        # Line comment: '--' for SQL; '//' otherwise, '#' additionally for PHP.
        if language == "sql":
            self._line_comment_re = re.compile(r"--.*")
        elif language == "php":
            self._line_comment_re = re.compile(r"(//|#).*")
        else:
            self._line_comment_re = re.compile(r"//.*")

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

        # Keywords / identifiers. SQL keywords match case-insensitively
        # (pg_get_functiondef emits uppercase; hand-written bodies vary).
        for m in self._keyword_re.finditer(text, start):
            word = m.group().lower() if self._language == "sql" else m.group()
            if word in self._keywords:
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


class CodeEditor(GutterBookmarkFoldMixin, QPlainTextEdit):
    """QPlainTextEdit tuned for editing a single code body in one language
    ("js" | "php" | "sql").

    Carries the shared gutter/bookmark/fold base (`ui/editor_gutter.py`, §8) --
    the same one `XmlEditor` uses, never a second parallel gutter. Foldable
    regions are supplied from outside via `set_fold_regions`; for the DDL
    Explorer's "sql" buffer `EditorPanel` derives them from the `DdlObjectSpan`
    index (one region per object body, banner → `end_line`, §18.1).
    """

    # Tab-stop width, in characters, for the DDL/"sql" mode (§18.1): Qt's
    # monospace default is ~8-11 characters, which makes pg_get_functiondef's
    # tab-indented bodies unreadably wide.
    _SQL_TAB_STOP_CHARS = 4

    def __init__(self, language: str, parent=None):
        super().__init__(parent)
        self._language = language

        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFixedPitch(True)
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        if language == "sql":
            self.setTabStopDistance(
                self._SQL_TAB_STOP_CHARS
                * self.fontMetrics().horizontalAdvance(" ")
            )

        self._highlighter = _CodeHighlighter(self.document(), language)

        # Foldable regions, keyed by the 0-based block number the region starts
        # on -> (first_contained_block, last_contained_block). Empty by default,
        # so js/php code bodies simply have nothing to fold.
        self._fold_regions: dict[int, tuple[int, int]] = {}

        # Closer characters this editor auto-inserted, tracked as QTextCursors
        # so their positions self-adjust across later edits. Consulted by the
        # type-through logic so a typed closer only skips over a closer THIS
        # editor inserted, never an arbitrary pre-existing one.
        self._auto_closed_cursors: list[QTextCursor] = []

        self._init_gutter_bookmarks_folding()
        self._apply_gutter_theme_colors(self._palette_is_light())

    # --- Shared gutter/bookmark/fold base hooks (§8) -----------------------
    def set_fold_regions(self, regions) -> None:
        """Install this editor's foldable regions: an iterable of
        ``(start_block, first_contained_block, last_contained_block)`` triples
        (all 0-based block numbers). Replaces any previous set and drops the
        fold state, since the old block numbers no longer mean anything."""
        self._fold_regions = {
            int(start): (int(first), int(last)) for start, first, last in regions
        }
        self._fold_state = {}

    def _foldable_region_starting_at(self, block):
        """The pluggable foldable-region provider the shared base calls."""
        if not block.isValid():
            return None
        return self._fold_regions.get(block.blockNumber())

    def _palette_is_light(self) -> bool:
        return self.palette().color(QPalette.ColorRole.Base).lightness() > 128

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (
            QEvent.Type.ApplicationPaletteChange,
            QEvent.Type.PaletteChange,
        ):
            # Can fire during base-class construction, before the gutter exists.
            if hasattr(self, "_gutter"):
                self._apply_gutter_theme_colors(self._palette_is_light())

    def navigate_to_line(self, line: int) -> None:
        """Move the caret to `line` (1-based) -- the same public navigation
        entry point XmlEditor exposes (§8), used by the DDL Explorer's
        BrowserPanel → EditorPanel jump (§18.1).

        In the "sql" / DDL mode the target line is scrolled to the **TOP** of
        the viewport rather than centered, so a clicked DDL object's banner
        sits at the top edge with its whole body visible below (§18.1).
        `XmlEditor.navigate_to_line` stays centered -- its Properties/tree-jump
        callers expect centering.
        """
        block = self.document().findBlockByNumber(max(0, line - 1))
        cursor = QTextCursor(block)
        self.setTextCursor(cursor)
        if self._language == "sql":
            self._scroll_line_to_top(block)
        else:
            self.centerCursor()

    def _scroll_line_to_top(self, block) -> None:
        """Scroll so ``block`` sits at the top of the viewport. Uses the
        vertical scrollbar (which counts VISIBLE blocks in a QPlainTextEdit),
        clamped to the bar's range so a target near EOF just scrolls to the
        bottom instead of being rejected."""
        self.ensureCursorVisible()
        bar = self.verticalScrollBar()
        if bar is None:
            return
        target = self._visible_block_offset(block)
        bar.setValue(max(bar.minimum(), min(target, bar.maximum())))

    def _visible_block_offset(self, block) -> int:
        """Number of VISIBLE blocks before ``block`` -- the scrollbar value
        that puts it at the top. Folded (hidden) blocks do not take a scroll
        step, so a plain blockNumber() would overshoot."""
        offset = 0
        walker = self.document().firstBlock()
        while walker.isValid() and walker.blockNumber() < block.blockNumber():
            if walker.isVisible():
                offset += 1
            walker = walker.next()
        return offset

    def replace_current_selection(self, text: str) -> None:
        """Replace the current selection with `text` (FindReplaceBar's
        Replace contract, mirroring XmlEditor). No-op without a selection and
        on a read-only editor -- QTextCursor edits bypass setReadOnly, so the
        guard here is what actually protects read-only DDL buffers (§18.1)."""
        if self.isReadOnly():
            return
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return
        cursor.insertText(text)
        self.setTextCursor(cursor)

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
