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

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QKeyEvent,
    QKeySequence,
    QPainter,
    QPalette,
    QPen,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QTextEdit,
    QToolTip,
    QWidget,
)

from pgtp_editor.schema_learning.settings_index import (
    enum_hint,
    known_attributes,
    known_values,
    unused_setting_attributes,
)
from pgtp_editor.ui import xml_structure
from pgtp_editor.ui.event_body import event_body_line_ranges

STATE_NORMAL = 0
STATE_IN_UNCLOSED_STRING = 1

_TAG_OPEN_RE = re.compile(r"</?[A-Za-z_][\w.-]*")
_TAG_CLOSE_RE = re.compile(r"/?>")
_ATTR_NAME_RE = re.compile(r"[A-Za-z_][\w.-]*(?=\s*=)")
_ATTR_VALUE_RE = re.compile(r'"[^"]*"')

# Matches one attribute pair -- name, '=', then a quoted value (single or
# double quotes; value text may itself contain the *other* quote char and
# even a '>' since it's inside the quotes) -- inside an opening tag. Used by
# attribute_at_position to find which attribute the cursor sits on.
_ATTR_PAIR_RE = re.compile(
    r"""([A-Za-z_][\w.-]*)\s*=\s*("[^"]*"|'[^']*')"""
)


def attribute_at_position(text: str, pos: int):
    """Resolve a document character position to ``(tag_chain, attr)`` when it
    falls on an attribute (name token or quoted value) inside an *opening*
    tag; otherwise return ``None``.

    ``tag_chain`` is the slash-joined ancestor open-tag names from the
    document root down to and including the tag the position is in (e.g.
    ``"PGTPProject/Pages/Page/Editor"``). The ancestor walk reuses
    xml_structure's tag scanner (``scan``/``parent_tag_span``) rather than a
    second XML scanner, so open/close/self-closing bookkeeping stays in one
    place.

    Returns ``None`` when the position is over the tag name, in whitespace
    between tokens, inside a close tag, in text content, or outside every
    element.
    """
    spans = xml_structure.scan(text)

    # The span the position is in is the innermost one whose *opening* tag
    # delimiters cover pos (self-closing tags included). A close tag's own
    # '</name>' is not an open-tag region, so positions there resolve to no
    # span and return None -- the desired behavior.
    # xml_structure's tag regex uses [^<>], so it truncates an opening tag at
    # the first '>' even when that '>' is inside a quoted attribute value. Its
    # open_start (and name/chain bookkeeping) is still reliable, so we take the
    # candidate span from open_start but recompute the tag's true '>' end here,
    # respecting quotes, to stay robust to '>' inside values.
    containing = None
    for span in spans:
        real_open_end = _opening_tag_end(text, span.open_start)
        if real_open_end is None:
            continue
        if span.open_start <= pos < real_open_end and (
            containing is None or span.depth > containing.depth
        ):
            containing = span
            containing_open_end = real_open_end
    if containing is None:
        return None

    attr = _attribute_name_at(text, containing.open_start, containing_open_end, pos)
    if attr is None:
        return None

    names = [containing.name]
    walker = containing
    while walker.depth > 0:
        parent = xml_structure.parent_tag_span(spans, walker)
        if parent is None:
            break
        names.append(parent.name)
        walker = parent
    tag_chain = "/".join(reversed(names))
    return tag_chain, attr


def enclosing_open_tag(text: str, pos: int):
    """Resolve a document position that falls *inside an opening tag* (on the
    name, an attribute, or the whitespace between tokens) to
    ``(tag_chain, present_attrs, insert_pos)``; return ``None`` otherwise.

    - ``tag_chain``: slash-joined ancestor open-tag names from the document
      root down to and including this tag (same construction Phase 3 uses via
      xml_structure's scan/parent_tag_span).
    - ``present_attrs``: the set of attribute names already on this opening
      tag, parsed quote-awarely so a '>' inside a quoted value does not
      truncate the tag.
    - ``insert_pos``: index of the tag's closing '>' (or the '/' of a
      self-closing '/>'), i.e. where a new ` name=""` should be spliced.

    Returns ``None`` when ``pos`` is in text content, a close tag, or outside
    every element. Unlike ``attribute_at_position``, ``pos`` need not be on an
    attribute token -- anywhere inside the opening-tag region qualifies.
    """
    spans = xml_structure.scan(text)

    containing = None
    containing_open_end = None
    for span in spans:
        real_open_end = _opening_tag_end(text, span.open_start)
        if real_open_end is None:
            continue
        if span.open_start <= pos < real_open_end and (
            containing is None or span.depth > containing.depth
        ):
            containing = span
            containing_open_end = real_open_end
    if containing is None:
        return None

    # insert_pos: the '/' of a self-closing '/>' or the closing '>'. The tag's
    # true end is containing_open_end (just past '>'); walk back over a
    # trailing '/' so a self-closing tag splices before "/>".
    insert_pos = containing_open_end - 1  # index of '>'
    if insert_pos - 1 >= containing.open_start and text[insert_pos - 1] == "/":
        insert_pos -= 1

    present_attrs = {
        match.group(1)
        for match in _ATTR_PAIR_RE.finditer(
            text[containing.open_start:containing_open_end]
        )
    }

    names = [containing.name]
    walker = containing
    while walker.depth > 0:
        parent = xml_structure.parent_tag_span(spans, walker)
        if parent is None:
            break
        names.append(parent.name)
        walker = parent
    tag_chain = "/".join(reversed(names))
    return tag_chain, present_attrs, insert_pos


