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

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QKeyEvent,
    QKeySequence,
    QPainter,
    QShortcut,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

from pgtp_editor.ui import xml_structure

STATE_NORMAL = 0
STATE_IN_UNCLOSED_STRING = 1

_TAG_OPEN_RE = re.compile(r"</?[A-Za-z_][\w.-]*")
_TAG_CLOSE_RE = re.compile(r"/?>")
_ATTR_NAME_RE = re.compile(r"[A-Za-z_][\w.-]*(?=\s*=)")
_ATTR_VALUE_RE = re.compile(r'"[^"]*"')

# Fixed horizontal allowance reserved for the fold-triangle glyph, added on
# top of the digit-count-dependent width for line numbers.
_FOLD_GLYPH_WIDTH = 16


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


def _cursor_immediately_after_open_tag(line_text: str, position_in_line: int, tag_name: str) -> bool:
    """True if the text on `line_text` immediately before `position_in_line`
    ends with the enclosing tag's own opening `>` and nothing else (i.e.
    there is no content yet between the open tag and the cursor)."""
    before_cursor = line_text[:position_in_line]
    stripped = before_cursor.rstrip()
    return stripped.endswith(">") and f"<{tag_name}" in stripped and not stripped.endswith("/>")


def _closing_tag_start(text: str, span: xml_structure.TagSpan) -> int | None:
    """Given a TagSpan with a known close_end, find where its own '</name>'
    token begins. Returns None if the span is self-closing or has no
    close_end. rfind over [open_end, close_end) is exact: the close tag's
    '</name>' is the last such occurrence before close_end, and the open
    tag's own '<' is a strictly earlier, distinct position."""
    if span.close_end is None or span.self_closing:
        return None
    close_tag_prefix = "</" + span.name
    start = text.rfind(close_tag_prefix, span.open_end, span.close_end)
    return start if start != -1 else None


class _EditorGutter(QWidget):
    """Line-number and fold-marker gutter, the standard QPlainTextEdit
    side-widget pattern (Qt's "Code Editor Example")."""

    def __init__(self, editor: "XmlEditor"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor._gutter_width(), 0)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor("#2b2b2b"))

        block = self._editor.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self._editor.blockBoundingGeometry(block).translated(
            self._editor.contentOffset()
        ).top()
        bottom = top + self._editor.blockBoundingRect(block).height()

        # Fold-triangle glyphs occupy the left [0, _FOLD_GLYPH_WIDTH) strip
        # of the gutter; line numbers occupy the remaining right-hand strip
        # and are right-aligned against the gutter's right edge.
        line_number_width = self.width() - _FOLD_GLYPH_WIDTH

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number_text = str(block_number + 1)
                painter.setPen(QColor("#858585"))
                painter.drawText(
                    _FOLD_GLYPH_WIDTH,
                    int(top),
                    line_number_width,
                    self._editor.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number_text,
                )

                if self._editor._foldable_region_starting_at(block) is not None:
                    collapsed = self._editor._fold_state.get(block_number, False)
                    self._draw_fold_glyph(painter, int(top), collapsed)

            block = block.next()
            top = bottom
            bottom = top + self._editor.blockBoundingRect(block).height()
            block_number += 1

    def _draw_fold_glyph(self, painter: QPainter, top: int, collapsed: bool) -> None:
        line_height = self._editor.fontMetrics().height()
        glyph_left = 0
        glyph_size = min(_FOLD_GLYPH_WIDTH - 4, line_height - 4)
        cx = glyph_left + _FOLD_GLYPH_WIDTH // 2
        cy = top + line_height // 2
        half = glyph_size // 2
        painter.setPen(QColor("#858585"))
        painter.setBrush(QColor("#858585"))
        if collapsed:
            # Right-pointing triangle.
            points = [QPoint(cx - half, cy - half), QPoint(cx - half, cy + half), QPoint(cx + half, cy)]
        else:
            # Down-pointing triangle.
            points = [QPoint(cx - half, cy - half), QPoint(cx + half, cy - half), QPoint(cx, cy + half)]
        painter.drawPolygon(points)

    def mousePressEvent(self, event) -> None:
        if event.position().x() >= _FOLD_GLYPH_WIDTH:
            return
        block = self._editor.firstVisibleBlock()
        top = self._editor.blockBoundingGeometry(block).translated(
            self._editor.contentOffset()
        ).top()
        bottom = top + self._editor.blockBoundingRect(block).height()
        click_y = event.position().y()

        while block.isValid() and top <= click_y:
            if block.isVisible() and top <= click_y < bottom:
                self._editor._toggle_fold(block)
                self.update()
                return
            block = block.next()
            top = bottom
            bottom = top + self._editor.blockBoundingRect(block).height()


