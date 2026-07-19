"""Ctrl+click (matching tag) / Alt+click (parent tag) navigation."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest

from pgtp_editor.ui.xml_editor import XmlEditor

_DOC = "<root>\n  <page>\n    <col/>\n  </page>\n</root>\n"


def _editor(qtbot, text=_DOC):
    ed = XmlEditor()
    qtbot.addWidget(ed)
    ed.resize(600, 400)
    ed.setPlainText(text)
    return ed


def _click_at_offset(ed, offset, modifier):
    """Click the pixel at `offset`'s cursor rect with `modifier` held."""
    cur = ed.textCursor()
    cur.setPosition(offset)
    pos = ed.cursorRect(cur).center()
    QTest.mouseClick(ed.viewport(), Qt.MouseButton.LeftButton, modifier, pos)


def test_ctrl_click_open_jumps_to_close(qtbot):
    ed = _editor(qtbot)
    _click_at_offset(ed, _DOC.index("<page>") + 2, Qt.KeyboardModifier.ControlModifier)
    assert ed.textCursor().position() == _DOC.index("</page>")
    assert not ed.textCursor().hasSelection()


def test_ctrl_click_close_jumps_to_open(qtbot):
    ed = _editor(qtbot)
    _click_at_offset(ed, _DOC.index("</page>") + 2, Qt.KeyboardModifier.ControlModifier)
    assert ed.textCursor().position() == _DOC.index("<page>")


def test_alt_click_jumps_to_parent_start_no_selection(qtbot):
    ed = _editor(qtbot)
    _click_at_offset(ed, _DOC.index("<col/>") + 2, Qt.KeyboardModifier.AltModifier)
    assert ed.textCursor().position() == _DOC.index("<page>")
    # Alt+click must NOT start a column selection.
    assert not ed.textCursor().hasSelection()


def test_ctrl_click_in_text_content_is_noop_falls_through(qtbot):
    ed = _editor(qtbot)
    # click just past <page>'s '>' (in content, not on a tag) with Ctrl
    offset = _DOC.index("<page>") + len("<page>")
    _click_at_offset(ed, offset, Qt.KeyboardModifier.ControlModifier)
    # No jump: caret is where a normal click landed, near the clicked offset,
    # NOT at a tag boundary. Assert it did not jump to an open/close start.
    assert ed.textCursor().position() not in (
        _DOC.index("<page>"), _DOC.index("</page>"),
    )


def test_plain_click_still_emits_line_clicked(qtbot):
    ed = _editor(qtbot)
    seen = []
    ed.line_clicked.connect(seen.append)
    _click_at_offset(ed, _DOC.index("<col/>") + 2, Qt.KeyboardModifier.NoModifier)
    assert seen and seen[-1] == ed.textCursor().blockNumber() + 1
    assert not ed.textCursor().hasSelection()


def test_ctrl_click_jump_emits_line_clicked_for_target(qtbot):
    ed = _editor(qtbot)
    with qtbot.waitSignal(ed.line_clicked, timeout=500) as sig:
        _click_at_offset(ed, _DOC.index("<page>") + 2, Qt.KeyboardModifier.ControlModifier)
    # target </page> is on its own line
    target_line = _DOC[: _DOC.index("</page>")].count("\n") + 1
    assert sig.args == [target_line]


def test_ctrl_click_caret_stays_after_release(qtbot):
    """Regression: the release must not drag the caret back to the click point."""
    ed = _editor(qtbot)
    _click_at_offset(ed, _DOC.index("<page>") + 2, Qt.KeyboardModifier.ControlModifier)
    assert ed.textCursor().position() == _DOC.index("</page>")
