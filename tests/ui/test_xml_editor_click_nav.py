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


# --- feature-tester gap fill ---


def test_ctrl_click_on_self_closing_tag_is_noop(qtbot):
    # <col/> has no partner; Ctrl+click must fall through (no jump, no crash).
    ed = _editor(qtbot)
    offset = _DOC.index("<col/>") + 2
    _click_at_offset(ed, offset, Qt.KeyboardModifier.ControlModifier)
    # Caret did not jump to any tag boundary; it landed at the plain-click spot.
    assert ed.textCursor().position() not in (
        _DOC.index("<page>"), _DOC.index("</page>"), _DOC.index("<root>"),
    )
    assert not ed.textCursor().hasSelection()


def test_ctrl_shift_click_falls_through_no_jump(qtbot):
    # Modifiers != exactly Ctrl and != exactly Alt must not trigger a jump.
    ed = _editor(qtbot)
    seen = []
    ed.line_clicked.connect(seen.append)
    offset = _DOC.index("<page>") + 2
    _click_at_offset(
        ed, offset,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    # No jump to the matching close tag.
    assert ed.textCursor().position() != _DOC.index("</page>")
    # Normal release path still emitted line_clicked for the clicked line.
    assert seen and seen[-1] == ed.textCursor().blockNumber() + 1


def test_ctrl_alt_click_falls_through_no_jump(qtbot):
    ed = _editor(qtbot)
    offset = _DOC.index("<col/>") + 2
    _click_at_offset(
        ed, offset,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
    )
    # Neither the matching-tag jump nor the parent jump fired.
    assert ed.textCursor().position() != _DOC.index("<page>")


def test_ctrl_click_after_edit_uses_updated_offsets(qtbot):
    # Editing the document shifts every offset; the jump must land on the NEW
    # matching-tag offset (spans are re-scanned on textChanged / revision guard).
    ed = _editor(qtbot)
    prefix = "<wrap>\n"
    cur = ed.textCursor()
    cur.setPosition(0)
    cur.insertText(prefix)
    new_text = ed.toPlainText()
    _click_at_offset(ed, new_text.index("<page>") + 2, Qt.KeyboardModifier.ControlModifier)
    assert ed.textCursor().position() == new_text.index("</page>")


def test_ctrl_click_target_on_folded_region_lands_at_correct_offset(qtbot):
    # With an inner region collapsed, an outer Ctrl+click must still resolve to
    # the exact character offset (spans use offsets, independent of visibility).
    doc = "<root>\n  <page>\n    <col>\n      x\n    </col>\n  </page>\n</root>\n"
    ed = _editor(qtbot, doc)
    # Collapse the <col> fold (hides the "x" content line).
    col_block = ed.document().findBlock(doc.index("<col>"))
    ed._toggle_fold(col_block)
    # Sanity: the fold actually hid the inner content line.
    assert not ed.document().findBlock(doc.index("x")).isVisible()
    # Ctrl+click the still-visible <page> open tag -> jump to </page>.
    _click_at_offset(ed, doc.index("<page>") + 2, Qt.KeyboardModifier.ControlModifier)
    assert ed.textCursor().position() == doc.index("</page>")


def test_alt_click_on_top_level_element_is_noop(qtbot):
    # Alt+click inside the top-level <root> open tag: no parent -> fall through.
    ed = _editor(qtbot)
    offset = _DOC.index("<root>") + 2
    _click_at_offset(ed, offset, Qt.KeyboardModifier.AltModifier)
    assert not ed.textCursor().hasSelection()
