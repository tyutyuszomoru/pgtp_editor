from PySide6.QtGui import QTextCursor

from pgtp_editor.ui.xml_editor import XmlEditor


def test_replace_current_selection_replaces_selected_text(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("hello world")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)  # select "hello"
    editor.setTextCursor(cursor)

    editor.replace_current_selection("goodbye")
    assert editor.toPlainText() == "goodbye world"


def test_replace_current_selection_noop_without_selection(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("hello world")
    cursor = editor.textCursor()
    cursor.setPosition(5)  # no selection, just a caret
    editor.setTextCursor(cursor)

    editor.replace_current_selection("XXX")
    assert editor.toPlainText() == "hello world"


def test_replace_current_selection_is_single_undo_step(qtbot):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText("hello world")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)

    editor.replace_current_selection("goodbye")
    assert editor.toPlainText() == "goodbye world"
    editor.undo()
    assert editor.toPlainText() == "hello world"
