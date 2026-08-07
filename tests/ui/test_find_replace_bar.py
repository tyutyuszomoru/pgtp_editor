from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

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


def test_bar_is_visible_from_construction_with_the_replace_row(qtbot):
    """FQ-016: no `self.hide()`, no show_find/show_replace mode -- the bar is
    permanently visible in its EXPANDED form (both rows)."""
    editor = _editor(qtbot, "alpha")
    host = QWidget()
    qtbot.addWidget(host)
    bar = FindReplaceBar(editor, parent=host)
    # `isVisibleTo(host)`, not `isVisible()`: nothing in this test is on screen,
    # so `isVisible()` is False for any widget. What FQ-016 changed is the bar's
    # OWN show state (the deleted `self.hide()` in __init__), which is what
    # `isVisibleTo` reports -- the same idiom the menu tests use.
    assert bar.isVisibleTo(host) is True
    assert bar._replace_row_widget.isVisibleTo(bar) is True
    assert not hasattr(bar, "show_find")
    assert not hasattr(bar, "show_replace")


def test_focus_find_prefills_from_selection(qtbot):
    editor = _editor(qtbot, "alpha beta gamma")
    _select(editor, 6, 10)  # "beta"
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar.show()
    bar.focus_find()
    assert bar._find_field.text() == "beta"
    assert bar.focusWidget() is bar._find_field


def test_focus_find_no_selection_leaves_field_unchanged(qtbot):
    editor = _editor(qtbot, "alpha beta")
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar._find_field.setText("prev")
    bar.focus_find()
    assert bar._find_field.text() == "prev"


def test_focus_find_never_clobbers_text_the_user_typed(qtbot):
    """The whole reason prefill moved onto the focus path with an emptiness
    guard (FQ-016, FQ-017's precedent): a focus gesture must not overwrite a
    term the user typed just because a selection is still live in the editor."""
    editor = _editor(qtbot, "alpha beta gamma")
    _select(editor, 6, 10)  # "beta" selected in the editor
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar._find_field.setText("gamma")  # what the user typed
    bar.focus_find()
    assert bar._find_field.text() == "gamma"
    # ...while `set_find_text` (the right-click Find path) is unconditional.
    bar.set_find_text("beta")
    assert bar._find_field.text() == "beta"


def test_focus_replace_lands_in_the_replace_field_and_still_arms_find(qtbot):
    editor = _editor(qtbot, "alpha beta gamma")
    _select(editor, 6, 10)  # "beta"
    bar = FindReplaceBar(editor)
    qtbot.addWidget(bar)
    bar.show()
    bar.focus_replace()
    assert bar.focusWidget() is bar._replace_field
    assert bar._find_field.text() == "beta"


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


def test_escape_returns_focus_to_the_editor_and_never_hides(qtbot):
    """FQ-016 reversed this test's original assertion on purpose: Escape used to
    hide the bar; now it only hands focus back."""
    # Both widgets live in the one shown host, so `setFocus` actually takes
    # effect. The editor is deliberately NOT registered with qtbot separately --
    # reparenting a qtbot-owned widget breaks its teardown.
    host = QWidget()
    qtbot.addWidget(host)
    editor = XmlEditor()
    editor.setPlainText("one page")
    bar = FindReplaceBar(editor, parent=host)
    layout = QVBoxLayout(host)
    layout.addWidget(editor)
    layout.addWidget(bar)
    host.show()
    bar.focus_find()
    QApplication.processEvents()
    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    bar.keyPressEvent(event)
    assert bar.isVisibleTo(host) is True
    assert editor.hasFocus() is True


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


# -- FQ-016: the Ctrl+F / Ctrl+R focus shortcuts ----------------------------

def test_install_focus_shortcuts_fires_with_the_caret_in_the_editor(qtbot):
    """The property the host choice exists for: the keys must work while focus is
    in the EDITOR, which is why they are installed on the widget owning both the
    editor and the bar, with `WidgetWithChildrenShortcut` context."""
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtWidgets import QVBoxLayout as _VBox

    from pgtp_editor.ui.find_replace_bar import install_focus_shortcuts

    host = QWidget()
    qtbot.addWidget(host)
    editor = XmlEditor()
    editor.setPlainText("alpha beta")
    bar = FindReplaceBar(editor, parent=host)
    layout = _VBox(host)
    layout.addWidget(editor)
    layout.addWidget(bar)
    find_shortcut, replace_shortcut = install_focus_shortcuts(host, bar)
    assert find_shortcut.context() == _Qt.ShortcutContext.WidgetWithChildrenShortcut
    assert replace_shortcut.context() == _Qt.ShortcutContext.WidgetWithChildrenShortcut

    host.show()
    QApplication.processEvents()
    # A shortcut only dispatches while its window is ACTIVE (offscreen included).
    host.activateWindow()
    QApplication.processEvents()
    editor.setFocus()
    QApplication.processEvents()
    assert host.isActiveWindow() is True

    qtbot.keyClick(editor, _Qt.Key.Key_F, _Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()
    assert bar.focusWidget() is bar._find_field

    editor.setFocus()
    qtbot.keyClick(editor, _Qt.Key.Key_R, _Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()
    assert bar.focusWidget() is bar._replace_field
