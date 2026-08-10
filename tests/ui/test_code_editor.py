from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit

from pgtp_editor.ui.code_editor import (
    CodeEditor,
    CodeEditorDialog,
    _CodeHighlighter,
    _JS_KEYWORDS,
    _PHP_KEYWORDS,
    _SQL_KEYWORDS,
    enclosing_bracket_span,
)


# ---------------------------------------------------------------------------
# Pure: enclosing_bracket_span (inner-exclusive span: [start, end) of the
# characters strictly between the matching brackets).
# ---------------------------------------------------------------------------

def test_enclosing_bracket_span_inner_pair():
    # a(b[c]d)e : positions - '(' at 1, ')' at 7; '[' at 3, ']' at 5.
    text = "a(b[c]d)e"
    # Cursor inside the inner [] pair (on 'c', index 4).
    assert enclosing_bracket_span(text, 4) == (4, 5)


def test_enclosing_bracket_span_outer_pair():
    text = "a(b[c]d)e"
    # Cursor in the outer () but outside [] (on 'b', index 2).
    assert enclosing_bracket_span(text, 2) == (2, 7)


def test_enclosing_bracket_span_cursor_outside_returns_none():
    text = "a(b[c]d)e"
    # Cursor at the very start, outside every bracket pair.
    assert enclosing_bracket_span(text, 0) is None
    # Cursor after everything.
    assert enclosing_bracket_span(text, len(text)) is None


def test_enclosing_bracket_span_unbalanced_returns_none():
    assert enclosing_bracket_span("a(b c", 3) is None
    assert enclosing_bracket_span("a)b c", 3) is None


def test_enclosing_bracket_span_mixed_types_do_not_match():
    # An opener '(' should not be closed by ']'.
    assert enclosing_bracket_span("(a]", 1) is None


# ---------------------------------------------------------------------------
# Pure-ish: keyword constants exist and are non-trivial.
# ---------------------------------------------------------------------------

def test_keyword_lists_exist_and_are_nontrivial():
    assert len(_JS_KEYWORDS) > 5
    assert len(_PHP_KEYWORDS) > 5
    assert "function" in _JS_KEYWORDS
    assert "function" in _PHP_KEYWORDS


def test_sql_keyword_list_exists_and_is_nontrivial():
    assert len(_SQL_KEYWORDS) > 20
    for kw in ("select", "insert", "update", "delete", "trigger", "function",
               "begin", "end", "returns", "language"):
        assert kw in _SQL_KEYWORDS, kw
    # Stored lowercase by contract (matching lowercases the candidate word).
    assert all(kw == kw.lower() for kw in _SQL_KEYWORDS)


def test_sql_keywords_are_the_shared_dialect_source_from_the_sql_package():
    """§18.4: the highlighter and the formatter must never disagree.

    `_SQL_KEYWORDS` now only re-binds `pgtp_editor.sql.keywords.SQL_KEYWORDS`;
    a copy here (or a second literal set) would let the two drift apart.
    """
    from pgtp_editor.sql.keywords import SQL_KEYWORDS

    assert _SQL_KEYWORDS is SQL_KEYWORDS


def test_the_formatter_sees_the_same_keywords_the_highlighter_highlights():
    from pgtp_editor.sql.tokenizer import tokenize

    for word in ("select", "BEGIN", "End", "if", "loop", "case", "when", "declare"):
        assert word.lower() in _SQL_KEYWORDS, word
        assert tokenize(word)[0].is_keyword, word
    for word in ("my_table", "ügyfél", "v_count"):
        assert word.lower() not in _SQL_KEYWORDS, word
        assert not tokenize(word)[0].is_keyword, word


# ---------------------------------------------------------------------------
# Widget: CodeEditor construction.
# ---------------------------------------------------------------------------

def test_code_editor_is_plain_text_edit(qtbot):
    editor = CodeEditor("js")
    qtbot.addWidget(editor)
    assert isinstance(editor, QPlainTextEdit)


def test_code_editor_uses_monospace_font(qtbot):
    editor = CodeEditor("js")
    qtbot.addWidget(editor)
    assert editor.font().fixedPitch() or editor.font().styleHint() != 0


def _type(qtbot, editor, ch):
    qtbot.keyClick(editor, ch)


def test_typing_opener_auto_closes_with_caret_between(qtbot):
    editor = CodeEditor("js")
    qtbot.addWidget(editor)
    editor.setFocus()
    qtbot.keyClicks(editor, "(")
    assert editor.toPlainText() == "()"
    assert editor.textCursor().position() == 1


