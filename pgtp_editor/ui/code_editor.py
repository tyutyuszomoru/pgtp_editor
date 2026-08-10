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
(``CodeEditorDialog``) with OK/Cancel buttons and no keyboard shortcuts.

The auto-close behavior mirrors XmlEditor's approach: the editor tracks the
closer characters it itself inserted (as QTextCursors so their positions
self-adjust) so that "type-through" only skips over a closer this editor
auto-inserted, never an arbitrary pre-existing one.

``CodeEditor`` is also where FQ-030's **one** template-expansion path lives:
`apply_expansion` takes an `sql/templates.py::Expansion` -- from a keyword
snippet or from expand-`SELECT`, which are one mechanism and not two -- applies
it as a single undo, and walks its tab stops on Tab. See the "Template
expansion" section on the class.
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
    QToolTip,
    QVBoxLayout,
)

from pgtp_editor.sql.keywords import SQL_KEYWORDS
from pgtp_editor.sql.templates import (
    DEFAULT_SNIPPETS,
    Expansion,
    Snippet,
    expand_template,
    find_snippet,
)
from pgtp_editor.ui.editor_gutter import GutterBookmarkFoldMixin
from pgtp_editor.ui.shortcut_registry import (  # noqa: F401  (re-exported names)
    CLAIMED_NOT_UNDO_REDO,
    EDITOR_UNDO_REDO_CHORDS,
    REDO,
    SUPPRESSED,
    UNDO,
)

# The three operation names are re-exported deliberately: a surface imports the
# matcher and the answers it can return from ONE module, and never spells a
# chord out for itself.


# -- the one undo/redo chord matcher every editing surface calls (DEC-014) ----
#
# DEC-014, verbatim: *"For every chord `RESERVED_SEQUENCES` reserves because an
# editor answers it, every editing surface states its answer."* The set is
# therefore **fixed** and this function takes **no per-surface parameter** -- the
# rejected alternative (option B, a per-surface chord list) was rejected because
# per-surface variation is how BUG-053 happened.
#
# It **classifies** -- undo, redo, or claimed-but-neither -- and deliberately
# never returns a bare boolean. DEC-014 spells out why: a caller that gets
# "yes, an undo/redo chord" and re-derives which one is how a redo silently
# becomes an undo. Only the MATCHING is shared here; the ANSWER stays per
# surface, because the answers genuinely differ (own undo stack / a stated
# refusal on a read-only buffer / re-emission into the project's snapshot
# history), and four sites hand-repeating the match is what made this the fourth
# Ctrl+Z-family bug (BUG-048, BUG-049, BUG-053, BUG-056).
#
# Parsed from the registry's chord strings so the set has exactly one source. A
# QKeySequence spelling is turned into the (key, modifiers) pair a QKeyEvent
# carries; nothing here consults Qt's platform-dependent StandardKey table,
# which is the whole point (DEC-015: *"an operation's chord is bound by this
# app, not inherited from Qt's platform table"*).
def _chord_combinations() -> dict[tuple[int, Qt.KeyboardModifier], str]:
    table: dict[tuple[int, Qt.KeyboardModifier], str] = {}
    for sequence, operation in EDITOR_UNDO_REDO_CHORDS.items():
        combination = QKeySequence(sequence)[0]
        table[(combination.key(), combination.keyboardModifiers())] = operation
    return table


_UNDO_REDO_COMBINATIONS = _chord_combinations()


