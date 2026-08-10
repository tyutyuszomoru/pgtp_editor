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

"""XmlEditor: a QPlainTextEdit-based editor for raw .pgtp XML text.

Built as a PySide6 port of QCodeEditor's approach (see pgtp_editor/ui/about.py
for the OSS credit). Composed of three cooperating pieces: XmlSyntaxHighlighter
(syntax coloring with unclosed-quote propagation), the shared
gutter/bookmark/fold base (``ui/editor_gutter.py`` -- ``_EditorGutter`` plus
``GutterBookmarkFoldMixin``, also carried by the DDL ``CodeEditor``, §8/§18.1),
and auto-indent/auto-close behavior implemented directly as XmlEditor methods,
since those need direct QTextCursor/QTextBlock access.

The only fold piece that stays here is the XML-span foldable-region *provider*
(``_foldable_region_starting_at`` over ``_spans``/``TagSpan``), which the
shared base calls.
"""
from __future__ import annotations

import re
from bisect import bisect_right

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QKeyEvent,
    QKeySequence,
    QPalette,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtGui import QAction, QShortcut
from PySide6.QtWidgets import (
    QMenu,
    QPlainTextEdit,
    QTextEdit,
    QToolTip,
)

from pgtp_editor.schema_learning.settings_index import (
    enum_hint,
    known_attributes,
    known_values,
    unused_setting_attributes,
)
from pgtp_editor.ui import xml_structure
from pgtp_editor.ui.completion_popup import (  # noqa: F401  (re-exported name)
    CompletionPopupHostMixin,
    _CompletionPopup,
)
from pgtp_editor.ui.editor_gutter import (  # noqa: F401  (re-exported names)
    _BOOKMARK_STRIP_WIDTH,
    _EditorGutter,
    _FOLD_GLYPH_WIDTH,
    GutterBookmarkFoldMixin,
)
from pgtp_editor.ui.code_editor import (
    CLAIMED_NOT_UNDO_REDO,
    REDO,
    UNDO,
    apply_editor_operation,
    apply_shrink_structural_selection,
    classify_editor_chord,
    is_mutating_editor_operation,
    is_paste_chord,
)
from pgtp_editor.ui.editor_shared import SharedEditorMixin
from pgtp_editor.ui.event_body import event_body_line_ranges
from pgtp_editor.ui.format_settings import current_xml_config
from pgtp_editor.ui.vim_mode import VimModeMixin
from pgtp_editor.xmlfmt import format_xml_selection

STATE_NORMAL = 0  # in text content, outside any tag
STATE_IN_UNCLOSED_STRING = 1  # inside a double-quoted attribute value
STATE_IN_TAG = 2  # inside <...>, not inside a quoted value
STATE_IN_SINGLE_QUOTED = 3  # inside a single-quoted attribute value
# The only characters that can change the highlighter's block state. Matching
# just these with one C-speed regex pass keeps the per-block scan cheap
# (BUG-016) -- the Python loop then runs over a handful of matches per line
# instead of every character.
_STATE_CHARS_RE = re.compile(r"""[<>"']""")

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


def attribute_at_position(text: str, pos: int, spans: list[xml_structure.TagSpan] | None = None):
    """Resolve a document character position to ``(tag_chain, attr)`` --
    see attribute_value_at_position, which this delegates to."""
    resolved = attribute_value_at_position(text, pos, spans)
    if resolved is None:
        return None
    tag_chain, attr, _value = resolved
    return tag_chain, attr


def attribute_value_at_position(text: str, pos: int, spans: list[xml_structure.TagSpan] | None = None):
    """Resolve a document character position to ``(tag_chain, attr, value)``
    when it falls on an attribute (name token or quoted value) inside an
    *opening* tag; otherwise return ``None``. ``value`` is the attribute's
    current value with the quotes stripped.

    ``tag_chain`` is the slash-joined ancestor open-tag names from the
    document root down to and including the tag the position is in (e.g.
    ``"PGTPProject/Pages/Page/Editor"``). The ancestor walk reuses
    xml_structure's tag scanner (``scan``/``parent_tag_span``) rather than a
    second XML scanner, so open/close/self-closing bookkeeping stays in one
    place.

    ``spans``: an already-scanned span list for ``text`` (e.g. an editor's
    cached ``self._spans``) to skip a redundant ``xml_structure.scan(text)``
    call -- pass None (the default) to scan from scratch.

    Returns ``None`` when the position is over the tag name, in whitespace
    between tokens, inside a close tag, in text content, or outside every
    element.
    """
    if spans is None:
        spans = xml_structure.scan(text)

    # The span the position is in is the innermost one whose *opening* tag
    # delimiters cover pos (self-closing tags included). A close tag's own
    # '</name>' is not an open-tag region, so positions there resolve to no
    # span and return None -- the desired behavior.
    containing_pair = _containing_open_tag(
        text, sorted(spans, key=lambda s: s.open_start), None, pos
    )
    if containing_pair is None:
        return None
    containing, containing_open_end = containing_pair

    pair = _attribute_pair_at(text, containing.open_start, containing_open_end, pos)
    if pair is None:
        return None
    attr, value = pair

    names = [containing.name]
    walker = containing
    while walker.depth > 0:
        parent = xml_structure.parent_tag_span(spans, walker)
        if parent is None:
            break
        names.append(parent.name)
        walker = parent
    tag_chain = "/".join(reversed(names))
    return tag_chain, attr, value