def test_typing_all_openers_auto_close(qtbot):
    for opener, expected in [("(", "()"), ("[", "[]"), ("{", "{}"), ("'", "''"), ('"', '""')]:
        editor = CodeEditor("js")
        qtbot.addWidget(editor)
        editor.setFocus()
        qtbot.keyClicks(editor, opener)
        assert editor.toPlainText() == expected, opener


def test_typing_closer_before_same_closer_types_through(qtbot):
    editor = CodeEditor("js")
    qtbot.addWidget(editor)
    editor.setFocus()
    qtbot.keyClicks(editor, "(")  # -> "()" caret between
    assert editor.toPlainText() == "()"
    qtbot.keyClicks(editor, ")")  # type through, no double
    assert editor.toPlainText() == "()"
    assert editor.textCursor().position() == 2


def test_selection_wrap_with_paren_keeps_selection(qtbot):
    editor = CodeEditor("js")
    qtbot.addWidget(editor)
    editor.setPlainText("foo")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(3, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    editor.setFocus()
    qtbot.keyClicks(editor, "(")
    assert editor.toPlainText() == "(foo)"
    assert editor.textCursor().selectedText() == "foo"


def test_selection_wrap_with_quote(qtbot):
    editor = CodeEditor("js")
    qtbot.addWidget(editor)
    editor.setPlainText("foo")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(3, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    editor.setFocus()
    qtbot.keyClicks(editor, '"')
    assert editor.toPlainText() == '"foo"'
    assert editor.textCursor().selectedText() == "foo"


def test_ctrl_shift_b_selects_bracket_span_caret_at_start(qtbot):
    editor = CodeEditor("js")
    qtbot.addWidget(editor)
    editor.setPlainText("a(bcd)e")
    cursor = editor.textCursor()
    cursor.setPosition(3)  # inside the () pair
    editor.setTextCursor(cursor)
    editor.setFocus()
    qtbot.keyClick(editor, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    c = editor.textCursor()
    assert c.selectedText() == "bcd"
    assert c.position() == c.selectionStart()  # caret at start


def test_cut_copy_paste_round_trips(qtbot):
    editor = CodeEditor("js")
    qtbot.addWidget(editor)
    editor.setPlainText("hello")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    editor.copy()
    cursor.setPosition(5)
    editor.setTextCursor(cursor)
    editor.paste()
    assert editor.toPlainText() == "hellohello"
    # cut
    cursor.setPosition(0)
    cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    editor.cut()
    assert editor.toPlainText() == "hello"


def _format_at(editor, position):
    block = editor.document().findBlock(position)
    layout = block.layout()
    offset_in_block = position - block.position()
    for fmt_range in layout.formats():
        if fmt_range.start <= offset_in_block < fmt_range.start + fmt_range.length:
            return QTextCharFormat(fmt_range.format)
    return QTextCharFormat()


def test_highlighter_applies_format_to_keyword(qtbot):
    editor = CodeEditor("js")
    qtbot.addWidget(editor)
    assert isinstance(editor._highlighter, _CodeHighlighter)
    text = "function foo() {}"
    editor.setPlainText(text)
    kw_format = _format_at(editor, text.index("function"))
    plain_format = _format_at(editor, text.index("foo"))
    assert kw_format.foreground().color() != plain_format.foreground().color()


def test_highlighter_php_variable_gets_format(qtbot):
    editor = CodeEditor("php")
    qtbot.addWidget(editor)
    text = "$var = 1;"
    editor.setPlainText(text)
    var_format = _format_at(editor, text.index("$var"))
    assert var_format.foreground().color().isValid()


# ---------------------------------------------------------------------------
# Widget: SQL language mode (spec §18.1 -- the DDL Explorer buffer).
# ---------------------------------------------------------------------------

def _sql_editor(qtbot, text):
    editor = CodeEditor("sql")
    qtbot.addWidget(editor)
    editor.setPlainText(text)
    return editor


def test_sql_highlighter_selected_for_sql_language(qtbot):
    editor = CodeEditor("sql")
    qtbot.addWidget(editor)
    assert editor._highlighter._keywords is _SQL_KEYWORDS


def test_sql_keyword_matching_is_case_insensitive(qtbot):
    # pg_get_functiondef emits uppercase; hand-written bodies vary.
    text = "SELECT id FROM t WHERE Select_col = 1; select 2;"
    editor = _sql_editor(qtbot, text)
    kw_color = editor._highlighter._keyword_format.foreground().color()
    assert _format_at(editor, text.index("SELECT")).foreground().color() == kw_color
    assert _format_at(editor, text.index("select 2")).foreground().color() == kw_color
    # A plain identifier is not keyword-colored.
    assert _format_at(editor, text.index("id")).foreground().color() != kw_color


def test_sql_uppercase_keyword_not_highlighted_in_js_mode(qtbot):
    # Case-insensitivity is SQL-specific: JS keeps exact-case matching.
    text = "RETURN x; return x;"
    editor = CodeEditor("js")
    qtbot.addWidget(editor)
    editor.setPlainText(text)
    kw_color = editor._highlighter._keyword_format.foreground().color()
    assert _format_at(editor, 0).foreground().color() != kw_color  # RETURN
    assert _format_at(editor, text.index("return")).foreground().color() == kw_color


def test_sql_double_dash_line_comment(qtbot):
    text = "SELECT 1; -- FUNCTION pr.calc_total(integer) --"
    editor = _sql_editor(qtbot, text)
    comment_color = editor._highlighter._comment_format.foreground().color()
    dash = text.index("--")
    # Everything from '--' to end-of-line is comment-formatted, keywords included.
    for pos in (dash, text.index("FUNCTION"), len(text) - 1):
        assert _format_at(editor, pos).foreground().color() == comment_color, pos
    assert _format_at(editor, 0).foreground().color() != comment_color


def test_sql_double_dash_is_not_a_comment_in_js_or_php(qtbot):
    for language in ("js", "php"):
        editor = CodeEditor(language)
        qtbot.addWidget(editor)
        text = "x -- y"
        editor.setPlainText(text)
        comment_color = editor._highlighter._comment_format.foreground().color()
        assert _format_at(editor, text.index("--")).foreground().color() != comment_color


def test_sql_string_with_doubled_quote_is_one_string(qtbot):
    text = "SELECT 'it''s' AS v"
    editor = _sql_editor(qtbot, text)
    string_color = editor._highlighter._string_format.foreground().color()
    # The doubled '' does NOT terminate the string: 's' after it is inside.
    assert _format_at(editor, text.index("it")).foreground().color() == string_color
    assert _format_at(editor, text.index("''s") + 2).foreground().color() == string_color
    # AS, after the closing quote, is back to keyword-land, not string.
    assert _format_at(editor, text.index("AS")).foreground().color() != string_color


def test_sql_backslash_does_not_escape_quote(qtbot):
    # SQL has no backslash escapes: '\' closes at the second quote.
    text = r"SELECT 'a\' , x"
    editor = _sql_editor(qtbot, text)
    string_color = editor._highlighter._string_format.foreground().color()
    assert _format_at(editor, text.index("a")).foreground().color() == string_color
    # x is OUTSIDE the string (in js the \' would keep the string open).
    assert _format_at(editor, text.index("x")).foreground().color() != string_color


def test_sql_double_quoted_identifier_is_not_string_styled(qtbot):
    # Double quotes delimit identifiers in SQL, not strings -- the string
    # format must not apply to them (in js the same text WOULD be a string).
    text = 'SELECT "MyColumn" FROM t'
    editor = _sql_editor(qtbot, text)
    string_color = editor._highlighter._string_format.foreground().color()
    quoted = _format_at(editor, text.index("MyColumn")).foreground().color()
    assert quoted != string_color


def test_sql_block_comment_still_works(qtbot):
    text = "SELECT /* FROM */ 1"
    editor = _sql_editor(qtbot, text)
    comment_color = editor._highlighter._comment_format.foreground().color()
    assert _format_at(editor, text.index("FROM")).foreground().color() == comment_color
    assert _format_at(editor, 0).foreground().color() != comment_color


# ---------------------------------------------------------------------------
# Widget: navigate_to_line / replace_current_selection (§18.1 additions).
# ---------------------------------------------------------------------------

def test_navigate_to_line_moves_caret_to_one_based_line(qtbot):
    editor = _sql_editor(qtbot, "line one\nline two\nline three\nline four")
    editor.navigate_to_line(3)
    assert editor.textCursor().blockNumber() == 2  # 0-based block for line 3
    assert editor.textCursor().block().text() == "line three"


def test_navigate_to_line_clamps_below_one_to_first_line(qtbot):
    editor = _sql_editor(qtbot, "first\nsecond")
    editor.navigate_to_line(0)
    assert editor.textCursor().blockNumber() == 0


def test_replace_current_selection_replaces_when_editable(qtbot):
    editor = _sql_editor(qtbot, "hello world")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    editor.replace_current_selection("goodbye")
    assert editor.toPlainText() == "goodbye world"


def test_replace_current_selection_no_selection_is_noop(qtbot):
    editor = _sql_editor(qtbot, "hello world")
    editor.replace_current_selection("goodbye")
    assert editor.toPlainText() == "hello world"


def test_replace_current_selection_read_only_guard(qtbot):
    # QTextCursor edits bypass setReadOnly -- the explicit guard is what
    # protects the read-only DDL buffer (§18.1).
    editor = _sql_editor(qtbot, "hello world")
    editor.setReadOnly(True)
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    editor.replace_current_selection("goodbye")
    assert editor.toPlainText() == "hello world"


# ---------------------------------------------------------------------------
# Widget: CodeEditorDialog.
# ---------------------------------------------------------------------------

def test_dialog_set_code_and_code_round_trip(qtbot):
    dialog = CodeEditorDialog(language="js")
    qtbot.addWidget(dialog)
    dialog.set_code("var x = 1;")
    assert dialog.code() == "var x = 1;"


def test_dialog_title_shows_handler_name_and_language(qtbot):
    dialog = CodeEditorDialog(language="php", handler_name="OnPreparePage")
    qtbot.addWidget(dialog)
    assert "OnPreparePage" in dialog.windowTitle()
    assert "php" in dialog.windowTitle().lower()


def test_dialog_save_emits_saved_with_code(qtbot):
    dialog = CodeEditorDialog(language="js")
    qtbot.addWidget(dialog)
    dialog.set_code("code here")
    with qtbot.waitSignal(dialog.saved, timeout=1000) as blocker:
        dialog.save()
    assert blocker.args == ["code here"]


def test_dialog_cancel_emits_cancelled(qtbot):
    dialog = CodeEditorDialog(language="js")
    qtbot.addWidget(dialog)
    with qtbot.waitSignal(dialog.cancelled, timeout=1000):
        dialog.cancel()


def test_the_dialog_has_no_ctrl_s_or_ctrl_w(qtbot):
    """The inverse of what this file asserted until 2026-08-09.

    `Ctrl+S` had been dead app-wide since FQ-020 moved saving onto the
    `Deployment` menu, and this modal was its ONE surviving carve-out (its
    `Ctrl+S` was the OK button, emitting `saved` and writing nothing to disk,
    paired with `Ctrl+W` = Cancel). The owner unbound `Ctrl+O` and then
    `Ctrl+W` from the File menu and chose to take these two as well, for total
    consistency: neither chord now does anything anywhere in the app.

    Asserted at BOTH former hosts, because it was implemented twice on purpose
    -- a `QShortcut` and a `keyPressEvent` branch, since QShortcut activation is
    unreliable under the offscreen platform -- and a sweep that removed only one
    would leave the key working in the real app while the test suite passed.
    """
    from PySide6.QtGui import QShortcut

    dialog = CodeEditorDialog(language="js")
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)

    bound = {s.key().toString() for s in dialog.findChildren(QShortcut)}
    assert "Ctrl+S" not in bound
    assert "Ctrl+W" not in bound

    dialog.set_code("abc")
    dialog._editor.setFocus()
    fired = []
    dialog.saved.connect(lambda text: fired.append(("saved", text)))
    dialog.cancelled.connect(lambda: fired.append(("cancelled", None)))
    qtbot.keyClick(dialog, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    qtbot.keyClick(dialog, Qt.Key.Key_W, Qt.KeyboardModifier.ControlModifier)
    assert fired == []


def test_the_dialogs_ok_and_cancel_are_still_reachable(qtbot):
    """The point of the check above is that the KEYS are gone, not the
    gestures. Nothing became unreachable: the button box still works, and so do
    Qt's own `Return`/`Escape` defaults for it."""
    dialog = CodeEditorDialog(language="js")
    qtbot.addWidget(dialog)
    dialog.set_code("abc")
    with qtbot.waitSignal(dialog.saved, timeout=1000) as blocker:
        dialog.save()
    assert blocker.args == ["abc"]

    other = CodeEditorDialog(language="js")
    qtbot.addWidget(other)
    with qtbot.waitSignal(other.cancelled, timeout=1000):
        other.cancel()


def test_dialog_opens_at_80_percent_of_parent_window(qtbot):
    from PySide6.QtWidgets import QMainWindow

    host = QMainWindow()
    qtbot.addWidget(host)
    host.resize(1000, 800)
    dialog = CodeEditorDialog(language="php", handler_name="OnX", parent=host)
    qtbot.addWidget(dialog)
    # 80% of the host window, within rounding.
    assert abs(dialog.width() - 800) <= 2
    assert abs(dialog.height() - 640) <= 2


def test_dialog_without_parent_uses_minimum_size(qtbot):
    dialog = CodeEditorDialog(language="js", handler_name="OnY")
    qtbot.addWidget(dialog)
    # No parent to size against: at least the usable minimum.
    assert dialog.minimumWidth() == 480
    assert dialog.minimumHeight() == 320


# --- Shared gutter / bookmark / fold base (spec §8, §18.1) -----------------


def test_code_editor_and_xml_editor_share_one_gutter_implementation(qtbot):
    """The hard requirement from §8: exactly ONE gutter/bookmark/fold
    implementation, carried by both editors -- never a second parallel gutter."""
    from pgtp_editor.ui.editor_gutter import _EditorGutter, GutterBookmarkFoldMixin
    from pgtp_editor.ui.xml_editor import XmlEditor

    code = CodeEditor(language="sql")
    qtbot.addWidget(code)
    xml = XmlEditor()
    qtbot.addWidget(xml)

    assert isinstance(code, GutterBookmarkFoldMixin)
    assert isinstance(xml, GutterBookmarkFoldMixin)
    assert type(code._gutter) is _EditorGutter
    assert type(xml._gutter) is _EditorGutter
    # Same functions, not copies.
    assert type(code).toggle_bookmark is type(xml).toggle_bookmark
    # CodeEditor uses the mixin's fold implementation verbatim. XmlEditor wraps
    # it (BUG-015: flush the debounced structure rescan so folding never acts
    # on stale spans) but must DELEGATE to that same one implementation via
    # super() -- a thin wrapper is fine, a re-implementation is not.
    import inspect

    assert type(code)._toggle_fold is GutterBookmarkFoldMixin._toggle_fold
    assert "super()._toggle_fold(block)" in inspect.getsource(type(xml)._toggle_fold)


def test_code_editor_has_a_gutter_reserving_viewport_margin(qtbot):
    editor = CodeEditor(language="sql")
    qtbot.addWidget(editor)
    editor.setPlainText("\n".join(f"line {i}" for i in range(200)))
    assert editor._gutter_width() > 0
    assert editor.viewportMargins().left() == editor._gutter_width()


def test_code_editor_bookmarks_toggle_and_cycle(qtbot):
    editor = CodeEditor(language="sql")
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb\nc\nd\n")
    editor.toggle_bookmark(1)
    editor.toggle_bookmark(3)
    assert editor.bookmarked_lines() == [1, 3]
    assert editor.next_bookmark(1) == 3
    assert editor.next_bookmark(3) == 1  # wraps
    assert editor.prev_bookmark(1) == 3  # wraps
    editor.toggle_bookmark(1)
    assert editor.bookmarked_lines() == [3]
    editor.clear_bookmarks()
    assert editor.bookmarked_lines() == []


def test_code_editor_setplaintext_resets_bookmarks_and_folds(qtbot):
    editor = CodeEditor(language="sql")
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb\nc\n")
    editor.toggle_bookmark(1)
    editor.set_fold_regions([(0, 1, 2)])
    editor._toggle_fold(editor.document().findBlockByNumber(0))
    assert editor._fold_state == {0: True}
    editor.setPlainText("x\ny\n")
    assert editor.bookmarked_lines() == []
    assert editor._fold_state == {}


def test_code_editor_folds_only_the_regions_it_was_given(qtbot):
    editor = CodeEditor(language="sql")
    qtbot.addWidget(editor)
    editor.setPlainText("head\nbody1\nbody2\ntail\n")
    document = editor.document()
    # Nothing foldable until regions are installed.
    assert editor._foldable_region_starting_at(document.findBlockByNumber(0)) is None
    editor.set_fold_regions([(0, 1, 2)])
    assert editor._foldable_region_starting_at(document.findBlockByNumber(0)) == (1, 2)
    assert editor._foldable_region_starting_at(document.findBlockByNumber(1)) is None

    editor._toggle_fold(document.findBlockByNumber(0))
    assert document.findBlockByNumber(0).isVisible() is True  # trigger line stays
    assert document.findBlockByNumber(1).isVisible() is False
    assert document.findBlockByNumber(2).isVisible() is False
    assert document.findBlockByNumber(3).isVisible() is True
    # Folding only hides rendering: the character stream is intact.
    assert editor.toPlainText() == "head\nbody1\nbody2\ntail\n"

    editor._toggle_fold(document.findBlockByNumber(0))
    assert document.findBlockByNumber(1).isVisible() is True


def test_js_code_editor_has_the_gutter_but_nothing_foldable(qtbot):
    editor = CodeEditor(language="js")
    qtbot.addWidget(editor)
    editor.setPlainText("function f() {\n  return 1;\n}\n")
    assert editor._gutter is not None
    assert editor._foldable_region_starting_at(editor.document().findBlockByNumber(0)) is None


# --- Tab stop (§18.1) ------------------------------------------------------


def test_sql_mode_uses_a_four_character_tab_stop(qtbot):
    editor = CodeEditor(language="sql")
    qtbot.addWidget(editor)
    expected = 4 * editor.fontMetrics().horizontalAdvance(" ")
    assert editor.tabStopDistance() == expected


def test_non_sql_modes_keep_qt_default_tab_stop(qtbot):
    """Scoped to the DDL/sql mode: JS/PHP event bodies are untouched."""
    sql = CodeEditor(language="sql")
    qtbot.addWidget(sql)
    js = CodeEditor(language="js")
    qtbot.addWidget(js)
    assert js.tabStopDistance() != sql.tabStopDistance()


# --- Top-aligned vs centered navigation (§18.1) ----------------------------


def _tall_editor(qtbot, language):
    editor = CodeEditor(language=language)
    qtbot.addWidget(editor)
    editor.setPlainText("\n".join(f"line {i}" for i in range(1, 401)))
    editor.resize(400, 200)
    editor.show()
    qtbot.waitExposed(editor)
    return editor


def test_sql_navigate_to_line_puts_the_target_at_the_top(qtbot):
    editor = _tall_editor(qtbot, "sql")
    editor.navigate_to_line(100)
    assert editor.textCursor().blockNumber() == 99
    # Scrollbar counts visible blocks: the target block is the first one shown.
    assert editor.verticalScrollBar().value() == 99


def test_non_sql_navigate_to_line_stays_centered(qtbot):
    editor = _tall_editor(qtbot, "js")
    editor.navigate_to_line(100)
    assert editor.textCursor().blockNumber() == 99
    # Centered: the target sits roughly mid-viewport, so the first visible
    # block is well ABOVE it.
    assert editor.verticalScrollBar().value() < 99


def test_xml_editor_navigate_to_line_stays_centered(qtbot):
    """XmlEditor's Properties/tree-jump callers depend on centering (§18.1)."""
    from pgtp_editor.ui.xml_editor import XmlEditor

    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("\n".join(f"<T{i}/>" for i in range(1, 401)))
    editor.resize(400, 200)
    editor.show()
    qtbot.waitExposed(editor)
    editor.navigate_to_line(100)
    assert editor.textCursor().blockNumber() == 99
    assert editor.verticalScrollBar().value() < 99


def test_sql_navigate_near_end_of_document_clamps_instead_of_failing(qtbot):
    editor = _tall_editor(qtbot, "sql")
    editor.navigate_to_line(400)
    bar = editor.verticalScrollBar()
    assert bar.value() == bar.maximum()
    assert editor.textCursor().blockNumber() == 399


# --- The shared gutter's mouse zones, on a CodeEditor host (§8) ------------

from PySide6.QtCore import QEvent as _QEvent_g, QPoint as _QPoint_g  # noqa: E402
from PySide6.QtGui import QMouseEvent as _QMouseEvent_g  # noqa: E402

from pgtp_editor.ui.editor_gutter import (  # noqa: E402
    _BOOKMARK_STRIP_WIDTH as _STRIP_W,
    _FOLD_GLYPH_WIDTH as _FOLD_W,
)


def _gutter_editor(qtbot):
    editor = CodeEditor(language="sql")
    qtbot.addWidget(editor)
    editor.resize(400, 300)
    editor.show()
    editor.setPlainText("-- BANNER --\nbody1\nbody2\ntail\n")
    editor.set_fold_regions([(0, 1, 2)])
    return editor


def _click_gutter(editor, x, block_number):
    block = editor.document().findBlockByNumber(block_number)
    top = editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top()
    event = _QMouseEvent_g(
        _QEvent_g.Type.MouseButtonPress,
        _QPoint_g(x, int(top) + 2),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    editor._gutter.mousePressEvent(event)


def test_code_editor_gutter_click_in_bookmark_strip_toggles_bookmark(qtbot):
    editor = _gutter_editor(qtbot)
    _click_gutter(editor, 2, 2)
    assert editor.bookmarked_lines() == [2]
    _click_gutter(editor, 2, 2)
    assert editor.bookmarked_lines() == []


def test_code_editor_gutter_click_in_fold_zone_toggles_fold(qtbot):
    editor = _gutter_editor(qtbot)
    _click_gutter(editor, _STRIP_W + _FOLD_W // 2, 0)
    assert editor.document().findBlockByNumber(1).isVisible() is False
    assert editor.document().findBlockByNumber(3).isVisible() is True
    assert editor.bookmarked_lines() == []


def test_code_editor_gutter_click_on_line_number_is_a_no_op(qtbot):
    editor = _gutter_editor(qtbot)
    _click_gutter(editor, _STRIP_W + _FOLD_W + 2, 0)
    assert editor.bookmarked_lines() == []
    assert editor.document().findBlockByNumber(1).isVisible() is True


def _double_click_gutter(editor, x, block_number):
    block = editor.document().findBlockByNumber(block_number)
    top = editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top()
    event = _QMouseEvent_g(
        _QEvent_g.Type.MouseButtonDblClick,
        _QPoint_g(x, int(top) + 2),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    editor._gutter.mouseDoubleClickEvent(event)


def test_code_editor_gutter_double_click_on_line_number_toggles_bookmark(qtbot):
    """The double-click gesture lives on the ONE shared ``_EditorGutter``, so
    every mixin host carries it — not just the Raw XML editor (spec §8)."""
    editor = _gutter_editor(qtbot)
    _double_click_gutter(editor, _STRIP_W + _FOLD_W + 2, 2)
    assert editor.bookmarked_lines() == [2]
    _double_click_gutter(editor, _STRIP_W + _FOLD_W + 2, 2)
    assert editor.bookmarked_lines() == []


def test_code_editor_gutter_paints_with_bookmark_and_fold_glyph(qtbot):
    """Exercise the shared paintEvent through the CodeEditor host: bookmark
    tag + fold chevron, collapsed and expanded."""
    from PySide6.QtGui import QPixmap

    editor = _gutter_editor(qtbot)
    editor.toggle_bookmark(1)
    pixmap = QPixmap(editor._gutter.size())
    editor._gutter.render(pixmap)
    editor._toggle_fold(editor.document().findBlockByNumber(0))
    editor._gutter.render(pixmap)  # collapsed chevron path
    assert editor._fold_state == {0: True}


def test_code_editor_gutter_theme_colors_follow_the_palette(qtbot):
    from PySide6.QtGui import QColor, QPalette

    from pgtp_editor.ui.editor_gutter import (
        _GUTTER_COLORS_DARK,
        _GUTTER_COLORS_LIGHT,
    )

    editor = CodeEditor(language="sql")
    qtbot.addWidget(editor)
    palette = editor.palette()
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    editor.setPalette(palette)
    editor._apply_gutter_theme_colors(editor._palette_is_light())
    assert editor._gutter_bg_color.name() == QColor(_GUTTER_COLORS_LIGHT[0]).name()

    palette.setColor(QPalette.ColorRole.Base, QColor("#101010"))
    editor.setPalette(palette)
    editor._apply_gutter_theme_colors(editor._palette_is_light())
    assert editor._gutter_bg_color.name() == QColor(_GUTTER_COLORS_DARK[0]).name()


def test_code_editor_palette_change_event_repaints_the_gutter(qtbot):
    """changeEvent guards on the gutter existing (it can fire during base
    construction) and otherwise re-applies the theme colors."""
    from PySide6.QtGui import QColor, QPalette

    from pgtp_editor.ui.editor_gutter import _GUTTER_COLORS_LIGHT

    editor = CodeEditor(language="sql")
    qtbot.addWidget(editor)
    palette = editor.palette()
    palette.setColor(QPalette.ColorRole.Base, QColor("#fafafa"))
    editor.setPalette(palette)  # emits a PaletteChange changeEvent
    assert editor._gutter_bg_color.name() == QColor(_GUTTER_COLORS_LIGHT[0]).name()


def test_set_fold_regions_replaces_the_previous_set_and_drops_fold_state(qtbot):
    editor = CodeEditor(language="sql")
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb\nc\nd\ne\n")
    editor.set_fold_regions([(0, 1, 2)])
    editor._toggle_fold(editor.document().findBlockByNumber(0))
    assert editor._fold_state == {0: True}

    editor.set_fold_regions([(2, 3, 4)])
    assert editor._fold_state == {}
    document = editor.document()
    assert editor._foldable_region_starting_at(document.findBlockByNumber(0)) is None
    assert editor._foldable_region_starting_at(document.findBlockByNumber(2)) == (3, 4)


def test_set_fold_regions_accepts_an_empty_iterable(qtbot):
    editor = CodeEditor(language="sql")
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb\n")
    editor.set_fold_regions([(0, 1, 1)])
    editor.set_fold_regions([])
    assert editor._foldable_region_starting_at(editor.document().findBlockByNumber(0)) is None


def test_toggle_fold_on_a_non_region_block_is_a_no_op(qtbot):
    editor = CodeEditor(language="sql")
    qtbot.addWidget(editor)
    editor.setPlainText("a\nb\nc\n")
    editor.set_fold_regions([(0, 1, 2)])
    editor._toggle_fold(editor.document().findBlockByNumber(1))
    assert editor._fold_state == {}
    assert editor.document().findBlockByNumber(2).isVisible() is True


def test_independent_regions_fold_and_expand_without_disturbing_siblings(qtbot):
    """Two sibling DDL objects: folding both then expanding one must leave the
    other collapsed (the _is_line_hidden_by_other_collapsed_fold contract)."""
    editor = CodeEditor(language="sql")
    qtbot.addWidget(editor)
    editor.setPlainText("\n".join(f"L{i}" for i in range(8)) + "\n")
    editor.set_fold_regions([(0, 1, 3), (4, 5, 7)])
    document = editor.document()
    editor._toggle_fold(document.findBlockByNumber(0))
    editor._toggle_fold(document.findBlockByNumber(4))
    assert [document.findBlockByNumber(i).isVisible() for i in range(8)] == [
        True, False, False, False, True, False, False, False
    ]

    editor._toggle_fold(document.findBlockByNumber(0))
    assert [document.findBlockByNumber(i).isVisible() for i in range(8)] == [
        True, True, True, True, True, False, False, False
    ]


def test_sql_navigate_to_line_accounts_for_folded_blocks_above(qtbot):
    """The scrollbar counts VISIBLE blocks, so a collapsed region above the
    target must not make the top-alignment overshoot."""
    editor = _tall_editor(qtbot, "sql")
    editor.set_fold_regions([(0, 1, 49)])
    editor._toggle_fold(editor.document().findBlockByNumber(0))
    editor.navigate_to_line(100)
    # 49 hidden blocks above the target -> 99 - 49 visible blocks precede it.
    assert editor.verticalScrollBar().value() == 50
    assert editor.textCursor().blockNumber() == 99


def test_sql_navigate_to_line_clamps_a_line_below_zero(qtbot):
    editor = _tall_editor(qtbot, "sql")
    editor.navigate_to_line(0)
    assert editor.textCursor().blockNumber() == 0
    assert editor.verticalScrollBar().value() == 0


def test_event_handler_dialog_editor_also_carries_the_gutter(qtbot):
    """Deliberate, user-approved side effect of putting the shared base on
    CodeEditor: the JS/PHP "Edit code..." dialog gains a line-number gutter
    and bookmarks too (folding stays inert -- no regions are installed)."""
    dialog = CodeEditorDialog(language="js")
    qtbot.addWidget(dialog)
    dialog.set_code("function f() {\n  return 1;\n}\n")
    editor = dialog._editor
    assert editor.viewportMargins().left() == editor._gutter_width()
    editor.toggle_bookmark(1)
    assert editor.bookmarked_lines() == [1]
    assert editor._foldable_region_starting_at(editor.document().findBlockByNumber(0)) is None


def test_event_handler_dialog_still_saves_its_text_with_the_gutter_present(qtbot):
    """Regression guard: the mixin sits ahead of QPlainTextEdit in the MRO
    (setPlainText/resizeEvent overrides) -- the dialog's save contract is
    unaffected."""
    dialog = CodeEditorDialog(language="php")
    qtbot.addWidget(dialog)
    dialog.set_code("<?php echo 1;")
    saved = []
    dialog.saved.connect(saved.append)
    dialog.set_code("<?php echo 2;")
    dialog.save()
    assert saved == ["<?php echo 2;"]