def classify_undo_redo_chord(event) -> str | None:
    """`UNDO`, `REDO`, `CLAIMED_NOT_UNDO_REDO`, `SUPPRESSED`, or None.

    **Any non-None answer must be consumed by the caller**, including the two
    that run no operation. Neither is an "ignore me": letting the key fall
    through hands it to Qt, whose compiled binding table is per-platform, and
    then the app has two different keyboards.

    - `CLAIMED_NOT_UNDO_REDO` -- `Ctrl+Shift+Z`, which Qt binds as
      `StandardKey.Redo` under `KB_Win | KB_X11` (BUG-056 read both schemes).
      DEC-015 freed it from redo, so every surface must actively refuse Qt's
      answer; FQ-034 will bind shrink-selection there.
    - `SUPPRESSED` -- `Alt+Backspace` / `Alt+Shift+Backspace`, which Qt binds as
      native Undo/Redo under `KB_Win` **only**. Suppressed on every platform, per
      the owner's rule that a chord means the same thing on Windows and Linux or
      is not bound at all.
    """
    return _UNDO_REDO_COMBINATIONS.get((event.key(), event.modifiers()))


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
# The set itself lives in the Qt-free `sql/` core (§18.4) so the highlighter and
# the selection formatter share ONE dialect source without dragging Qt into that
# core -- ui depends on core, never the other way round. Same object, so
# `_highlighter._keywords is _SQL_KEYWORDS` still holds.
_SQL_KEYWORDS = SQL_KEYWORDS

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

    #: Emitted when an expansion gesture (snippet or expand-`SELECT`) refuses,
    #: carrying the reason fit to show the user -- never on success. The same
    #: "report outward, never reach into MainWindow" precedent as
    #: `DdlObjectEditorPanel.format_refused`; a host that connects nothing
    #: still sees the reason, because `report_refusal` also shows it as a
    #: transient tooltip at the caret (the status bar is static since FQ-028).
    expansion_refused = Signal(str)

    #: Emitted for every transient caret hint this editor shows -- a refusal
    #: (which also emits `expansion_refused`) or an answer, e.g. signature help
    #: (FQ-030 slice 3). It exists because `QToolTip` shows nothing at all under
    #: the offscreen platform, so this is the only thing a test can observe;
    #: hosts are free to ignore it, and all of them do.
    hint_shown = Signal(str)

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

        # Template expansion (FQ-030). The snippet set is the shipped plpgsql
        # default until someone installs another via `set_snippets`; the
        # schema-dynamic expander is unwired until a panel that HAS a
        # `SchemaIndex` supplies one. Tab-stop mode is off, which is the state
        # every editor is in except right after an expansion -- see
        # `in_tab_stop_mode`.
        self._snippets: tuple[Snippet, ...] = DEFAULT_SNIPPETS
        self._dynamic_expander = None
        self._tab_stop_cursors: list[QTextCursor] = []
        self._tab_stop_index = 0

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

    # --- Template expansion: the ONE application path (FQ-030) -------------
    #
    # `sql/templates.py` states the insight this half exists to honor: keyword
    # snippets and expand-`SELECT` are ONE mechanism -- both hand back an
    # `Expansion` (text + span + caret + tab stops) and both are applied here,
    # by `apply_expansion`, in one undo block. There is deliberately no second
    # insertion path: a caller that wants to insert something computes an
    # `Expansion` for it.
    #
    # **Explicit-trigger only, like Ctrl+Space completion (§18.6).** Nothing
    # here is connected to `textChanged`: the expansion gestures run from a key
    # press and nowhere else, so the expensive resolvers they call
    # (`resolve_caret_context`, `analyze_from_items`) are paid once per
    # deliberate keystroke rather than once per typed character.

    def set_snippets(self, snippets) -> None:
        """Install the snippet set the expand gesture matches against.

        The seam the user-defined store layers over the shipped defaults
        through: `sql/templates.py::find_snippet` already takes a `snippets`
        argument for exactly this, so the store never forks the engine.
        `None` restores `DEFAULT_SNIPPETS`.

        **The store now exists** and this is what installs it:
        `sql/snippet_store.py` owns the format, `ui/snippet_controller.py`
        resolves the one per-user file (DEC-001: the app's own folder, never
        the `.pgtp` artifact) and `CenterStage.set_snippets` fans the loaded set
        out over every SQL editor -- including tabs opened later. Nothing in
        this widget had to change when it landed, which was the point of
        putting the seam here first: this class still knows only "a set of
        `Snippet`s", never where one came from or whether the user wrote it.
        """
        self._snippets = (
            DEFAULT_SNIPPETS if snippets is None else tuple(snippets)
        )

    def snippets(self) -> tuple[Snippet, ...]:
        """The snippet set in force -- the shipped defaults unless replaced."""
        return self._snippets

    @property
    def language(self) -> str:
        """`"sql"` / `"php"` / `"js"` -- which highlighter and which gestures.

        Public because a host that fans a setting out over its editors has to
        be able to tell them apart: the snippet set is plpgsql, so only the SQL
        ones may be given it (the same reason `keyPressEvent` gates Ctrl+Alt+E).
        """
        return self._language

    def set_dynamic_expander(self, expander) -> None:
        """Wire the schema-dynamic expansion seam, or `None` to unwire it.

        `expander(text, pos) -> Expansion | None` is called by
        `expand_select_at_caret`. It lives OUTSIDE this widget because it needs
        a `SchemaIndex`, which no editor may hold (§18.5 D1: the panel never
        talks to a database, and this widget knows even less than a panel).
        The hosting panel supplies a three-line adapter over
        `sql/expand_select.py`. Unwired (the default -- Raw XML, PHP tabs, the
        read-only DDL Explorer buffer) the gesture states that it has no schema
        rather than doing nothing.
        """
        self._dynamic_expander = expander

    def apply_expansion(self, expansion: Expansion) -> bool:
        """Apply `expansion` -- the one insertion path. Returns whether it ran.

        Replaces `[start, end)` with the expansion's text **in a single undo
        block**, so one Ctrl+Z takes the whole expansion back however many
        template pieces it was built from. The caret then lands on the
        expansion's first tab stop (which, for a template whose only stop is
        `{{0}}`, IS `expansion.caret`), or at `expansion.caret` when the
        template declares no stops at all.

        Tab-stop mode is entered only when the expansion has a stop the user
        can actually walk TO -- i.e. at least one non-final stop. A template
        whose sole stop is the final caret has nowhere for Tab to go, so the
        editor stays in its ordinary state and Tab keeps inserting a tab, which
        is what someone typing a `WHERE` condition right after expand-`SELECT`
        expects.

        A falsy `Expansion` is NOT applied and is NOT silent: its `reason` is
        reported through `report_refusal` (FQ-023 -- a gesture that cannot run
        says why).
        """
        if not expansion:
            self.report_refusal(expansion.reason)
            return False
        if self.isReadOnly():
            # QTextCursor edits bypass setReadOnly, so this guard is what
            # actually protects the read-only DDL Explorer buffer (§18.1).
            self.report_refusal("this buffer is read-only")
            return False

        self.exit_tab_stop_mode()
        cursor = self.textCursor()
        cursor.beginEditBlock()
        cursor.setPosition(expansion.start)
        cursor.setPosition(expansion.end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(expansion.text)
        cursor.endEditBlock()

        walkable = [stop for stop in expansion.stops if not stop.is_final]
        if walkable:
            self._enter_tab_stop_mode(expansion.stops)
        else:
            cursor.setPosition(expansion.caret)
            self.setTextCursor(cursor)
        self.ensureCursorVisible()
        return True

    # --- The two gestures that feed it -------------------------------------

    def word_before_caret(self) -> tuple[str, int]:
        """The identifier-shaped word ending at the caret, and where it starts.

        `("", pos)` when the character before the caret is not part of a word.
        """
        cursor = self.textCursor()
        pos = cursor.position()
        text = self.toPlainText()
        start = pos
        while start > 0 and (text[start - 1].isalnum() or text[start - 1] == "_"):
            start -= 1
        return text[start:pos], start

    def snippet_expansion_at_caret(self) -> Expansion:
        """The `Expansion` the word before the caret triggers -- pure, unapplied.

        Falsy with a `reason` when that word names no snippet, which is the
        normal answer for almost every word.
        """
        word, start = self.word_before_caret()
        if not word:
            return Expansion(reason="there is no word before the caret to expand")
        snippet = find_snippet(word, self._snippets)
        if snippet is None:
            return Expansion(reason=f"'{word}' is not a snippet")
        return expand_template(
            snippet.template, at=start, end=start + len(word)
        )

    def expand_snippet_at_caret(self) -> bool:
        """Ctrl+Alt+E: expand the word before the caret into its snippet."""
        return self.apply_expansion(self.snippet_expansion_at_caret())

    def expand_select_at_caret(self) -> bool:
        """Ctrl+Alt+C: expand the bare `SELECT` at the caret into its columns.

        The schema-dynamic flavor of the very same mechanism: the wired
        `set_dynamic_expander` seam turns the buffer and the caret into an
        `Expansion`, and `apply_expansion` applies it. Nothing about the
        expansion's application differs from a snippet's.
        """
        expander = self._dynamic_expander
        if expander is None:
            self.report_refusal(
                "expanding a SELECT needs a database schema, and this editor "
                "has none"
            )
            return False
        expansion = expander(self.toPlainText(), self.textCursor().position())
        if expansion is None:
            self.report_refusal("there is nothing to expand at the caret")
            return False
        return self.apply_expansion(expansion)

    def report_refusal(self, reason: str) -> None:
        """State why a gesture could not run (FQ-023), never nothing.

        Two channels, and both still earn their place now that a host DOES
        connect the signal (`MainWindow._report_editor_gesture_refusal` files
        it as an Audit `[SQL]` row, since the status bar is static since
        FQ-028): the signal is the durable record, readable after the fact and
        reachable by a test; the caret tooltip is the immediate one, at the
        place the author is looking, for a refusal that answers a keystroke
        they just pressed. A dock row alone would make a Ctrl+Alt+E that
        matched no snippet look like nothing happened; a tooltip alone would
        vanish before it could be re-read. The hosts that connect nothing (Raw
        XML, the PHP tabs) still get the tooltip.
        """
        self.show_hint(reason or "this gesture cannot run here", refusal=True)

    def show_hint(self, text: str, *, refusal: bool = False) -> None:
        """Show `text` as a transient tooltip at the caret -- the ONE hint path.

        Signature help (FQ-030 slice 3) is a query, not an insertion: it has
        nothing to put in the buffer and everything to say, so it says it here,
        through the same channel a refusal uses. `refusal=True` additionally
        emits `expansion_refused`, which is what makes a REFUSAL (and only a
        refusal) reach the Audit surface -- an answered question is not a
        notice and does not belong in a journal.
        """
        if not text:
            return
        if refusal:
            self.expansion_refused.emit(text)
        if self.isVisible():
            # A tooltip anchored to a hidden widget has nowhere to appear, and
            # asking for one under the offscreen platform only produces a Qt
            # warning. `hint_shown` below is the channel that always fires, and
            # is what tests assert on.
            QToolTip.showText(
                self.viewport().mapToGlobal(self.cursorRect().bottomLeft()),
                text,
                self,
            )
        self.hint_shown.emit(text)

    # --- Tab-stop mode ------------------------------------------------------

    @property
    def in_tab_stop_mode(self) -> bool:
        """Whether Tab/Shift+Tab currently walk an expansion's stops.

        False everywhere except between an expansion with a walkable stop and
        its exit, which is what keeps Tab byte-for-byte unchanged in Raw XML,
        the PHP tabs and every editor that has not just expanded something.
        """
        return bool(self._tab_stop_cursors)

    def tab_stop_spans(self) -> list[tuple[int, int]]:
        """The live `(start, end)` of each remaining stop, in tab order.

        Live because the stops are tracked as `QTextCursor`s (the
        `_auto_closed_cursors` idiom): typing over a placeholder moves every
        later stop with it, so no offset arithmetic is ever repeated.
        """
        return [
            (cursor.selectionStart(), cursor.selectionEnd())
            for cursor in self._tab_stop_cursors
        ]

    @property
    def tab_stop_index(self) -> int:
        """Which stop the caret is on, or -1 outside tab-stop mode."""
        return self._tab_stop_index if self.in_tab_stop_mode else -1

    def next_tab_stop(self) -> bool:
        """Tab: move to the next stop. Walking past the last one EXITS.

        Returns whether the key was consumed -- True for both the move and the
        exiting step, so the Tab that leaves the last stop does not also insert
        a tab character.
        """
        if not self.in_tab_stop_mode:
            return False
        if self._tab_stop_index + 1 >= len(self._tab_stop_cursors):
            last = self._tab_stop_cursors[-1]
            end = last.selectionEnd()
            self.exit_tab_stop_mode()
            cursor = self.textCursor()
            cursor.setPosition(end)
            self.setTextCursor(cursor)
            return True
        self._tab_stop_index += 1
        self._select_current_tab_stop()
        return True

    def previous_tab_stop(self) -> bool:
        """Shift+Tab: move to the previous stop. At the first one, stays put
        (leaving backwards would drop the user out of a template they are
        still filling in)."""
        if not self.in_tab_stop_mode:
            return False
        if self._tab_stop_index > 0:
            self._tab_stop_index -= 1
        self._select_current_tab_stop()
        return True

    def exit_tab_stop_mode(self) -> None:
        """Leave tab-stop mode: Tab is a tab again. Idempotent."""
        self._tab_stop_cursors = []
        self._tab_stop_index = 0

    def _enter_tab_stop_mode(self, stops) -> None:
        cursors: list[QTextCursor] = []
        for stop in stops:
            tracked = QTextCursor(self.document())
            tracked.setPosition(stop.start)
            if stop.end > stop.start:
                tracked.setPosition(stop.end, QTextCursor.MoveMode.KeepAnchor)
            cursors.append(tracked)
        self._tab_stop_cursors = cursors
        self._tab_stop_index = 0
        self._select_current_tab_stop()

    def _select_current_tab_stop(self) -> None:
        tracked = self._tab_stop_cursors[self._tab_stop_index]
        cursor = self.textCursor()
        cursor.setPosition(tracked.selectionStart())
        end = tracked.selectionEnd()
        if end > tracked.selectionStart():
            # Select the placeholder so the next character typed replaces it.
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def mousePressEvent(self, event) -> None:
        """A click anywhere leaves tab-stop mode -- the "clicking away" exit.

        Any click, not only one outside the template: once the user navigates
        by mouse there is no longer a walk in progress to resume, and a Tab
        that silently jumped somewhere else would be worse than a tab.
        """
        self.exit_tab_stop_mode()
        super().mousePressEvent(event)

    def focusOutEvent(self, event) -> None:
        self.exit_tab_stop_mode()
        super().focusOutEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        # NOTE (BUG-046, owner ruling 2026-08-10): Ctrl+Shift+B is NOT handled
        # here. It is `Select ▸ Select Enclosing Block`'s QAction on every tab,
        # and `CodeEditorDialog`'s own QShortcut in the menu-less dialog.
        # `select_enclosing_brackets` is purely a slot. The duplicate branch
        # that used to live here was justified by "QShortcut activation is not
        # guaranteed under the offscreen platform", which is measurably FALSE:
        # shortcuts do activate offscreen; what fails is key delivery to a
        # widget that was never `show()`n (no `windowHandle()`, so QTest posts
        # the event straight at the widget and the shortcut map is bypassed).
        # A design that exists to satisfy the test harness rather than the
        # product means the harness is what should change.

        # --- Template expansion (FQ-030) -----------------------------------
        #
        # Tab and Shift+Tab are taken ONLY while a walk is in progress. Outside
        # tab-stop mode this branch is skipped entirely, so Tab keeps inserting
        # a tab character in every editor exactly as it did before -- the PHP
        # tabs, the Raw XML code dialogs, the console, an untouched DDL object
        # tab. (The completion popup's own Tab-chooses-the-current-item is a
        # different widget's key handler and is not affected either.)
        key = event.key()
        if self.in_tab_stop_mode:
            if key == Qt.Key.Key_Tab and event.modifiers() == Qt.KeyboardModifier.NoModifier:
                if self.next_tab_stop():
                    return
            elif key == Qt.Key.Key_Backtab or (
                key == Qt.Key.Key_Tab
                and event.modifiers() == Qt.KeyboardModifier.ShiftModifier
            ):
                if self.previous_tab_stop():
                    return
            elif key == Qt.Key.Key_Escape:
                # Consumed only in tab-stop mode; Escape keeps its §27 meaning
                # ("returns focus to the document") everywhere else.
                self.exit_tab_stop_mode()
                return

        # The two expansion gestures, in the `Ctrl+Alt+` editor-gesture family
        # Format Selection (`Ctrl+Alt+F`) established. Handled in the widget
        # rather than as QShortcuts because the whole family has NO menu
        # command: these are widget *behaviours* (like auto-close brackets),
        # not commands, so the widget is their one legitimate host. DEC-009
        # decided this deliberately -- the defect DEC-004 ruled against was
        # *two hosts for one gesture*, not *a widget answers a key*, and a
        # gesture with no menu entry cannot have two hosts. They also depend on
        # caret state and on `self._language`, which a window-level shortcut
        # would have to reach back into the focused widget to discover.
        # SQL only -- the snippet set is plpgsql,
        # and a `Ctrl+Alt+E` that expanded plpgsql into a PHP body would be a
        # bug, so in js/php these keys stay untouched.
        if self._language == "sql" and event.modifiers() == (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
        ):
            if key == Qt.Key.Key_E:
                self.expand_snippet_at_caret()
                return
            if key == Qt.Key.Key_C:
                self.expand_select_at_caret()
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

        # NO `Ctrl+S` / `Ctrl+W` (owner decision, 2026-08-09). This dialog was
        # the last carve-out for either chord: `Ctrl+S` had been dead app-wide
        # since FQ-020 moved saving onto `Deployment`, and `Ctrl+W` lost its
        # `File ▸ Close` binding the same day. The owner chose total
        # consistency -- neither chord does anything anywhere in the app --
        # over the local convention that OK/Cancel in a text-editing modal are
        # naturally those two keys.
        #
        # OK and Cancel remain reachable by the button box, by `Return`/`Escape`
        # (Qt's own defaults for a QDialogButtonBox), and by the window's close
        # button, so nothing became unreachable.
        #
        # ONE key this dialog does own: `Ctrl+Shift+B` (bracket-select). It is
        # `Select ▸ Select Enclosing Block` everywhere else, and this dialog has
        # no menu bar to host that action, so the dialog hosts the chord itself
        # (BUG-046). `WindowShortcut` — the dialog IS the window; never
        # `ApplicationShortcut`, which would fight the MainWindow action. The
        # reference is kept on `self` deliberately: a QShortcut whose only
        # Python reference is dropped is garbage collected and stops working.
        #
        # Known limitation, deliberate: this is a literal `Ctrl+Shift+B` and
        # does NOT follow a user rebinding of `Select ▸ Select Enclosing Block`
        # (`MainWindow._apply_shortcut_bindings` only walks menu QActions).
        # Making it follow means passing the resolved sequence in at both
        # construction sites (`main_window._open_code_editor_dialog` and
        # `activity_panel.open_viewer`, which has no MainWindow to ask).
        self._select_enclosing_shortcut = QShortcut(QKeySequence("Ctrl+Shift+B"), self)
        self._select_enclosing_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._select_enclosing_shortcut.activated.connect(
            self._editor.select_enclosing_brackets
        )

        # The reserved undo/redo chord set, stated here too (DEC-014's fixed
        # set: *every* editing surface states its answer, and this dialog hosts
        # a full CodeEditor). Nothing can steal these keys from a modal -- no
        # window `QShortcut` reaches it -- so `Ctrl+Z`/`Ctrl+Y` would have worked
        # natively on Windows and `Ctrl+Y` would have been dead on Linux, which
        # is exactly the divergence BUG-056 measured in the Sandbox SQL Console.
        # DEC-014 accepted the uniformity cost here knowingly; the part that is
        # NOT cosmetic is `Ctrl+Shift+Z`, which Qt answers with a native redo on
        # both schemes and which DEC-015 freed from redo.
        self._editor.installEventFilter(self)

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

    def eventFilter(self, obj, event) -> bool:
        """The dialog's stated answer to the reserved undo/redo chords.

        Same two halves as every other surface (claim the `ShortcutOverride`,
        answer the `KeyPress`), routed into this editor's own native stack --
        the dialog holds no snapshot history.
        """
        if obj is self._editor and event.type() in (
            QEvent.Type.ShortcutOverride,
            QEvent.Type.KeyPress,
        ):
            operation = classify_undo_redo_chord(event)
            if operation is not None:
                if event.type() == QEvent.Type.ShortcutOverride:
                    event.accept()
                elif operation == UNDO:
                    self._editor.undo()
                elif operation == REDO:
                    self._editor.redo()
                # else: the two answers that run nothing -- Ctrl+Shift+Z
                # (DEC-015) and the suppressed Alt+Backspace pair. Consumed so
                # Qt's own platform-conditional handling cannot answer instead.
                return True
        return super().eventFilter(obj, event)

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