def _containing_open_tag(text, spans_sorted, open_starts, pos):
    """Innermost span whose *opening* tag covers ``pos`` as a
    ``(span, real_open_end)`` pair, or None.

    ``spans_sorted`` must be ordered by ``open_start``; ``open_starts`` is the
    matching pre-extracted key list for bisect (pass None to derive it here).

    xml_structure's tag regex uses [^<>], so it truncates an opening tag at
    the first '>' even when that '>' is inside a quoted attribute value. Its
    open_start (and name/chain bookkeeping) is still reliable, so candidates
    come from open_start but the tag's true '>' end is recomputed here
    (``_opening_tag_end``, quote-aware) to stay robust to '>' inside values.

    Instead of the old full pass over every span (O(n) text scans per call --
    the BUG-008 hot spot), walk BACKWARDS from the last span opening at or
    before ``pos``: the first span (i.e. largest open_start) whose real
    opening tag covers ``pos`` is the innermost one. The walk stops at the
    first span that closed at or before ``pos`` -- an element that ended
    before ``pos`` cannot contain it, and neither can anything opened earlier
    (its ancestors' opening tags end before this element even opened) -- so
    the walk is O(depth)-ish, not O(n), for well-formed nesting.
    """
    if open_starts is None:
        open_starts = [s.open_start for s in spans_sorted]
    for i in range(bisect_right(open_starts, pos) - 1, -1, -1):
        span = spans_sorted[i]
        span_end = span.close_end if span.close_end is not None else span.open_end
        if span_end <= pos and span.close_end is not None:
            break
        real_open_end = _opening_tag_end(text, span.open_start)
        if real_open_end is not None and span.open_start <= pos < real_open_end:
            return span, real_open_end
    return None


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


def _attribute_pair_at(text: str, open_start: int, open_end: int, pos: int):
    """Return ``(name, value)`` (value unquoted) for the attribute whose
    name-token or quoted value contains ``pos`` within the opening tag
    spanning ``[open_start, open_end)``, or ``None`` if ``pos`` is over the
    tag name, in an inter-token gap, or on the tag delimiters."""
    tag_text = text[open_start:open_end]
    offset = pos - open_start
    for match in _ATTR_PAIR_RE.finditer(tag_text):
        on_name = match.start(1) <= offset < match.end(1)
        on_value = match.start(2) <= offset < match.end(2)
        if on_name or on_value:
            return match.group(1), match.group(2)[1:-1]
    return None

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

    # Quote handling is TAG-AWARE (BUG-016). The old rule -- "this block ends
    # inside a string if the number of '\"' on it is odd" -- ignored whether a
    # quote could delimit anything at all, so a single quote typed in text
    # content flipped this block's state, which flipped the next block's, and
    # so on with the parity never re-synchronising: Qt cascaded a re-highlight
    # to the END OF THE DOCUMENT on every parity-flipping keystroke (measured:
    # one '\"' = 5,972 highlightBlock calls / 45ms on a 6k-block file). In XML a
    # quote only opens an attribute value INSIDE a tag; in text content -- where
    # .pgtp keeps its PHP event-handler bodies, full of quotes and apostrophes
    # -- quotes are ordinary characters and must not change the state at all.

    def _end_state(self, text: str, state: int) -> int:
        """The block state at the end of `text`, entering it in `state`."""
        for match in _STATE_CHARS_RE.finditer(text):
            char = match.group()
            if state == STATE_NORMAL:
                if char == "<":
                    state = STATE_IN_TAG
            elif state == STATE_IN_TAG:
                if char == ">":
                    state = STATE_NORMAL
                elif char == '"':
                    state = STATE_IN_UNCLOSED_STRING
                elif char == "'":
                    state = STATE_IN_SINGLE_QUOTED
            else:  # inside a quoted attribute value
                closing = '"' if state == STATE_IN_UNCLOSED_STRING else "'"
                if char == closing:
                    state = STATE_IN_TAG
                elif char == "<":
                    # RESYNC (the rule that actually bounds the cascade): a raw
                    # '<' cannot appear inside a well-formed attribute value
                    # (it must be &lt;), so seeing one means our state is wrong
                    # and a tag starts here. Without this, an unterminated quote
                    # inside a tag still flips every following block's state to
                    # EOF; with it the very next tag snaps the state back and
                    # the cascade stops after a block or two. Cost: a raw '<'
                    # typed inside an attribute value ends its highlighting
                    # early -- acceptable, since that document is invalid XML
                    # anyway and it self-corrects once escaped or closed.
                    state = STATE_IN_TAG
        return state

    def _continued_string_end(self, text: str, quote: str) -> int:
        """Index just past a string continued from the previous block: past its
        closing `quote`, at a raw '<' (the resync above), or end of line."""
        for index, char in enumerate(text):
            if char == quote:
                return index + 1
            if char == "<":
                return index
        return len(text)

    def highlightBlock(self, text: str) -> None:
        state = self.previousBlockState()
        if state not in (STATE_IN_TAG, STATE_IN_UNCLOSED_STRING, STATE_IN_SINGLE_QUOTED):
            state = STATE_NORMAL  # includes -1, Qt's "no previous block"
        start = 0
        if state in (STATE_IN_UNCLOSED_STRING, STATE_IN_SINGLE_QUOTED):
            quote = '"' if state == STATE_IN_UNCLOSED_STRING else "'"
            start = self._continued_string_end(text, quote)
            self.setFormat(0, start, self._string_format)

        for match in _TAG_OPEN_RE.finditer(text, start):
            self.setFormat(match.start(), match.end() - match.start(), self._tag_format)
        for match in _TAG_CLOSE_RE.finditer(text, start):
            self.setFormat(match.start(), match.end() - match.start(), self._tag_format)
        for match in _ATTR_NAME_RE.finditer(text, start):
            self.setFormat(match.start(), match.end() - match.start(), self._attr_name_format)
        for match in _ATTR_VALUE_RE.finditer(text, start):
            self.setFormat(match.start(), match.end() - match.start(), self._string_format)

        self.setCurrentBlockState(self._end_state(text, state))


def _cursor_immediately_after_open_tag(line_text: str, position_in_line: int, tag_name: str) -> bool:
    """True if the text on `line_text` immediately before `position_in_line`
    ends with the enclosing tag's own opening `>` and nothing else (i.e.
    there is no content yet between the open tag and the cursor)."""
    before_cursor = line_text[:position_in_line]
    stripped = before_cursor.rstrip()
    return stripped.endswith(">") and f"<{tag_name}" in stripped and not stripped.endswith("/>")


def _closing_tag_start(text: str, span: xml_structure.TagSpan) -> int | None:
    """Delegates to xml_structure.closing_tag_start (kept as a module-local
    name for the highlight call site)."""
    return xml_structure.closing_tag_start(text, span)