def insert_attribute(text: str, insert_pos: int, name: str):
    """Splice ` name=""` (leading space + name + ``=""``) into ``text`` just
    before ``insert_pos`` and return ``(new_text, caret_pos)`` where
    ``caret_pos`` is the index BETWEEN the two inserted quotes.

    ``insert_pos`` is the index of the tag's closing '>' (or the '/' of a
    self-closing '/>'); the inserted text goes immediately before it.
    """
    fragment = f' {name}=""'
    new_text = text[:insert_pos] + fragment + text[insert_pos:]
    # Caret sits between the two quotes: one char back from the fragment's end.
    caret_pos = insert_pos + len(fragment) - 1
    return new_text, caret_pos


def _opening_tag_end(text: str, open_start: int):
    """Return the offset just past the '>' that closes the opening tag
    beginning at ``open_start``, scanning left-to-right and treating any '>'
    inside a single- or double-quoted attribute value as ordinary text. Returns
    None if no closing '>' is found (a truncated/mid-edit tag)."""
    quote = None
    for i in range(open_start, len(text)):
        ch = text[i]
        if quote is not None:
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
        elif ch == ">":
            return i + 1
    return None


def _attribute_name_at(text: str, open_start: int, open_end: int, pos: int):
    """Return the attribute name whose name-token or quoted value contains
    ``pos`` within the opening tag spanning ``[open_start, open_end)``, or
    ``None`` if ``pos`` is over the tag name, in an inter-token gap, or on the
    tag delimiters."""
    tag_text = text[open_start:open_end]
    offset = pos - open_start
    for match in _ATTR_PAIR_RE.finditer(tag_text):
        name_start, name_end = match.start(1), match.end(1)
        value_start, value_end = match.start(2), match.end(2)
        on_name = name_start <= offset < name_end
        on_value = value_start <= offset < value_end
        if on_name or on_value:
            return match.group(1)
    return None

# Fixed horizontal allowance reserved for the fold-triangle glyph, added on
# top of the digit-count-dependent width for line numbers.
_FOLD_GLYPH_WIDTH = 16

# Fixed horizontal allowance reserved on the LEFT of the gutter for the
# bookmark strip (where the rounded bookmark tags are drawn / clicked to
# toggle). Sits left of the fold zone and the line numbers, which both shift
# right by this amount.
_BOOKMARK_STRIP_WIDTH = 12


class XmlSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)

        self._tag_format = QTextCharFormat()
        self._tag_format.setForeground(QColor("#569cd6"))

        self._attr_name_format = QTextCharFormat()
        self._attr_name_format.setForeground(QColor("#9cdcfe"))

        self._string_format = QTextCharFormat()
        self._string_format.setForeground(QColor("#ce9178"))

    def set_colors(self, tag: str, attr_name: str, string: str) -> None:
        """Recolor the three syntax formats (tag, attribute-name, string) for a
        light or dark theme. The caller rehighlights afterwards."""
        self._tag_format.setForeground(QColor(tag))
        self._attr_name_format.setForeground(QColor(attr_name))
        self._string_format.setForeground(QColor(string))

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
        painter.fillRect(event.rect(), self._editor._gutter_bg_color)

        block = self._editor.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self._editor.blockBoundingGeometry(block).translated(
            self._editor.contentOffset()
        ).top()
        bottom = top + self._editor.blockBoundingRect(block).height()

        # Three zones, left to right: the bookmark strip
        # [0, _BOOKMARK_STRIP_WIDTH), the fold zone
        # [_BOOKMARK_STRIP_WIDTH, _BOOKMARK_STRIP_WIDTH + _FOLD_GLYPH_WIDTH),
        # and the line-number area (right-aligned against the gutter's right
        # edge). The fold glyph and numbers both shift right by the strip width.
        number_x = _BOOKMARK_STRIP_WIDTH + _FOLD_GLYPH_WIDTH
        line_number_width = self.width() - number_x

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number_text = str(block_number + 1)
                painter.setPen(self._editor._gutter_fg_color)
                painter.drawText(
                    number_x,
                    int(top),
                    line_number_width,
                    self._editor.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number_text,
                )

                if block_number in self._editor._bookmarks:
                    self._draw_bookmark_tag(painter, int(top))

                if self._editor._foldable_region_starting_at(block) is not None:
                    collapsed = self._editor._fold_state.get(block_number, False)
                    self._draw_fold_glyph(painter, int(top), collapsed)

            block = block.next()
            top = bottom
            bottom = top + self._editor.blockBoundingRect(block).height()
            block_number += 1

    def _draw_bookmark_tag(self, painter: QPainter, top: int) -> None:
        """Draw a small filled rounded tag in the bookmark strip, vertically
        centered on the line, in the palette's Highlight accent (theme-aware,
        no border, antialiased)."""
        line_height = self._editor.fontMetrics().height()
        tag_w = _BOOKMARK_STRIP_WIDTH - 4
        tag_h = max(4, min(line_height - 6, _BOOKMARK_STRIP_WIDTH))
        x = 2
        y = top + (line_height - tag_h) // 2
        radius = max(1, tag_h // 4)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._editor._bookmark_color())
        painter.drawRoundedRect(QRect(x, y, tag_w, tag_h), radius, radius)
        painter.restore()

    def _draw_fold_glyph(self, painter: QPainter, top: int, collapsed: bool) -> None:
        line_height = self._editor.fontMetrics().height()
        glyph_size = min(_FOLD_GLYPH_WIDTH - 6, line_height - 6)
        half = max(2, glyph_size // 2)
        depth = max(1, half // 2)  # how far the chevron's tip protrudes
        cx = _BOOKMARK_STRIP_WIDTH + _FOLD_GLYPH_WIDTH // 2
        cy = top + line_height // 2
        # A fine, unfilled chevron (technical arrow) rather than a filled triangle.
        pen = QPen(self._editor._gutter_fg_color)
        pen.setWidthF(1.3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if collapsed:
            # Right-pointing chevron ">"
            painter.drawLine(cx - depth, cy - half, cx + depth, cy)
            painter.drawLine(cx + depth, cy, cx - depth, cy + half)
        else:
            # Down-pointing chevron "v"
            painter.drawLine(cx - half, cy - depth, cx, cy + depth)
            painter.drawLine(cx, cy + depth, cx + half, cy - depth)
        painter.restore()

    def mousePressEvent(self, event) -> None:
        click_x = event.position().x()
        # Zone routing: bookmark strip toggles the clicked line's bookmark;
        # fold zone keeps the existing fold toggle; a click in the line-number
        # area does nothing (as before).
        in_bookmark_strip = click_x < _BOOKMARK_STRIP_WIDTH
        in_fold_zone = (
            _BOOKMARK_STRIP_WIDTH
            <= click_x
            < _BOOKMARK_STRIP_WIDTH + _FOLD_GLYPH_WIDTH
        )
        if not (in_bookmark_strip or in_fold_zone):
            return
        block = self._editor.firstVisibleBlock()
        top = self._editor.blockBoundingGeometry(block).translated(
            self._editor.contentOffset()
        ).top()
        bottom = top + self._editor.blockBoundingRect(block).height()
        click_y = event.position().y()

        while block.isValid() and top <= click_y:
            if block.isVisible() and top <= click_y < bottom:
                if in_bookmark_strip:
                    self._editor.toggle_bookmark(block.blockNumber())
                else:
                    self._editor._toggle_fold(block)
                self.update()
                return
            block = block.next()
            top = bottom
            bottom = top + self._editor.blockBoundingRect(block).height()


class _CompletionPopup(QListWidget):
    """Frameless completion list for the XML editor. Holds a master list of
    ``(key, display)`` items and a running filter; arrows navigate, printable
    chars filter by key prefix (case-insensitive), Enter/Tab or a mouse click
    choose, Esc cancels. Emits the chosen *key* (not the display string).
    Callers pass items pre-ordered; filtering preserves that order."""

    chosen = Signal(str)
    cancelled = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setUniformItemSizes(True)
        self._items: list[tuple[str, str]] = []
        self._filter = ""
        self.itemClicked.connect(
            lambda item: self.chosen.emit(item.data(Qt.ItemDataRole.UserRole))
        )

    def set_items(self, items) -> None:
        """Replace the master ``(key, display)`` list, reset the filter, and
        select the first row."""
        self._items = list(items)
        self._filter = ""
        self._rebuild()

    def append_filter(self, text: str) -> None:
        self._filter += text
        self._rebuild()

    def backspace_filter(self) -> None:
        self._filter = self._filter[:-1]
        self._rebuild()

    def visible_keys(self) -> list[str]:
        return [
            self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())
        ]

    def current_key(self):
        item = self.currentItem()
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def _rebuild(self) -> None:
        prefix = self._filter.lower()
        self.clear()
        for key, display in self._items:
            if key.lower().startswith(prefix):
                item = QListWidgetItem(display)
                item.setData(Qt.ItemDataRole.UserRole, key)
                self.addItem(item)
        if self.count():
            self.setCurrentRow(0)

    def _choose_current(self) -> None:
        key = self.current_key()
        if key is not None:
            self.chosen.emit(key)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
            self._choose_current()
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self.cancelled.emit()
            event.accept()
            return
        if key == Qt.Key.Key_Backspace:
            self.backspace_filter()
            event.accept()
            return
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            super().keyPressEvent(event)
            return
        # Ctrl/Meta chords (Ctrl+C, Ctrl+A, ...) still carry a text() payload
        # on some platforms; never swallow them into the filter. Shift stays
        # allowed (uppercase typing filters) and Alt passes through below via
        # the empty/non-printable text check or the fallthrough.
        if event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier
        ):
            super().keyPressEvent(event)
            return
        text = event.text()
        if text and text.isprintable() and not text.isspace():
            self.append_filter(text)
            event.accept()
            return
        super().keyPressEvent(event)


class XmlEditor(QPlainTextEdit):
    line_clicked = Signal(int)  # 1-based line of a left-mouse click in the text
    # Emitted when a text-modifying key is pressed while the editor is
    # read-only (Caption Mode). The base already blocks the edit; this signal
    # lets MainWindow flash a non-modal "read-only" hint.
    read_only_edit_attempted = Signal()
    # Emitted when the user picks "Find" from the editor's right-click context
    # menu with a non-empty selection. Carries the selected text; MainWindow
    # reveals the Raw XML find bar, prefills it, and runs Find Next.
    find_selected_text = Signal(str)
    # Emitted when the user picks "Edit code..." from the editor's right-click
    # context menu while the cursor is inside an event-handler body. Carries
    # the 1-based line of that handler's open tag; MainWindow opens the
    # CodeEditorDialog and owns the write-back.
    edit_code_requested = Signal(int)
    # Emitted when Ctrl+Z / Ctrl+Y (or Ctrl+Shift+Z) is pressed while the
    # editor is focused. The editor's native per-keystroke undo would otherwise
    # shadow the window-level snapshot undo; keyPressEvent consumes these keys
    # and routes them to MainWindow's document-level snapshot undo/redo instead
    # (Sub-project C, C1).
    undo_requested = Signal()
    redo_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._highlighter = XmlSyntaxHighlighter(self.document())
        self._gutter = _EditorGutter(self)
        self._fold_state: dict[int, bool] = {}
        # Session/file-scoped line bookmarks, tracked by block number. Reset
        # alongside _fold_state on every setPlainText (a new file loaded), so
        # bookmarks never drift from external edits or leak across documents.
        self._bookmarks: set[int] = set()
        # Theme-aware colors. These default to the DARK set; apply_theme_colors
        # swaps the whole set to the LIGHT variant (and back) and is driven
        # automatically off ApplicationPaletteChange in changeEvent, so the
        # editor follows the app's Light/Dark theme. The gutter widget reads
        # _gutter_bg_color/_gutter_fg_color directly when painting.
        self._gutter_bg_color = QColor("#2b2b2b")
        self._gutter_fg_color = QColor("#858585")
        self._current_line_color = QColor("#2d2d30")
        self._error_line_color = QColor("#5a1d1d")
        self._navigation_highlight_color = QColor("#264f78")
        self._matching_tag_color = QColor("#3a5f3a")
        self._current_line_selections: list[QTextEdit.ExtraSelection] = []
        self._matching_tag_selections: list[QTextEdit.ExtraSelection] = []
        # Distinct styling for event-handler code bodies (the text between
        # <OnXxx ...> and </OnXxx>): a subdued background + monospace font,
        # keyed to event_body_line_ranges so styling and the "which handler is
        # under the cursor" lookup share one source of truth. Recomputed on
        # every text change (see _refresh_code_region_selections); rendered
        # underneath every other extra-selection layer. Read-only-safe:
        # extra selections are purely visual and apply in Caption Mode too.
        self._code_region_color = QColor("#232a2f")
        self._code_region_font = self._make_monospace_font()
        self._code_region_selections: list[QTextEdit.ExtraSelection] = []
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
        self.textChanged.connect(self._refresh_code_region_selections)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self.cursorPositionChanged.connect(self._update_matching_tag_highlight)

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
        # Learned schema model injected by MainWindow after each enrich; None
        # disables value-hover tooltips (see set_schema_model / event()).
        self._schema_model = None
        # The shared Ctrl+Space completion popup (attribute names, then
        # chained values). Created lazily on first use; see
        # _ensure_completion_popup.
        self._completion_popup: _CompletionPopup | None = None
        # True once _rewire_popup has connected the popup's signals at least
        # once; guards the disconnect calls in _rewire_popup so a fresh popup
        # doesn't log a PySide6 RuntimeWarning for disconnecting nothing.
        self._popup_wired = False
        self._update_gutter_width(0)
        self._rescan_structure()
        self._refresh_code_region_selections()
        self._highlight_current_line()

    def setPlainText(self, text: str) -> None:
        super().setPlainText(text)
        # Folding state is per-document-instance; a fresh setPlainText call
        # (a new file loaded into this editor) starts fully unfolded.
        self._fold_state = {}
        # Bookmarks share the fold-state lifecycle: a new document starts with
        # no bookmarks (session/file-scoped, see __init__).
        self._bookmarks = set()

    def apply_theme_colors(self, light: bool) -> None:
        """Swap the editor's color attributes and the syntax highlighter's
        format colors between a LIGHT set (readable dark-on-white) and the DARK
        set (the original values), then rehighlight and repaint so the change
        shows immediately -- gutter, current-line band, matching-tag spans and
        code-region backgrounds all recolor at once. Wired to run automatically
        on ApplicationPaletteChange via changeEvent."""
        if light:
            self._gutter_bg_color = QColor("#f0f0f0")
            self._gutter_fg_color = QColor("#888888")
            self._current_line_color = QColor("#eef1f7")
            self._error_line_color = QColor("#f7d4d4")
            self._navigation_highlight_color = QColor("#cfe0ff")
            self._matching_tag_color = QColor("#d3ecd3")
            self._code_region_color = QColor("#eef2f5")
            self._highlighter.set_colors(
                tag="#0000ff", attr_name="#e50000", string="#a31515"
            )
        else:
            self._gutter_bg_color = QColor("#2b2b2b")
            self._gutter_fg_color = QColor("#858585")
            self._current_line_color = QColor("#2d2d30")
            self._error_line_color = QColor("#5a1d1d")
            self._navigation_highlight_color = QColor("#264f78")
            self._matching_tag_color = QColor("#3a5f3a")
            self._code_region_color = QColor("#232a2f")
            self._highlighter.set_colors(
                tag="#569cd6", attr_name="#9cdcfe", string="#ce9178"
            )
        self._highlighter.rehighlight()
        # Rebuild the extra-selection layers so their stored per-selection
        # colors pick up the new values (they cache the color at build time).
        self._refresh_code_region_selections()
        self._update_matching_tag_highlight()
        self._highlight_current_line()
        self._gutter.update()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (
            QEvent.Type.ApplicationPaletteChange,
            QEvent.Type.PaletteChange,
        ):
            # changeEvent can fire during base-class construction, before the
            # theme attributes/highlighter exist; ignore until we're set up.
            if not hasattr(self, "_highlighter"):
                return
            light = self.palette().color(QPalette.ColorRole.Base).lightness() > 128
            self.apply_theme_colors(light)

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

    # --- Bookmarks ---------------------------------------------------------
    def toggle_bookmark(self, block_number: int) -> None:
        """Add or remove a bookmark on ``block_number`` (0-based line index)
        and repaint the gutter so the tag appears/disappears immediately."""
        if block_number in self._bookmarks:
            self._bookmarks.discard(block_number)
        else:
            self._bookmarks.add(block_number)
        self._gutter.update()

    def bookmarked_lines(self) -> list[int]:
        """Bookmarked block numbers in ascending order."""
        return sorted(self._bookmarks)

    def next_bookmark(self, from_line: int) -> int | None:
        """Smallest bookmark strictly greater than ``from_line``, wrapping to
        the smallest bookmark overall; ``None`` when there are no bookmarks."""
        ordered = self.bookmarked_lines()
        if not ordered:
            return None
        for line in ordered:
            if line > from_line:
                return line
        return ordered[0]

    def prev_bookmark(self, from_line: int) -> int | None:
        """Largest bookmark strictly less than ``from_line``, wrapping to the
        largest bookmark overall; ``None`` when there are no bookmarks."""
        ordered = self.bookmarked_lines()
        if not ordered:
            return None
        for line in reversed(ordered):
            if line < from_line:
                return line
        return ordered[-1]

    def clear_bookmarks(self) -> None:
        """Remove every bookmark and repaint the gutter."""
        self._bookmarks = set()
        self._gutter.update()

    def toggle_bookmark_at_cursor(self) -> None:
        """Toggle a bookmark on the line the text cursor currently sits on."""
        self.toggle_bookmark(self.textCursor().blockNumber())

    def goto_next_bookmark(self) -> None:
        """Move the cursor to the next bookmark after the current line (with
        wrap-around) and center it. No-op when there are no bookmarks."""
        target = self.next_bookmark(self.textCursor().blockNumber())
        if target is not None:
            self._goto_bookmark_line(target)

    def goto_prev_bookmark(self) -> None:
        """Move the cursor to the previous bookmark before the current line
        (with wrap-around) and center it. No-op when there are no bookmarks."""
        target = self.prev_bookmark(self.textCursor().blockNumber())
        if target is not None:
            self._goto_bookmark_line(target)

    def _goto_bookmark_line(self, block_number: int) -> None:
        """Move the cursor to ``block_number`` (0-based) and center it. Guards
        against out-of-range bookmarks that may point past EOF after edits."""
        block = self.document().findBlockByNumber(block_number)
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        self.setTextCursor(cursor)
        self.centerCursor()

    def _refresh_extra_selections(self) -> None:
        """The single place XmlEditor calls setExtraSelections. Combines
        every named selection source in a fixed layering order (current-line
        band underneath, matching-tag spans above it, one-shot navigation/
        error line on top) and pushes the combined list to Qt in one call.
        Individual features update their own named attribute and call this;
        they never call setExtraSelections directly."""
        selections: list[QTextEdit.ExtraSelection] = []
        # Code-region background sits underneath everything so the current-line
        # band, matching-tag spans and one-shot indicators paint over it.
        selections.extend(self._code_region_selections)
        selections.extend(self._current_line_selections)
        selections.extend(self._matching_tag_selections)
        if self._oneshot_selection is not None:
            selections.append(self._oneshot_selection)
        self.setExtraSelections(selections)

    def _make_monospace_font(self) -> QFont:
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFixedPitch(True)
        return font

    def _refresh_code_region_selections(self) -> None:
        """Recompute the distinct styling for event-handler code bodies from
        event_body_line_ranges. Marks every line from a handler's open-tag line
        through its close-tag line (inclusive) with a subdued full-width
        background band + monospace font. Purely visual, so it is safe when the
        editor is read-only (Caption Mode)."""
        text = self.toPlainText()
        document = self.document()
        selections: list[QTextEdit.ExtraSelection] = []
        for range_ in event_body_line_ranges(text):
            for line in range(range_["start_line"], range_["end_line"] + 1):
                block = document.findBlockByNumber(line - 1)  # 1-based -> 0-based
                if not block.isValid():
                    continue
                selection = QTextEdit.ExtraSelection()
                selection.format.setBackground(self._code_region_color)
                selection.format.setFont(self._code_region_font)
                selection.format.setProperty(
                    QTextFormat.Property.FullWidthSelection, True
                )
                cursor = QTextCursor(block)
                cursor.clearSelection()
                selection.cursor = cursor
                selections.append(selection)
        self._code_region_selections = selections
        self._refresh_extra_selections()

    def event_body_start_line_at_cursor(self) -> int | None:
        """Return the 1-based open-tag line of the event-handler body the
        cursor currently sits within (start_line..end_line inclusive), or None
        when the cursor is not inside any event-handler body. Drives whether
        the "Edit code..." context-menu action is offered and which handler it
        targets."""
        cursor_line = self.textCursor().blockNumber() + 1  # 0-based -> 1-based
        for range_ in event_body_line_ranges(self.toPlainText()):
            if range_["start_line"] <= cursor_line <= range_["end_line"]:
                return range_["start_line"]
        return None

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
        # Anchor at the block END and move the caret to the block START with
        # KeepAnchor: the whole block stays selected, but selectionStart()==the
        # caret position, so the visible cursor (and the ensured-visible scroll)
        # lands at the beginning of the selection rather than the end.
        cursor = self.textCursor()
        cursor.setPosition(end)
        cursor.setPosition(span.open_start, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

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
        # Caret-at-start (see select_enclosing_block): anchor at END, caret at
        # START, so selectionStart() is where the visible cursor sits and the
        # view scrolls to the block's beginning. Note select_parent_block
        # re-derives from selectionStart() on the next press, so caret-at-start
        # keeps repeated presses walking up correctly.
        new_cursor = self.textCursor()
        new_cursor.setPosition(end)
        new_cursor.setPosition(parent.open_start, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(new_cursor)
        self.ensureCursorVisible()

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

    def is_line_wrap_enabled(self) -> bool:
        return self.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth

    @staticmethod
    def _is_text_modifying_key(event: QKeyEvent) -> bool:
        """True if `event` would mutate the document: a printable character,
        one of Backspace/Delete/Return/Enter, or a paste (Ctrl+V). Used only
        in read-only mode to decide whether to emit read_only_edit_attempted."""
        if event.matches(QKeySequence.StandardKey.Paste):
            return True
        if event.key() in (
            Qt.Key.Key_Backspace,
            Qt.Key.Key_Delete,
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        ):
            return True
        return bool(event.text()) and event.text().isprintable()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.isReadOnly() and self._is_text_modifying_key(event):
            # Caption Mode: the base QPlainTextEdit already refuses the edit
            # when read-only; the only added behavior is a non-modal hint.
            self.read_only_edit_attempted.emit()
            return

        # Route Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z to the document-level snapshot
        # undo/redo (MainWindow) rather than QPlainTextEdit's native char-level
        # undo, which would otherwise win while the editor has focus (C1).
        # Consume the key here so the coexisting window QShortcut does not also
        # fire (no double-undo).
        mods = event.modifiers()
        ctrl = Qt.KeyboardModifier.ControlModifier
        shift = Qt.KeyboardModifier.ShiftModifier
        if mods == ctrl and event.key() == Qt.Key.Key_Z:
            self.undo_requested.emit()
            event.accept()
            return
        if (mods == ctrl and event.key() == Qt.Key.Key_Y) or (
            mods == (ctrl | shift) and event.key() == Qt.Key.Key_Z
        ):
            self.redo_requested.emit()
            event.accept()
            return

        if mods == ctrl and event.key() == Qt.Key.Key_Space:
            self._show_attribute_completions()
            event.accept()
            return

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

    def _build_context_menu(self) -> QMenu:
        """Build the editor's right-click menu: the standard editable menu
        with a "Find" action prepended when there is a non-empty selection.
        Split out from contextMenuEvent so tests can inspect/trigger the menu
        without calling .exec() (which would block on a real popup)."""
        menu = self.createStandardContextMenu()
        cursor = self.textCursor()
        actions = menu.actions()
        before = actions[0] if actions else None
        if cursor.hasSelection():
            find_action = QAction("Find", menu)
            find_action.triggered.connect(self._emit_find_selected_text)
            if before is not None:
                menu.insertAction(before, find_action)
            else:
                menu.addAction(find_action)
        # "Edit code..." is offered only when the cursor is inside an
        # event-handler body; triggering it hands the handler's open-tag line
        # to MainWindow, which owns the CodeEditorDialog + write-back.
        start_line = self.event_body_start_line_at_cursor()
        if start_line is not None:
            edit_code_action = QAction("Edit code…", menu)
            edit_code_action.triggered.connect(
                lambda: self.edit_code_requested.emit(start_line)
            )
            if before is not None:
                menu.insertAction(before, edit_code_action)
            else:
                menu.addAction(edit_code_action)
        # "Add attribute ▸" lists settings-attributes the schema knows for this
        # element path that the element doesn't already have. Omitted entirely
        # when there are none (model None, read-only, not in an opening tag, or
        # nothing unused) so the menu stays clean.
        names = self.unused_attributes_at(self.textCursor().position())
        if names:
            add_menu = QMenu("Add attribute", menu)
            for name in names:
                action = QAction(name, add_menu)
                action.triggered.connect(
                    lambda _checked=False, n=name: self._insert_attribute(n)
                )
                add_menu.addAction(action)
            if before is not None:
                menu.insertMenu(before, add_menu)
            else:
                menu.addMenu(add_menu)
        # "Wrap Lines" toggles soft line-wrapping of the Raw XML editor. It is
        # checkable and reflects the editor's current wrap state each time the
        # menu is built, and toggling it drives set_line_wrap_enabled.
        menu.addSeparator()
        wrap_action = QAction("Wrap Lines", menu)
        wrap_action.setCheckable(True)
        wrap_action.setChecked(self.is_line_wrap_enabled())
        wrap_action.toggled.connect(self.set_line_wrap_enabled)
        menu.addAction(wrap_action)
        return menu

    def _emit_find_selected_text(self) -> None:
        # QTextCursor.selectedText() uses U+2029 (paragraph separator) to join
        # lines of a multi-line selection; collapse those to spaces so the find
        # term is a plain string. Single-line selections (the norm) are
        # unaffected.
        selected = self.textCursor().selectedText().replace(chr(0x2029), chr(32))
        self.find_selected_text.emit(selected)

    def contextMenuEvent(self, event) -> None:
        menu = self._build_context_menu()
        menu.exec(event.globalPos())

    def set_schema_model(self, model) -> None:
        """Inject the current in-memory schema Model (or None). Passed by
        MainWindow after each enrich so value-hover tooltips reflect the
        latest labels; None disables hovers (default)."""
        self._schema_model = model

    def unused_attributes_at(self, cursor_pos: int) -> list[str]:
        """Setting-attributes the schema knows for the opening tag at
        ``cursor_pos`` that the element does not already carry, sorted.

        Returns ``[]`` when the editor is read-only (Caption Mode), no model is
        set, ``cursor_pos`` is not inside an opening tag, or nothing is unused.
        Drives the "Add attribute" submenu; exposed so tests can exercise the
        menu-building logic without popping a real menu.
        """
        if self.isReadOnly() or self._schema_model is None:
            return []
        resolved = enclosing_open_tag(self.toPlainText(), cursor_pos)
        if resolved is None:
            return []
        tag_chain, present_attrs, _insert_pos = resolved
        return unused_setting_attributes(
            self._schema_model, tag_chain, present_attrs
        )

    def _insert_attribute(self, name: str) -> None:
        """Insert ` name=""` into the opening tag at the current cursor and
        place the caret between the quotes. No-op when the cursor is not
        inside an opening tag. Thin wrapper around
        ``_splice_attribute_at_cursor``, which does the actual splicing."""
        self._splice_attribute_at_cursor(name)

    def _splice_attribute_at_cursor(self, name: str):
        """Insert ` name=""` into the opening tag at the current cursor as one
        undoable edit and place the caret between the quotes. Returns the
        tag_chain of the tag spliced into, or None when the cursor is not
        inside an opening tag (no edit made)."""
        resolved = enclosing_open_tag(
            self.toPlainText(), self.textCursor().position()
        )
        if resolved is None:
            return None
        tag_chain, _present_attrs, insert_pos = resolved
        fragment = f' {name}=""'
        cursor = self.textCursor()
        cursor.beginEditBlock()
        cursor.setPosition(insert_pos)
        cursor.insertText(fragment)
        cursor.endEditBlock()
        # Caret between the two quotes: one char back from the fragment's end.
        cursor.setPosition(insert_pos + len(fragment) - 1)
        self.setTextCursor(cursor)
        return tag_chain

    def _ensure_completion_popup(self) -> _CompletionPopup:
        if self._completion_popup is None:
            self._completion_popup = _CompletionPopup(self)
        return self._completion_popup

    def _popup_at_caret(self, popup: _CompletionPopup) -> None:
        """Show ``popup`` just below the caret and give it focus."""
        rect = self.cursorRect()
        point = self.viewport().mapToGlobal(rect.bottomLeft())
        popup.move(point)
        popup.show()
        popup.setFocus()

    def _show_attribute_completions(self) -> None:
        """Ctrl+Space entry point. Opens the attribute popup for the opening
        tag at the caret. No-op when read-only, no model, not inside an
        opening tag, or nothing unused is left to offer."""
        if self.isReadOnly() or self._schema_model is None:
            return
        resolved = enclosing_open_tag(
            self.toPlainText(), self.textCursor().position()
        )
        if resolved is None:
            return
        tag_chain, present_attrs, _insert_pos = resolved
        names = known_attributes(self._schema_model, tag_chain, present_attrs)
        if not names:
            return
        popup = self._ensure_completion_popup()
        popup.set_items([(n, n) for n in names])
        self._rewire_popup(popup, self._complete_attribute)
        self._popup_at_caret(popup)

    def _rewire_popup(self, popup: _CompletionPopup, on_chosen) -> None:
        """Point the shared popup's signals at the current completion stage.
        Only disconnects previous connections when the popup was actually
        wired before, so a fresh popup's first use does not trigger a
        PySide6 RuntimeWarning for disconnecting an unconnected signal."""
        if self._popup_wired:
            popup.chosen.disconnect()
            popup.cancelled.disconnect()
        popup.chosen.connect(on_chosen)
        popup.cancelled.connect(popup.hide)
        self._popup_wired = True

    def _complete_attribute(self, name: str) -> None:
        """Insert ``name=""`` at the caret's opening tag (single undoable
        edit, caret between the quotes), hide the popup, then chain into the
        value picker when the schema knows values for ``name``."""
        popup = self._completion_popup
        if popup is not None:
            popup.hide()
        tag_chain = self._splice_attribute_at_cursor(name)
        if tag_chain is None:
            return
        values = known_values(self._schema_model, tag_chain, name)
        if values:
            self._show_value_completions(values)

    def _show_value_completions(self, pairs) -> None:
        """Open the value picker for the just-inserted attribute. ``pairs`` is
        a list of ``(value, label)``; rows show ``value`` or ``value = label``
        but carry the bare value as their key. The caret sits between the
        quotes."""
        popup = self._ensure_completion_popup()
        popup.set_items(
            [
                (value, f"{value} = {label}" if label else value)
                for value, label in pairs
            ]
        )
        self._rewire_popup(popup, self._complete_value)
        self._popup_at_caret(popup)

    def _complete_value(self, value: str) -> None:
        """Insert ``value`` at the caret (between the quotes) as one undoable
        edit, move the caret just past the closing quote, and hide the
        popup."""
        popup = self._completion_popup
        if popup is not None:
            popup.hide()
        cursor = self.textCursor()
        cursor.beginEditBlock()
        cursor.insertText(value)
        cursor.endEditBlock()
        cursor.setPosition(cursor.position() + 1)  # step past the closing quote
        self.setTextCursor(cursor)

    def _hint_for_help_pos(self, char_pos: int):
        """Given a document character position, return the settings hover
        hint text or None. Factored out of the ToolTip event so the
        resolver+hint path is testable without synthesizing a QHelpEvent.
        Returns None when no model is set, the position isn't on a setting
        attribute, or enum_hint yields nothing."""
        if self._schema_model is None:
            return None
        resolved = attribute_at_position(self.toPlainText(), char_pos)
        if resolved is None:
            return None
        tag_chain, attr = resolved
        return enum_hint(self._schema_model, tag_chain, attr)

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.ToolTip:
            # The ToolTip QHelpEvent is delivered to this widget in widget
            # coordinates; cursorForPosition expects viewport coordinates, so
            # translate through the viewport before mapping to a char offset.
            viewport_pos = self.viewport().mapFrom(self, e.pos())
            char_pos = self.cursorForPosition(viewport_pos).position()
            text = self._hint_for_help_pos(char_pos)
            if text:
                QToolTip.showText(e.globalPos(), text, self)
            else:
                QToolTip.hideText()
            return False
        return super().event(e)

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

    def _bookmark_color(self) -> QColor:
        """The bookmark tag's fill, derived from the palette's Highlight role
        so it reads in both Light and Dark themes. Recomputed on each paint,
        so it tracks palette changes with no cache to invalidate."""
        return self.palette().color(QPalette.ColorRole.Highlight)

    def _gutter_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        digit_width = self.fontMetrics().horizontalAdvance("9")
        return (
            digits * digit_width
            + _BOOKMARK_STRIP_WIDTH
            + _FOLD_GLYPH_WIDTH
            + 6
        )

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