class XmlEditor(QPlainTextEdit):
    line_clicked = Signal(int)  # 1-based line of a left-mouse click in the text

    def __init__(self, parent=None):
        super().__init__(parent)
        self._highlighter = XmlSyntaxHighlighter(self.document())
        self._gutter = _EditorGutter(self)
        self._fold_state: dict[int, bool] = {}
        self._current_line_color = QColor("#2d2d30")
        self._error_line_color = QColor("#5a1d1d")
        self._navigation_highlight_color = QColor("#264f78")
        self._matching_tag_color = QColor("#3a5f3a")
        self._current_line_selections: list[QTextEdit.ExtraSelection] = []
        self._matching_tag_selections: list[QTextEdit.ExtraSelection] = []
        # One-shot "overriding" indicator used by navigate_to_line,
        # highlight_error_line and select_range_on_line. It sits on top of the
        # current-line band and matching-tag spans, and is cleared on the next
        # cursor move (see _highlight_current_line) so it does not persist and
        # accumulate across independent navigations.
        self._oneshot_selection: QTextEdit.ExtraSelection | None = None
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter_on_scroll)
        self.textChanged.connect(self._rescan_structure)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self.cursorPositionChanged.connect(self._update_matching_tag_highlight)

        select_block_shortcut = QShortcut(QKeySequence("Ctrl+Shift+B"), self)
        select_block_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        select_block_shortcut.activated.connect(self.select_enclosing_block)

        select_parent_shortcut = QShortcut(QKeySequence("Ctrl+Shift+A"), self)
        select_parent_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        select_parent_shortcut.activated.connect(self.select_parent_block)
        # Positions of '>' characters this editor itself auto-inserted as
        # the closing half of its auto-close-'<' feature (see keyPressEvent's
        # `event.text() == "<"` branch). Tracked as QTextCursors -- rather
        # than raw int offsets -- specifically so Qt keeps each position in
        # sync automatically as the document is edited elsewhere; a raw
        # offset would go stale after any earlier edit shifts the text.
        # Consulted by _type_through_auto_closed_greater_than so that typing
        # '>' only "types through" a '>' this editor itself just inserted,
        # never an arbitrary pre-existing '>' the cursor happens to sit
        # before (see the "<Page>" pre-existing-'>' bug this guards against).
        self._auto_closed_greater_than_cursors: list[QTextCursor] = []
        self._update_gutter_width(0)
        self._rescan_structure()
        self._highlight_current_line()

    def setPlainText(self, text: str) -> None:
        super().setPlainText(text)
        # Folding state is per-document-instance; a fresh setPlainText call
        # (a new file loaded into this editor) starts fully unfolded.
        self._fold_state = {}

    def _rescan_structure(self) -> None:
        self._spans = xml_structure.scan(self.toPlainText())

    def _foldable_region_starting_at(self, block):
        """Return (first_contained_block_number, last_contained_block_number)
        for the foldable region whose open tag starts on `block`, or None if
        no such region exists (no matching TagSpan, self-closing, or a
        single-line element)."""
        block_start = block.position()
        block_end = block_start + block.length()
        for span in self._spans:
            if span.self_closing or span.close_end is None:
                continue
            if not (block_start <= span.open_start < block_end):
                continue
            open_line = self.document().findBlock(span.open_start).blockNumber()
            close_line = self.document().findBlock(span.close_end - 1).blockNumber()
            if open_line == close_line:
                continue  # single-line element: nothing to fold
            return open_line + 1, close_line - 1
        return None

    def _toggle_fold(self, block) -> None:
        region = self._foldable_region_starting_at(block)
        if region is None:
            return
        first_contained, last_contained = region
        block_number = block.blockNumber()
        currently_collapsed = self._fold_state.get(block_number, False)
        new_visible = currently_collapsed  # if collapsed, expand; else collapse
        for line_number in range(first_contained, last_contained + 1):
            contained_block = self.document().findBlockByNumber(line_number)
            if new_visible and self._is_line_hidden_by_other_collapsed_fold(
                line_number, exclude_block_number=block_number
            ):
                # Expanding this region must not reveal lines that belong to
                # a separate, still-collapsed nested fold (e.g. re-expanding
                # an outer element after its inner child was independently
                # collapsed and never re-expanded).
                continue
            contained_block.setVisible(new_visible)
        self._fold_state[block_number] = not currently_collapsed
        self.document().markContentsDirty(block.position(), self.document().characterCount() - block.position())
        self.viewport().update()

    def _is_line_hidden_by_other_collapsed_fold(self, line_number: int, exclude_block_number: int) -> bool:
        for other_block_number, collapsed in self._fold_state.items():
            if other_block_number == exclude_block_number or not collapsed:
                continue
            other_block = self.document().findBlockByNumber(other_block_number)
            other_region = self._foldable_region_starting_at(other_block)
            if other_region is None:
                continue
            other_first, other_last = other_region
            if other_first <= line_number <= other_last:
                return True
        return False

    def _refresh_extra_selections(self) -> None:
        """The single place XmlEditor calls setExtraSelections. Combines
        every named selection source in a fixed layering order (current-line
        band underneath, matching-tag spans above it, one-shot navigation/
        error line on top) and pushes the combined list to Qt in one call.
        Individual features update their own named attribute and call this;
        they never call setExtraSelections directly."""
        selections: list[QTextEdit.ExtraSelection] = []
        selections.extend(self._current_line_selections)
        selections.extend(self._matching_tag_selections)
        if self._oneshot_selection is not None:
            selections.append(self._oneshot_selection)
        self.setExtraSelections(selections)

    def _set_oneshot_selection(self, selection: QTextEdit.ExtraSelection) -> None:
        """Install `selection` as the sole overriding indicator: clear the
        current-line band and matching-tag spans, set the one-shot slot, and
        push the combined list. Reproduces the pre-refactor "replace the whole
        list" semantics for navigate_to_line / highlight_error_line /
        select_range_on_line, so exactly one selection remains immediately
        afterward. The one-shot is cleared on the NEXT cursor move by
        _highlight_current_line."""
        self._current_line_selections = []
        self._matching_tag_selections = []
        self._oneshot_selection = selection
        self._refresh_extra_selections()

    def _make_span_cursor(self, start: int, end: int) -> QTextCursor:
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        return cursor

    def _update_matching_tag_highlight(self) -> None:
        text = self.toPlainText()
        position = self.textCursor().position()
        span = xml_structure.enclosing_tag_span(text, position)
        self._matching_tag_selections = []
        if span is None or span.self_closing:
            self._refresh_extra_selections()
            return

        on_open_tag = span.open_start <= position < span.open_end
        close_start = _closing_tag_start(text, span)
        on_close_tag = (
            close_start is not None
            and span.close_end is not None
            and close_start <= position < span.close_end
        )
        if not (on_open_tag or on_close_tag):
            self._refresh_extra_selections()
            return

        open_selection = QTextEdit.ExtraSelection()
        open_selection.format.setBackground(self._matching_tag_color)
        open_selection.cursor = self._make_span_cursor(span.open_start, span.open_end)
        selections = [open_selection]

        if close_start is not None and span.close_end is not None:
            close_selection = QTextEdit.ExtraSelection()
            close_selection.format.setBackground(self._matching_tag_color)
            close_selection.cursor = self._make_span_cursor(close_start, span.close_end)
            selections.append(close_selection)

        self._matching_tag_selections = selections
        self._refresh_extra_selections()

    def select_enclosing_block(self) -> None:
        """Ctrl+Shift+B: select the innermost element containing the cursor,
        from its opening '<' through its closing '>'. Selection is built
        purely from TagSpan character offsets, so it captures the full
        underlying text even when intervening blocks are folded (hidden via
        setVisible(False)); QTextCursor addresses the document's character
        stream, not what is currently painted. No-op when the cursor is
        outside every element."""
        text = self.toPlainText()
        position = self.textCursor().position()
        span = xml_structure.enclosing_tag_span(text, position)
        if span is None:
            return
        end = span.close_end if span.close_end is not None else span.open_end
        cursor = self.textCursor()
        cursor.setPosition(span.open_start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)

    def select_parent_block(self) -> None:
        """Ctrl+Shift+A: select the block exactly one nesting level up from
        the current position. Stateless -- always re-derived from the current
        selection's START offset (never remembered state), so repeated presses
        walk up one level each time and a manually adjusted selection Just
        Works. Using selectionStart() (== the selected block's open_start
        after a prior press) rather than the cursor's moving-end position
        avoids landing exactly on close_end, which the containment rule
        (open_start <= position < end) would resolve to the FOLLOWING sibling
        instead of this block. No-op when there is no enclosing element, or
        when the enclosing element is top-level (no parent)."""
        text = self.toPlainText()
        cursor = self.textCursor()
        position = cursor.selectionStart() if cursor.hasSelection() else cursor.position()
        spans = xml_structure.scan(text)
        enclosing = xml_structure.enclosing_tag_span(text, position)
        if enclosing is None:
            return
        parent = xml_structure.parent_tag_span(spans, enclosing)
        if parent is None:
            return
        end = parent.close_end if parent.close_end is not None else parent.open_end
        new_cursor = self.textCursor()
        new_cursor.setPosition(parent.open_start)
        new_cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(new_cursor)

    def _highlight_current_line(self) -> None:
        # An independent cursor move clears any lingering one-shot navigation/
        # error/range band, reproducing the pre-refactor "next cursor move
        # wipes the one-shot indicator" behavior. When highlight_error_line /
        # navigate_to_line / select_range_on_line call setTextCursor, this slot
        # fires FIRST (as a side effect) and clears the slot; those methods
        # then set their own one-shot AFTER via _set_oneshot_selection, so the
        # override survives until the next genuinely independent cursor move.
        self._oneshot_selection = None
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(self._current_line_color)
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self._current_line_selections = [selection]
        self._refresh_extra_selections()

    def highlight_error_line(self, line: int) -> None:
        self._scroll_and_highlight_whole_line(line, self._error_line_color)

    def navigate_to_line(self, line: int) -> None:
        """Scroll to and highlight `line` (1-based) -- the general-purpose
        navigation entry point (e.g. used by the Properties panel to jump
        to a node's location). `highlight_error_line` is a thin,
        error-colored wrapper around the same mechanism for the Tier-1
        parse-failure case."""
        self._scroll_and_highlight_whole_line(line, self._navigation_highlight_color)

    def _scroll_and_highlight_whole_line(self, line: int, color: QColor) -> None:
        block = self.document().findBlockByNumber(max(0, line - 1))  # 1-based -> 0-based
        cursor = QTextCursor(block)
        self.setTextCursor(cursor)
        self.centerCursor()

        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(color)
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = cursor
        selection.cursor.clearSelection()
        # This whole-line indicator is a one-shot that intentionally overrides
        # both the current-line band and any matching-tag highlight, matching
        # the pre-refactor behavior (setTextCursor above fires the current-line
        # slot first; we then set this one-shot so only this indicator remains
        # until the next cursor move).
        self._set_oneshot_selection(selection)

    def line_text(self, line: int) -> str:
        """Return the plain text of `line` (1-based), or "" if out of range."""
        block = self.document().findBlockByNumber(max(0, line - 1))
        return block.text() if block.isValid() else ""

    def select_range_on_line(self, line: int, start: int, end: int) -> None:
        """Select and highlight the character range [start, end) within
        `line` (1-based) -- the column-precise refinement the Properties
        panel uses after `navigate_to_line` has already scrolled there."""
        block = self.document().findBlockByNumber(max(0, line - 1))
        cursor = QTextCursor(block)
        cursor.setPosition(block.position() + start)
        cursor.setPosition(block.position() + end, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)
        self.centerCursor()

        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(self._navigation_highlight_color)
        selection.cursor = cursor
        self._set_oneshot_selection(selection)

    def replace_current_selection(self, text: str) -> None:
        """Replace the current selection's text with `text` as a single undo
        step. No-op if there is no selection. Used by FindReplaceBar's
        Replace (Search & Replace sub-project)."""
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return
        cursor.insertText(text)  # QTextCursor.insertText replaces the selection
        self.setTextCursor(cursor)

    def set_line_wrap_enabled(self, enabled: bool) -> None:
        self.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth
            if enabled
            else QPlainTextEdit.LineWrapMode.NoWrap
        )

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._insert_newline_with_indent()
            return

        if event.text() == "<":
            cursor = self.textCursor()
            cursor.insertText("<>")
            # The just-inserted '>' sits one position to the left of the
            # cursor's current (post-insert) position. Track it with a
            # QTextCursor so its position self-adjusts if the document is
            # edited elsewhere before the user types the matching '>'.
            greater_than_position = cursor.position() - 1
            tracked = QTextCursor(self.document())
            tracked.setPosition(greater_than_position)
            self._auto_closed_greater_than_cursors.append(tracked)
            cursor.movePosition(QTextCursor.MoveOperation.Left)
            self.setTextCursor(cursor)
            return

        if event.text() in ('"', "'"):
            cursor = self.textCursor()
            char_before = self._character_before_cursor(cursor)
            if char_before == "=":
                quote = event.text()
                cursor.insertText(quote + quote)
                cursor.movePosition(QTextCursor.MoveOperation.Left)
                self.setTextCursor(cursor)
                return

        if event.text() == ">":
            typed_through = self._type_through_auto_closed_greater_than()
            if not typed_through:
                super().keyPressEvent(event)
                cursor = self.textCursor()
                if self._character_after_cursor(cursor) == ">":
                    # We just inserted a '>' literally, directly in front of
                    # some other, unrelated pre-existing '>' (e.g. fixing a
                    # typo in already-loaded/pasted XML -- the very scenario
                    # this fix targets). That leftover '>' is not one this
                    # editor auto-inserted, so this is not a fresh "opening
                    # tag just got completed" event; don't spuriously
                    # auto-insert a matching close tag.
                    return
            self._maybe_insert_closing_tag()
            return

        super().keyPressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        # Let Qt place the text cursor at the clicked position first, then
        # read the resulting 1-based line and notify listeners. This is the
        # editor->tree click-sync entry point (see MainWindow). It only reads
        # the cursor; it does not alter selection, folding, or the
        # auto-close/auto-indent state.
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            line = self.textCursor().blockNumber() + 1  # 0-based -> 1-based
            self.line_clicked.emit(line)

    def _character_before_cursor(self, cursor: QTextCursor) -> str:
        position = cursor.position()
        if position == 0:
            return ""
        probe = QTextCursor(self.document())
        probe.setPosition(position - 1)
        probe.setPosition(position, QTextCursor.MoveMode.KeepAnchor)
        return probe.selectedText()

    def _character_after_cursor(self, cursor: QTextCursor) -> str:
        position = cursor.position()
        probe = QTextCursor(self.document())
        probe.setPosition(position)
        probe.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
        return probe.selectedText()

    def _type_through_auto_closed_greater_than(self) -> bool:
        cursor = self.textCursor()
        position = cursor.position()
        if self._character_after_cursor(cursor) != ">":
            return False
        if not self._consume_tracked_auto_closed_greater_than_at(position):
            # The next character is a '>', but it's not one this editor
            # itself auto-inserted (e.g. pre-existing/pasted text) -- so the
            # typed '>' must be inserted literally, not typed through.
            return False
        cursor.movePosition(QTextCursor.MoveOperation.Right)
        self.setTextCursor(cursor)
        return True

    def _consume_tracked_auto_closed_greater_than_at(self, position: int) -> bool:
        """If a tracked auto-inserted '>' sits at `position`, remove it from
        tracking and return True. Otherwise return False. Also opportunistically
        drops any tracked cursors that no longer point at a '>' (e.g. the
        auto-inserted '>' was deleted by other edits), so the tracking list
        doesn't grow stale entries forever."""
        found = False
        still_tracked = []
        for tracked in self._auto_closed_greater_than_cursors:
            if tracked.isNull():
                continue
            tracked_position = tracked.position()
            if self._character_after_cursor(tracked) != ">":
                continue  # stale: no longer a '>' at this tracked position
            if not found and tracked_position == position:
                found = True
                continue  # consume this one -- do not keep tracking it
            still_tracked.append(tracked)
        self._auto_closed_greater_than_cursors = still_tracked
        return found

    def _maybe_insert_closing_tag(self) -> None:
        cursor = self.textCursor()
        text = self.toPlainText()
        position = cursor.position()
        # Only auto-insert a closing tag when the '>' just typed completes a
        # non-self-closing opening tag (does not end in "/>").
        line_start = cursor.block().position()
        text_before_cursor_on_line = text[line_start:position]
        if text_before_cursor_on_line.rstrip().endswith("/>"):
            return
        enclosing = xml_structure.find_enclosing_open_tag(text, position)
        if enclosing is None:
            return
        cursor.insertText(f"</{enclosing}>")
        cursor.setPosition(position)
        self.setTextCursor(cursor)

    def _insert_newline_with_indent(self) -> None:
        cursor = self.textCursor()
        current_line = cursor.block().text()
        leading_ws = current_line[: len(current_line) - len(current_line.lstrip())]
        position = cursor.position() - cursor.block().position()
        text = self.toPlainText()
        enclosing = xml_structure.find_enclosing_open_tag(text, cursor.position())
        depth = xml_structure.nesting_depth_at(text, cursor.position())
        extra_indent = ""
        # Only add one extra indent level when the tag we just typed the
        # open-tag-closing '>' for is itself nested inside some other real
        # parent (depth > 0) -- a root-level element (depth 0) that has no
        # separate close tag yet is trivially its own "enclosing" tag per
        # find_enclosing_open_tag, but that's not a case that should add an
        # indent level: nothing contains it.
        if (
            enclosing is not None
            and depth > 0
            and _cursor_immediately_after_open_tag(current_line, position, enclosing)
        ):
            extra_indent = "  "
        cursor.insertText("\n" + leading_ws + extra_indent)

    def _gutter_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        digit_width = self.fontMetrics().horizontalAdvance("9")
        return digits * digit_width + _FOLD_GLYPH_WIDTH + 6

    def _update_gutter_width(self, _new_block_count: int) -> None:
        self.setViewportMargins(self._gutter_width(), 0, 0, 0)

    def _update_gutter_on_scroll(self, rect, dy: int) -> None:
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_gutter_width(0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        contents_rect = self.contentsRect()
        self._gutter.setGeometry(
            QRect(contents_rect.left(), contents_rect.top(), self._gutter_width(), contents_rect.height())
        )