class XmlEditor(
    CompletionPopupHostMixin,
    GutterBookmarkFoldMixin,
    SharedEditorMixin,
    VimModeMixin,
    QPlainTextEdit,
):
    """The Raw XML / Edit XSD editor.

    Carries the same family-agnostic layers `CodeEditor` does, all declared
    **before** `QPlainTextEdit`: the shared gutter/bookmark/fold base,
    `SharedEditorMixin` (the ONE hint/refusal path and the ONE line-wrap toggle,
    both lifted for FQ-032 -- this class had no `report_refusal` at all and
    `CodeEditor` had no wrap toggle) and `VimModeMixin` (FQ-032's Edit-mode /
    Command-mode layer).
    """

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
    #
    # EVERY host MUST connect both signals (BUG-049). The key is consumed here
    # whether or not anyone is listening, so an unwired instance does not fall
    # back to native undo -- it swallows Ctrl+Z forever and silently, which is
    # exactly what the FQ-006 draft fragment tab did until it was wired. A host
    # with no snapshot history connects them straight back to `self.undo` /
    # `self.redo` (the Edit XSD tab and the draft tab both do).
    undo_requested = Signal()
    redo_requested = Signal()
    # Emitted when the user picks "Go To XSD" from the editor's right-click
    # context menu, or triggers the window-level Ctrl+L action. Carries the
    # resolved (tag_chain, attr) -- attr is "" when the caret is inside an
    # opening tag but not on a specific attribute. MainWindow opens the Edit
    # XSD tab and navigates to the matching definition line.
    goto_xsd_requested = Signal(str, str)
    # Emitted when Format Selection (§18.4 part C) REFUSES: carries the list of
    # fatal `sql.Issue`s, which MainWindow renders in the Activity Log under the
    # **`[XML]`** prefix (§7 -- non-clickable, no line role, `[SQL]`'s treatment
    # exactly). A new prefix rather than a reuse because an `[SQL]` row saying
    # "this XML selection is mis-nested" would be a lie to the user.
    #
    # A read-only buffer produces NO row here: the gesture emits the existing
    # `read_only_edit_attempted` instead, because the app already has one answer
    # to "you cannot change this buffer" and FQ-021 already lists the reasons on
    # screen. A selection-less Ctrl+Alt+F is a silent no-op, matching both SQL
    # hosts.
    format_refused = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._highlighter = XmlSyntaxHighlighter(self.document())
        # Shared gutter/bookmark/fold base (§8). Set up here -- immediately
        # after the highlighter -- so changeEvent's `hasattr(_highlighter)`
        # guard keeps covering an early ApplicationPaletteChange: by the time
        # that guard passes, _gutter and the fold/bookmark state exist too.
        self._init_gutter_bookmarks_folding()
        # Theme-aware colors. These default to the DARK set; apply_theme_colors
        # swaps the whole set to the LIGHT variant (and back) and is driven
        # automatically off ApplicationPaletteChange in changeEvent, so the
        # editor follows the app's Light/Dark theme. The gutter widget reads
        # _gutter_bg_color/_gutter_fg_color directly when painting.
        # Guard flag: True only while apply_theme_colors's rehighlight() is in
        # flight. Its spurious textChanged (format-only, no text change) would
        # otherwise be indistinguishable from a real edit to MainWindow's
        # dirty-tracking handlers; they check is_applying_theme() and no-op.
        self._applying_theme = False
        # True while a deferred step-2 rehighlight (BUG-013) is queued, so
        # several palette-change events in one toggle coalesce into one.
        self._theme_rehighlight_pending = False
        # Kickoff timer for the deferred step-2 rehighlight (BUG-014): PARENTED
        # to self so ~QWidget cancels a still-pending 0ms tick. An unparented
        # QTimer.singleShot(0, self._rehighlight_for_theme) escapes the
        # editor's lifetime and fires _rehighlight_for_theme on an
        # already-deleted C++ XmlEditor (e.g. a widget torn down between a
        # theme toggle and the next event-loop turn).
        self._theme_kickoff_timer = QTimer(self)
        self._theme_kickoff_timer.setSingleShot(True)
        self._theme_kickoff_timer.setInterval(0)
        self._theme_kickoff_timer.timeout.connect(self._rehighlight_for_theme)
        # Step-2 background sweep state (BUG-013): the timer that re-formats
        # _THEME_SWEEP_BLOCKS_PER_TICK blocks per event-loop turn, and the
        # next block number it resumes from. Timer created on first use.
        self._theme_sweep_timer: QTimer | None = None
        self._theme_sweep_block = 0
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
        # Cached scan() result and the document text it was scanned from,
        # refreshed on every textChanged (see _rescan_structure) so that
        # per-keystroke cursor-move handlers (e.g.
        # _update_matching_tag_highlight) don't have to re-scan -- or even
        # re-copy (toPlainText() copies the whole multi-MB document) -- the
        # document on every arrow key/click. _spans_revision records the
        # document revision the cache was built from, so a consumer can
        # detect staleness (see _update_matching_tag_highlight) if signal
        # order ever changes -- textChanged is expected to fire before
        # cursorPositionChanged, but that ordering is not contractual.
        self._spans: list[xml_structure.TagSpan] = []
        self._spans_text: str = ""
        self._spans_revision: int | None = None
        # Lazy attribute-resolution index over _spans (BUG-008): parent map +
        # spans sorted by open_start (+ the open_start keys for bisect). Built
        # only when resolve_attribute_at actually runs, NOT in
        # _rescan_structure -- rescans happen per keystroke and must not pay
        # the O(n log n) index cost for a feature that may never be used in
        # that revision. Invalidated whenever _spans is rebuilt.
        self._resolution_index: tuple | None = None
        self._nav_click_handled = False
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        # Structure rescan + code-region rebuild are DEBOUNCED (BUG-015).
        # Both are O(document) -- a full toPlainText() copy plus a
        # whole-document regex/handler walk each -- and running them inline
        # on textChanged meant every single keystroke and Enter paid that
        # cost on a multi-MB .pgtp ("painfully slow", the reported symptom).
        # They now run once after the user pauses. Parented QTimer(self),
        # never QTimer.singleShot -- an unparented one fires on a deleted
        # editor (BUG-014).
        self._rescan_timer = QTimer(self)
        self._rescan_timer.setSingleShot(True)
        self._rescan_timer.setInterval(self._RESCAN_DEBOUNCE_MS)
        self._rescan_timer.timeout.connect(self._rescan_now)
        self.textChanged.connect(self._on_text_changed_schedule_rescan)
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
        # chained values) and its wiring state -- see CompletionPopupHostMixin.
        self._init_completion_popup()
        # FQ-032's editing-mode layer. Every editor starts in **Edit mode**,
        # always -- no setting, no persistence, no restore.
        self._init_vim_mode()
        # Format Selection (§18.4 part C): Ctrl+Alt+F, enabled only with a
        # selection. ONE gesture, TWO engines, dispatched by HOST SURFACE and
        # never by sniffing the text -- this class is an XML surface, so it wires
        # `xmlfmt` and the SQL engine is never reachable from here (a text-
        # sniffing dispatcher would eventually guess wrong on a selection that
        # looks like both, e.g. `<x>select 1</x>`).
        #
        # A panel-local `QShortcut` with `WidgetWithChildrenShortcut`, disabled
        # without a selection: the shape both SQL hosts already ship
        # (`ddl_object_editor.py`, `sql_console_panel.py`). It is the gesture's
        # ONLY keyboard host -- there is deliberately NO `keyPressEvent` branch
        # for Ctrl+Alt+F (DEC-004/BUG-046: double-hosting makes Qt fire neither).
        self._format_shortcut = QShortcut(QKeySequence("Ctrl+Alt+F"), self)
        self._format_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._format_shortcut.activated.connect(self.format_selection)
        self._format_shortcut.setEnabled(False)
        self.selectionChanged.connect(self._update_format_shortcut_enabled)
        self._rescan_structure()
        self._refresh_code_region_selections()
        self._highlight_current_line()

    # Idle gap after the last edit before the O(document) structure rescan +
    # code-region rebuild run (BUG-015). Short enough to feel immediate on a
    # typing pause, long enough that a burst of keystrokes coalesces into one
    # rescan. Same debounce shape as MainWindow's snapshot/auto-parse timers.
    _RESCAN_DEBOUNCE_MS = 250

    def _on_text_changed_schedule_rescan(self) -> None:
        """textChanged slot: (re)start the debounce instead of rescanning
        inline (BUG-015). Format-only theme sweeps change no characters, so
        the spans/code-regions cannot differ -- skip them entirely rather
        than scheduling pointless work (this guard used to live inside the
        two handlers themselves)."""
        if self._applying_theme:
            return
        self._rescan_timer.start()

    def _rescan_now(self) -> None:
        """Run the debounced work immediately: structure first (code regions
        and the matching-tag highlight both read fresh `_spans`), then the
        code-region rebuild, then repaint the layers that were showing stale
        or suppressed state during the debounce window -- the matching-tag
        highlight (suppressed while stale, see _update_matching_tag_highlight)
        and the gutter (fold glyphs are derived from `_spans`)."""
        self._rescan_timer.stop()
        self._rescan_structure()
        self._refresh_code_region_selections()
        self._update_matching_tag_highlight()
        self._gutter.update()

    def _flush_pending_rescan(self) -> None:
        """Force the debounced rescan to complete NOW if one is pending.
        Call this from any deliberate user action that must see exact
        structure (e.g. folding) rather than up-to-`_RESCAN_DEBOUNCE_MS`-old
        spans. Cheap no-op when nothing is pending."""
        if self._rescan_timer.isActive():
            self._rescan_now()

    def setPlainText(self, text: str) -> None:
        """Load/replace the whole document. Unlike incremental typing this is
        a document SWAP whose structure must be correct immediately (BUG-015
        gotcha): callers load a file, revert, or write a rename through the
        buffer and then read spans / fold regions / code regions / the
        matching-tag highlight straight away. So run the debounced work
        synchronously here rather than leaving it `_RESCAN_DEBOUNCE_MS` in the
        future. Costs one scan per load, which a load already pays for in the
        document copy anyway -- the debounce exists for per-keystroke edits."""
        super().setPlainText(text)
        self._rescan_now()

    def _toggle_fold(self, block) -> None:
        """Folding is a deliberate user action and must act on exact spans --
        flush any pending debounced rescan first (BUG-015), then defer to the
        shared gutter mixin. NOTE: the flush belongs here, NOT inside
        `_foldable_region_starting_at`: the gutter's paintEvent calls that
        hook for every visible block, so rescanning there would fire on every
        repaint (i.e. every keystroke) and silently undo the whole debounce."""
        self._flush_pending_rescan()
        super()._toggle_fold(block)

    def is_applying_theme(self) -> bool:
        """True only while apply_theme_colors's rehighlight() is in flight.
        Dirty-tracking handlers listening on textChanged should check this
        and no-op -- rehighlight reformats the whole document (a real Qt
        textChanged fires) even though no character of text changed."""
        return self._applying_theme

    def apply_theme_colors(self, light: bool) -> None:
        """Swap the editor's color attributes and the syntax highlighter's
        format colors between a LIGHT set (readable dark-on-white) and the DARK
        set (the original values), then rehighlight and repaint so the change
        shows immediately -- gutter, current-line band, matching-tag spans and
        code-region backgrounds all recolor at once. Wired to run automatically
        on ApplicationPaletteChange via changeEvent."""
        self._apply_gutter_theme_colors(light)
        if light:
            self._current_line_color = QColor("#eef1f7")
            self._error_line_color = QColor("#f7d4d4")
            self._navigation_highlight_color = QColor("#cfe0ff")
            self._matching_tag_color = QColor("#d3ecd3")
            self._code_region_color = QColor("#eef2f5")
            self._highlighter.set_colors(
                tag="#0000ff", attr_name="#e50000", string="#a31515"
            )
        else:
            self._current_line_color = QColor("#2d2d30")
            self._error_line_color = QColor("#5a1d1d")
            self._navigation_highlight_color = QColor("#264f78")
            self._matching_tag_color = QColor("#3a5f3a")
            self._code_region_color = QColor("#232a2f")
            self._highlighter.set_colors(
                tag="#569cd6", attr_name="#9cdcfe", string="#ce9178"
            )
        # Rebuild the extra-selection layers so their stored per-selection
        # colors pick up the new values (they cache the color at build time).
        self._refresh_code_region_selections()
        self._update_matching_tag_highlight()
        self._highlight_current_line()
        self._gutter.update()
        # Two-step theme change (BUG-013): the app-wide coloring (palette +
        # QSS re-polish) paints FIRST; the whole-document syntax rehighlight
        # -- ~1.5s on a multi-MB .pgtp, the dominant per-toggle cost -- runs
        # as a single deferred call after the app coloring has returned, so
        # the theme flip is visible immediately and the text recolors as a
        # visible second step. Coalesced: several palette-change events in
        # one toggle schedule only one rehighlight.
        if not self._theme_rehighlight_pending:
            self._theme_rehighlight_pending = True
            # Parented single-shot timer, not QTimer.singleShot (BUG-014): the
            # unparented form fires on an already-deleted editor.
            self._theme_kickoff_timer.start()

    # Blocks re-formatted per event-loop turn during the step-2 sweep. Small
    # enough that each turn stays well under a frame, large enough that even
    # a huge .pgtp finishes in a couple of seconds of BACKGROUND sweeping
    # while the UI keeps responding.
    _THEME_SWEEP_BLOCKS_PER_TICK = 400

    def _rehighlight_for_theme(self) -> None:
        """Step 2 of the theme change: re-apply character formats with the
        colors apply_theme_colors already swapped in -- visible region first
        (so what's on screen recolors together with the app chrome), then the
        rest of the document swept a fixed number of blocks per event-loop
        turn so a multi-MB document never freezes the UI (BUG-013: a single
        synchronous rehighlight() blocked ~1.5s+).

        rehighlightBlock() reports through the same textChanged path as a
        real edit -- with no text actually changing. The _applying_theme
        guard wraps every batch: MainWindow's dirty handlers check
        is_applying_theme() and no-op, and this editor's own textChanged
        bookkeeping (_rescan_structure/_refresh_code_region_selections)
        skips format-only batches the same way -- otherwise every sweep turn
        would trigger a full-document structure rescan."""
        self._theme_rehighlight_pending = False
        # Recolor what the user is actually looking at, immediately.
        self._applying_theme = True
        try:
            block = self.firstVisibleBlock()
            bottom = self.viewport().rect().bottom()
            while block.isValid():
                geo = self.blockBoundingGeometry(block).translated(self.contentOffset())
                if geo.top() > bottom:
                    break
                self._highlighter.rehighlightBlock(block)
                block = block.next()
        finally:
            self._applying_theme = False
        # Sweep the rest from the top, one batch per event-loop turn. A new
        # theme change while a sweep is running restarts it from block 0 with
        # the new colors (apply_theme_colors always schedules a fresh step 2,
        # and _theme_sweep_block resets here).
        self._theme_sweep_block = 0
        if self._theme_sweep_timer is None:
            self._theme_sweep_timer = QTimer(self)
            self._theme_sweep_timer.setInterval(0)
            self._theme_sweep_timer.timeout.connect(self._theme_sweep_tick)
        self._theme_sweep_timer.start()

    def _theme_sweep_tick(self) -> None:
        doc = self.document()
        block = doc.findBlockByNumber(self._theme_sweep_block)
        self._applying_theme = True
        try:
            remaining = self._THEME_SWEEP_BLOCKS_PER_TICK
            while block.isValid() and remaining > 0:
                self._highlighter.rehighlightBlock(block)
                block = block.next()
                remaining -= 1
        finally:
            self._applying_theme = False
        if block.isValid():
            self._theme_sweep_block = block.blockNumber()
        else:
            self._theme_sweep_timer.stop()

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
        # Format-only rehighlight batches (theme step-2 sweep, BUG-013) fire
        # textChanged without any character changing -- the spans cannot
        # differ, so skip the full-document copy + scan. Consumers'
        # revision guards lazily rescan later if the revision moved.
        if self._applying_theme:
            return
        self._spans_text = self.toPlainText()
        self._spans = xml_structure.scan(self._spans_text)
        self._spans_revision = self.document().revision()
        self._resolution_index = None  # spans changed; rebuild lazily (BUG-008)

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
        # Skip format-only rehighlight batches (theme step-2 sweep, BUG-013):
        # no text changed, so the ranges are identical -- and
        # apply_theme_colors calls this explicitly (outside the guard) for
        # the color swap, so the recolor still happens exactly once.
        if self._applying_theme:
            return
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
        # Use the cached spans instead of rescanning the whole document on
        # every cursor move -- see the _spans/_spans_revision comment in
        # __init__.
        #
        # BUG-015: this must NOT rescan when the cache is stale. Typing moves
        # the caret, so cursorPositionChanged fires on every keystroke; a
        # rescan-if-stale here would run the full-document scan per character
        # and completely defeat the textChanged debounce (this path, not
        # textChanged, was the remaining per-keystroke stall). While the cache
        # is stale the cached spans' character offsets refer to the PRE-edit
        # text, so highlighting from them would paint a visibly wrong range --
        # worse than none. Clear the highlight and return; _rescan_now
        # re-invokes this once the debounced rescan lands, a few hundred ms
        # later, and the correct highlight appears then.
        if self.document().revision() != self._spans_revision:
            self._matching_tag_selections = []
            self._refresh_extra_selections()
            return
        # By the revision invariant just enforced, _spans_text is identical
        # to what toPlainText() would return -- but without re-copying the
        # whole document on every cursor move.
        text = self._spans_text
        position = self.textCursor().position()
        span = xml_structure.enclosing_tag_span_from_spans(self._spans, position)
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

    def supports_structural_expansion(self) -> bool:
        """`Select ▸ Expand Selection` is always available on an XML document.

        The predicate exists because `CodeEditor`'s answer is a **per-instance**
        fact (only `language == "sql"` has a plpgsql ladder), which the old
        `hasattr(editor, "select_parent_block")` gate could not express -- so both
        families answer one question instead (§8, FQ-034). Here it is
        unconditional: every `XmlEditor` instance holds XML.

        Note the asymmetry this class deliberately keeps: there is **no**
        `shrink_structural_selection` here. XML's grow is stateless and
        re-derived from `selectionStart()` each press, so shrink would need an
        expansion stack on this class too -- a second host for that state, for a
        family whose users did not ask for it. `Shrink Selection` is therefore
        hidden on XML tabs, and `Ctrl+Shift+Z` stays claimed-and-inert there.
        """
        return True

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

    def resolve_attribute_at(self, pos: int):
        """Cache-aware ``(tag_chain, attr)`` resolution at document position
        `pos` -- the entry point PropertiesPanel/hover-hint callers should use
        instead of the module-level `attribute_at_position(toPlainText(), pos)`,
        which always re-scans the whole document. Same staleness guard as
        `_update_matching_tag_highlight`: rescan only if the document changed
        since the cache was last built.

        BUG-008: resolution runs O(log n + depth) against a lazily built,
        revision-guarded index (spans sorted by open_start for bisect + a
        build_parent_map ancestor map) instead of the module function's
        per-call full-span pass and per-level parent_tag_span scans --
        PropertiesPanel calls this once per attribute row on every tree
        selection, so the per-call cost is what makes selection feel instant
        vs. frozen on ~37k-tag documents."""
        if self.document().revision() != self._spans_revision:
            self._rescan_structure()
        if self._resolution_index is None:
            spans_sorted = sorted(self._spans, key=lambda s: s.open_start)
            self._resolution_index = (
                spans_sorted,
                [s.open_start for s in spans_sorted],
                xml_structure.build_parent_map(self._spans),
            )
        spans_sorted, open_starts, parent_map = self._resolution_index

        containing_pair = _containing_open_tag(
            self._spans_text, spans_sorted, open_starts, pos
        )
        if containing_pair is None:
            return None
        containing, containing_open_end = containing_pair
        pair = _attribute_pair_at(
            self._spans_text, containing.open_start, containing_open_end, pos
        )
        if pair is None:
            return None
        attr, _value = pair

        names = [containing.name]
        walker = containing
        while walker is not None:
            parent = parent_map.get(id(walker))
            # A '>' inside a quoted attribute value leaves that tag's span
            # unclosed (close_end=None), and build_parent_map keeps such a
            # span on its ancestor stack forever -- polluting every later
            # element's chain with a false ancestor. A real parent is exactly
            # one depth level up (the same filter parent_tag_span applies),
            # so climb past any ancestor at the wrong depth.
            while parent is not None and parent.depth != walker.depth - 1:
                parent = parent_map.get(id(parent))
            if parent is None:
                break
            names.append(parent.name)
            walker = parent
        return "/".join(reversed(names)), attr

    def replace_current_selection(self, text: str) -> None:
        """Replace the current selection's text with `text` as a single undo
        step. No-op if there is no selection. Used by FindReplaceBar's
        Replace (Search & Replace sub-project)."""
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return
        cursor.insertText(text)  # QTextCursor.insertText replaces the selection
        self.setTextCursor(cursor)

    # `set_line_wrap_enabled` / `is_line_wrap_enabled` moved to
    # `SharedEditorMixin` (`ui/editor_shared.py`), unchanged. FQ-032's
    # `:set wrap` / `:set nowrap` is family-agnostic and `CodeEditor` had no
    # toggle at all, and a family-agnostic layer may not be given a private copy
    # of something one family already implements. The context menu's checkable
    # `Wrap Lines` entry still drives exactly this method.

    def vim_undo(self) -> None:
        """`u` in Command mode routes to THIS surface's undo answer -- the
        window's document-level snapshot history, which is what `Ctrl+Z` does
        here. Never `QPlainTextEdit.undo()`: that is `F14`'s recorded defect
        (undo that bypasses the app's routing), and reproducing it on a reachable
        key would be worse."""
        self.undo_requested.emit()

    def vim_redo(self) -> None:
        """`Ctrl+R` in Command mode -- Command-mode ONLY
        (`DEC-260810193638`); `Ctrl+Y` remains the app's redo everywhere."""
        self.redo_requested.emit()

    @staticmethod
    def _is_text_modifying_key(event: QKeyEvent) -> bool:
        """True if `event` would mutate the document: a printable character,
        one of Backspace/Delete/Return/Enter, or a paste (Ctrl+V). Used only
        in read-only mode to decide whether to emit read_only_edit_attempted.

        A Ctrl/⌘ chord is a COMMAND, never typing, so it is excluded before the
        printable-text test (FQ-015). `event.text()` for Ctrl+A is the control
        character "\\x01" on Windows/Linux, which is not printable — but it is the
        bare letter on some platforms and under `QTest.keyClick`, and treating
        that as an edit attempt made a read-only editor SWALLOW Ctrl+A (and every
        other Ctrl+letter command) while flashing the "this editor is read-only"
        hint. Paste is checked first and keeps its hint: Ctrl+V really is an edit
        attempt.

        The paste test goes through `is_paste_chord`, which reads the app's own
        `EDITOR_PASTE_CHORDS`, and NOT through
        `event.matches(QKeySequence.StandardKey.Paste)`: that call answers Qt's
        per-scheme table, so the hint used to fire for `Ctrl+Shift+Ins` and `F18`
        on Linux and for neither on Windows (DEC-015 -- a chord means the same
        thing on both systems or the app does not claim it).
        """
        if is_paste_chord(event):
            return True
        # The three line-editing gestures the app took ownership of on
        # 2026-08-10 (`Ctrl+D`/`Ctrl+K`/`Ctrl+U`) are Ctrl chords, so the
        # command-not-typing test below would call them "not an edit" -- and
        # `Ctrl+U` deletes a whole line, which is the most edit-like keystroke on
        # this list. They get the hint for exactly the reason `Ctrl+V` does.
        if is_mutating_editor_operation(classify_editor_chord(event)):
            return True
        if event.key() in (
            Qt.Key.Key_Backspace,
            Qt.Key.Key_Delete,
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        ):
            return True
        if event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier
        ):
            return False
        return bool(event.text()) and event.text().isprintable()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.isReadOnly() and self._is_text_modifying_key(event):
            # Caption Mode: the base QPlainTextEdit already refuses the edit
            # when read-only; the only added behavior is a non-modal hint.
            self.read_only_edit_attempted.emit()
            return

        # Route Ctrl+Z / Ctrl+Y to the document-level snapshot undo/redo
        # (MainWindow) rather than QPlainTextEdit's native char-level undo,
        # which would otherwise win while the editor has focus (C1). Consume the
        # key here so the coexisting window QShortcut does not also fire (no
        # double-undo).
        #
        # The chord set and the classification come from the ONE matcher every
        # editing surface calls (DEC-014's fixed set, `code_editor`); this
        # surface must not spell the chords out for itself.
        operation = classify_editor_chord(event)
        if operation == UNDO:
            self.undo_requested.emit()
            event.accept()
            return
        if operation == REDO:
            self.redo_requested.emit()
            event.accept()
            return
        if is_mutating_editor_operation(operation):
            # Paste (`Ctrl+Shift+Insert`) and the three line-editing gestures
            # (`Ctrl+D`/`Ctrl+K`/`Ctrl+U`), which Qt answers on the Linux/KDE
            # scheme only and the app therefore implements on both (owner,
            # 2026-08-10). A read-only Caption Mode buffer never reaches here:
            # `_is_text_modifying_key` counts these as edit attempts, so the
            # read-only branch above already emitted the hint and returned.
            apply_editor_operation(self, operation)
            event.accept()
            return
        if operation == CLAIMED_NOT_UNDO_REDO:
            # `Ctrl+Shift+Z` = Shrink Selection (FQ-034), delegated to the one
            # implementation every surface calls. **On this family it is inert,
            # and that is a scope decision with a reason rather than an
            # omission** (§8): XML's grow (`select_parent_block`) is stateless
            # and re-derivable, so giving XML shrink would mean giving
            # `XmlEditor` the expansion stack as well -- a second host for that
            # state, for a family whose users did not ask for it. This editor
            # therefore has no `shrink_structural_selection` at all, the shared
            # helper finds none, and the chord is consumed exactly as before.
            #
            # Consuming it is the load-bearing half either way: DEC-015 freed
            # the chord from redo, but Qt binds it as native Redo under
            # `KB_Win | KB_X11`, so dropping the interception would leave Qt
            # redoing anyway.
            apply_shrink_structural_selection(self)
            event.accept()
            return
        if operation is not None:
            # `Alt+Backspace` / `Alt+Shift+Backspace` -- suppressed app-wide, so
            # the keyboard is identical on both systems (Qt binds them `KB_Win`
            # only). Consumed rather than passed on: the interception IS the
            # behaviour.
            event.accept()
            return

        # FQ-032's editing-mode layer, HERE: after the read-only branch (row 5 of
        # the `Esc` precedence order -- vim is inactive entirely on a read-only
        # buffer) and after the `classify_editor_chord` block, so `Ctrl+Z`,
        # `Ctrl+Y` and `Ctrl+D`/`Ctrl+K`/`Ctrl+U` keep this surface's answers.
        # Those three are declined for a Command-mode editor inside
        # `apply_editor_operation`, in ONE place, never here.
        if self.handle_command_mode_key(event):
            event.accept()
            return

        mods = event.modifiers()
        ctrl = Qt.KeyboardModifier.ControlModifier
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
        # "Go To XSD" jumps to the curated XSD definition for the element/
        # attribute under the caret. Offered only when a schema model is
        # loaded and the caret sits inside an opening tag.
        if (
            self._schema_model is not None
            and enclosing_open_tag(self.toPlainText(), cursor.position()) is not None
        ):
            goto_xsd_action = QAction("Go To XSD", menu)
            goto_xsd_action.triggered.connect(self.request_goto_xsd)
            if before is not None:
                menu.insertAction(before, goto_xsd_action)
            else:
                menu.addAction(goto_xsd_action)
        # "Wrap Lines" toggles soft line-wrapping of the Raw XML editor. It is
        # checkable and reflects the editor's current wrap state each time the
        # menu is built, and toggling it drives set_line_wrap_enabled.
        menu.addSeparator()
        wrap_action = QAction("Wrap Lines", menu)
        wrap_action.setCheckable(True)
        wrap_action.setChecked(self.is_line_wrap_enabled())
        wrap_action.toggled.connect(self.set_line_wrap_enabled)
        menu.addAction(wrap_action)
        # "Format Selection" (§18.4 part C) -- the gesture's COMMAND form, which
        # this menu makes free (the SQL console has no context menu at all, which
        # is why the chord is its only form there). It carries NO shortcut of its
        # own: the panel-local QShortcut is the single keyboard host.
        format_action = QAction("Format Selection", menu)
        format_action.setEnabled(cursor.hasSelection() and not self.isReadOnly())
        format_action.triggered.connect(self.format_selection)
        menu.addAction(format_action)
        return menu

    # --- Format Selection (§18.4 part C: the XML indentation engine) --------

    def _update_format_shortcut_enabled(self) -> None:
        self._format_shortcut.setEnabled(self.textCursor().hasSelection())

    def format_selection(self) -> bool:
        """Reindent the selected XML by element-nesting depth, in place.

        Indentation only -- `xmlfmt` never touches element text, never breaks an
        opening tag, and never enters a comment/CDATA/PI/DOCTYPE (§18.4 C's three
        rules, each derived from §2's `.pgtp` layout guarantees). Returns True
        when the buffer was rewritten.

        THE DOCUMENT, NOT JUST THE SELECTION, is handed to the engine: the whole
        reason a user reformats a fragment is that its indentation is wrong, so
        the base depth must come from the selection's POSITION in the document
        rather than from its own first line -- the one place the XML engine
        deliberately diverges from the SQL engine's behaviour.

        Three outcomes besides success, and none of them is a new channel:
        * read-only buffer -> the existing `read_only_edit_attempted` signal (no
          `[XML]` row: FQ-021 already lists the reasons on screen);
        * no selection -> silent no-op, as on both SQL hosts;
        * refusal -> the selection is left byte-for-byte unchanged, the offending
          span is underlined, and `format_refused` carries the issues to the
          `[XML]` Audit prefix.
        """
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return False
        if self.isReadOnly():
            self.read_only_edit_attempted.emit()
            return False
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        result = format_xml_selection(
            self.toPlainText(), start, end, config=current_xml_config()
        )
        if result.ok:
            if result.text != self.toPlainText()[start:end]:
                span = self._make_span_cursor(start, end)
                span.beginEditBlock()  # one undo step for the whole reformat
                span.insertText(result.text)
                span.endEditBlock()
            return True
        self._underline_format_refusal(result.issues)
        self.format_refused.emit(list(result.issues))
        return False

    def _underline_format_refusal(self, issues) -> None:
        """Wave-underline the FIRST refused span (document offsets).

        One span, not all of them, because `_set_oneshot_selection` is this
        editor's single "overriding indicator" slot and the XML engine's refusals
        are singular by construction anyway -- an unterminated construct is
        reported alone, a split boundary names one construct, and the mis-nesting
        walk stops at the first offender. Transient like every other one-shot:
        cleared on the next cursor move.
        """
        if not issues:
            return
        issue = issues[0]
        selection = QTextEdit.ExtraSelection()
        fmt = QTextCharFormat()
        fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
        fmt.setUnderlineColor(QColor("red"))
        selection.cursor = self._make_span_cursor(issue.start, issue.end)
        selection.format = fmt
        self._set_oneshot_selection(selection)

    def _emit_find_selected_text(self) -> None:
        # QTextCursor.selectedText() uses U+2029 (paragraph separator) to join
        # lines of a multi-line selection; collapse those to spaces so the find
        # term is a plain string. Single-line selections (the norm) are
        # unaffected.
        selected = self.textCursor().selectedText().replace(chr(0x2029), chr(32))
        self.find_selected_text.emit(selected)

    def contextMenuEvent(self, event) -> None:
        # event.pos() is delivered in this widget's own coordinates, but
        # cursorForPosition expects viewport coordinates (same translation
        # the ToolTip handler in event() does, and for the same reason) --
        # without it, a right-click on value B while the caret sits on value
        # A would build the menu (and resolve "Add attribute", "Edit
        # code...") against the stale caret at A instead of the
        # actually-clicked position.
        viewport_pos = self.viewport().mapFrom(self, event.pos())
        doc_pos = self.cursorForPosition(viewport_pos).position()
        self._prepare_context_menu_at(doc_pos)
        menu = self._build_context_menu()
        menu.exec(event.globalPos())

    def _prepare_context_menu_at(self, doc_pos: int) -> None:
        """Move the caret to ``doc_pos`` so the context menu built right
        after this call reflects the right-clicked position rather than a
        stale caret left over from an earlier click or edit. Split out from
        contextMenuEvent so tests can drive it directly with a document
        position instead of synthesizing a QContextMenuEvent.

        Leaves the caret (and selection) untouched when ``doc_pos`` falls
        inside the current selection: right-clicking inside a selection must
        not destroy it, since the "Find" action depends on that selection
        surviving the right-click. Standard editor behavior."""
        cursor = self.textCursor()
        if cursor.hasSelection():
            start, end = cursor.selectionStart(), cursor.selectionEnd()
            if start <= doc_pos <= end:
                return
        new_cursor = QTextCursor(self.document())
        new_cursor.setPosition(doc_pos)
        self.setTextCursor(new_cursor)

    def set_schema_model(self, model) -> None:
        """Inject the current in-memory schema Model (or None). Passed by
        MainWindow after each enrich so hover tooltips and completion
        reflect the latest labels; None disables them (default)."""
        self._schema_model = model

    def schema_model(self):
        """The injected schema Model, or None. Read-only accessor used by
        tests and callers that need to check whether a schema is loaded."""
        return self._schema_model

    def request_goto_xsd(self) -> bool:
        """Resolve the caret to (tag_chain, attr) -- attr "" when the caret is
        inside an opening tag but not on an attribute -- and emit
        goto_xsd_requested. False when no model or unresolvable."""
        if self._schema_model is None:
            return False
        text = self.toPlainText()
        pos = self.textCursor().position()
        resolved = attribute_value_at_position(text, pos)
        if resolved is not None:
            tag_chain, attr, _value = resolved
            self.goto_xsd_requested.emit(tag_chain, attr)
            return True
        enclosing = enclosing_open_tag(text, pos)
        if enclosing is None:
            return False
        tag_chain, _present, _insert = enclosing
        self.goto_xsd_requested.emit(tag_chain, "")
        return True

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
        resolved = self.resolve_attribute_at(char_pos)
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

    def mousePressEvent(self, event) -> None:
        # Ctrl+left-click jumps to the matching open/close tag; Alt+left-click
        # jumps to the parent element's opening tag. Handled at PRESS (not
        # release) so accepting the event suppresses Qt's Alt+drag column
        # selection and leaves no stray selection at the destination.
        if event.button() == Qt.MouseButton.LeftButton:
            ctrl = Qt.KeyboardModifier.ControlModifier
            alt = Qt.KeyboardModifier.AltModifier
            mods = event.modifiers()
            if mods == ctrl or mods == alt:
                click_pos = self.cursorForPosition(
                    event.position().toPoint()
                ).position()
                if self.document().revision() != self._spans_revision:
                    self._rescan_structure()
                if mods == ctrl:
                    target = xml_structure.matching_tag_target(
                        self._spans, self._spans_text, click_pos
                    )
                else:
                    target = xml_structure.parent_tag_target(
                        self._spans, click_pos
                    )
                if target is not None:
                    cursor = self.textCursor()
                    cursor.setPosition(target)
                    self.setTextCursor(cursor)
                    self.ensureCursorVisible()
                    self._nav_click_handled = True
                    self.line_clicked.emit(cursor.blockNumber() + 1)
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        # A modifier-jump handled the matching press; consume the release too so
        # Qt's default release handling doesn't reposition the caret back to the
        # click point (which would undo the jump and misreport line_clicked).
        if self._nav_click_handled:
            self._nav_click_handled = False
            event.accept()
            return
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
