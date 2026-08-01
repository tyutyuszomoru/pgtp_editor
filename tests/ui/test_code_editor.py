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


def test_dialog_ctrl_s_saves(qtbot):
    dialog = CodeEditorDialog(language="js")
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    dialog.set_code("abc")
    dialog._editor.setFocus()
    with qtbot.waitSignal(dialog.saved, timeout=1000) as blocker:
        qtbot.keyClick(dialog, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    assert blocker.args == ["abc"]


def test_dialog_ctrl_w_cancels(qtbot):
    dialog = CodeEditorDialog(language="js")
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    with qtbot.waitSignal(dialog.cancelled, timeout=1000):
        qtbot.keyClick(dialog, Qt.Key.Key_W, Qt.KeyboardModifier.ControlModifier)


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
