from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import QApplication

from pgtp_editor.ui.find_replace_bar import FindReplaceBar
from pgtp_editor.ui.xml_editor import XmlEditor


def _editor(qtbot, text=""):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(text)
    return editor


def _select(editor, start, end):
    cursor = editor.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def test_show_find_prefills_from_selection(qtbot):
    editor = _editor(qtbot, "alpha beta gamma")
    _select(editor, 6, 10)  # "beta"
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar.show_find()
    assert bar._find_field.text() == "beta"
    assert bar.isVisible() is True


def test_show_find_no_selection_leaves_field_unchanged(qtbot):
    editor = _editor(qtbot, "alpha beta")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar._find_field.setText("prev")
    bar.show_find()
    assert bar._find_field.text() == "prev"


def test_find_next_selects_the_match(qtbot):
    editor = _editor(qtbot, "one page two page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    editor.moveCursor(QTextCursor.MoveOperation.Start)
    bar._find_field.setText("page")
    bar.find_next()
    cursor = editor.textCursor()
    assert cursor.selectedText() == "page"
    assert cursor.selectionStart() == 4


def test_find_next_advances_to_second_match(qtbot):
    editor = _editor(qtbot, "one page two page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    editor.moveCursor(QTextCursor.MoveOperation.Start)
    bar._find_field.setText("page")
    bar.find_next()  # selects match at 4
    bar.find_next()  # advances to match at 13
    assert editor.textCursor().selectionStart() == 13


def test_find_next_wraps_around(qtbot):
    editor = _editor(qtbot, "one page two page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    editor.moveCursor(QTextCursor.MoveOperation.Start)
    bar._find_field.setText("page")
    bar.find_next()  # 4
    bar.find_next()  # 13
    bar.find_next()  # wraps back to 4
    assert editor.textCursor().selectionStart() == 4


def test_find_next_empty_term_is_noop(qtbot):
    editor = _editor(qtbot, "one page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    editor.moveCursor(QTextCursor.MoveOperation.Start)
    bar._find_field.setText("")
    bar.find_next()
    assert editor.textCursor().hasSelection() is False


def test_escape_hides_bar_and_refocuses_editor(qtbot):
    editor = _editor(qtbot, "one page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar.show_find()
    QApplication.processEvents()
    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    bar.keyPressEvent(event)
    assert bar.isVisible() is False


# -- Task 4: replace behaviors --------------------------------------------

def test_replace_replaces_current_matching_selection_then_advances(qtbot):
    editor = _editor(qtbot, "page one page two")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar._find_field.setText("page")
    bar._replace_field.setText("PAGE")
    _select(editor, 0, 4)  # current selection == "page", a match

    bar.replace()
    # First occurrence replaced, and selection advanced to the next "page".
    assert editor.toPlainText() == "PAGE one page two"
    assert editor.textCursor().selectedText() == "page"


def test_replace_without_matching_selection_only_finds_next(qtbot):
    editor = _editor(qtbot, "page one page two")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    editor.moveCursor(QTextCursor.MoveOperation.Start)  # no selection
    bar._find_field.setText("page")
    bar._replace_field.setText("PAGE")

    bar.replace()
    # Nothing replaced; just selected the first match.
    assert editor.toPlainText() == "page one page two"
    assert editor.textCursor().selectedText() == "page"


def test_replace_all_replaces_every_occurrence(qtbot):
    editor = _editor(qtbot, "page page PAGE")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar._find_field.setText("page")
    bar._replace_field.setText("X")
    bar.replace_all()
    assert editor.toPlainText() == "X X X"


def test_replace_all_is_single_undo_step(qtbot):
    editor = _editor(qtbot, "page page page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar._find_field.setText("page")
    bar._replace_field.setText("X")
    bar.replace_all()
    assert editor.toPlainText() == "X X X"
    editor.undo()  # a single undo must revert the entire Replace All
    assert editor.toPlainText() == "page page page"


def test_replace_all_with_longer_replacement_keeps_indices_valid(qtbot):
    editor = _editor(qtbot, "ab ab ab")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar._find_field.setText("ab")
    bar._replace_field.setText("LONGER")
    bar.replace_all()
    assert editor.toPlainText() == "LONGER LONGER LONGER"


def test_replace_all_no_matches_is_noop(qtbot):
    editor = _editor(qtbot, "nothing here")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar._find_field.setText("zzz")
    bar._replace_field.setText("X")
    bar.replace_all()
    assert editor.toPlainText() == "nothing here"


def test_set_find_all_running_toggles_button_label(qtbot):
    editor = _editor(qtbot, "page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    assert bar._find_all_button.text() == "Find All"
    bar.set_find_all_running(True)
    assert bar._find_all_button.text() == "Stop"
    bar.set_find_all_running(False)
    assert bar._find_all_button.text() == "Find All"


def test_find_all_calls_on_find_all_when_idle(qtbot):
    editor = _editor(qtbot, "page page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    calls = []
    bar.set_on_find_all(lambda term: calls.append(term))
    bar._find_field.setText("page")
    bar.find_all()
    assert calls == ["page"]


def test_find_all_calls_stop_callback_when_running(qtbot):
    editor = _editor(qtbot, "page page")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    find_calls, stop_calls = [], []
    bar.set_on_find_all(lambda term: find_calls.append(term))
    bar.set_on_stop_find_all(lambda: stop_calls.append(True))
    bar._find_field.setText("page")
    bar.set_find_all_running(True)  # simulate an active run
    bar.find_all()
    assert stop_calls == [True]
    assert find_calls == []  # does NOT start a new find while running


def test_replace_all_reports_status_count(qtbot):
    editor = _editor(qtbot, "page page PAGE")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    messages = []
    bar.set_on_status(lambda msg: messages.append(msg))
    bar._find_field.setText("page")
    bar._replace_field.setText("X")
    bar.replace_all()
    assert editor.toPlainText() == "X X X"
    assert messages == ['3 replacement(s) for "page"']


def test_replace_all_reports_zero_when_no_matches(qtbot):
    editor = _editor(qtbot, "nothing here")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    messages = []
    bar.set_on_status(lambda msg: messages.append(msg))
    bar._find_field.setText("zzz")
    bar._replace_field.setText("X")
    bar.replace_all()
    assert editor.toPlainText() == "nothing here"
    assert messages == ['0 replacement(s) for "zzz"']
