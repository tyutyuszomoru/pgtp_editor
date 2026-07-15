from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit

from pgtp_editor.ui.code_editor import (
    CodeEditor,
    CodeEditorDialog,
    _CodeHighlighter,
    _JS_KEYWORDS,
    _PHP_KEYWORDS,
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
