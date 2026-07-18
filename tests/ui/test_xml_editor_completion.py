"""Ctrl+Space attribute/value completion: the reusable _CompletionPopup and
the XmlEditor seams that drive it (never via a blocking modal)."""
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from pgtp_editor.schema_learning.model import Model
from pgtp_editor.ui.xml_editor import XmlEditor, _CompletionPopup


def _popup(qtbot, items):
    popup = _CompletionPopup()
    qtbot.addWidget(popup)
    popup.set_items(items)
    return popup


def test_popup_lists_all_keys_initially(qtbot):
    popup = _popup(qtbot, [("alpha", "alpha"), ("beta", "beta")])
    assert popup.visible_keys() == ["alpha", "beta"]
    assert popup.current_key() == "alpha"  # row 0 preselected


def test_popup_filter_prefix_case_insensitive(qtbot):
    popup = _popup(qtbot, [("alpha", "alpha"), ("Album", "Album"), ("beta", "beta")])
    popup.append_filter("al")
    assert popup.visible_keys() == ["alpha", "Album"]
    assert popup.current_key() == "alpha"  # master order preserved, row 0


def test_popup_backspace_restores(qtbot):
    popup = _popup(qtbot, [("alpha", "alpha"), ("beta", "beta")])
    popup.append_filter("a")
    assert popup.visible_keys() == ["alpha"]
    popup.backspace_filter()
    assert popup.visible_keys() == ["alpha", "beta"]


def test_popup_display_differs_from_key(qtbot):
    popup = _popup(qtbot, [("1", "1 = modal"), ("2", "2 = new page")])
    # keys drive filtering/selection; display is what the row shows
    assert popup.visible_keys() == ["1", "2"]
    assert popup.item(0).text() == "1 = modal"


def test_popup_enter_emits_chosen_current_key(qtbot):
    popup = _popup(qtbot, [("alpha", "alpha"), ("beta", "beta")])
    with qtbot.waitSignal(popup.chosen, timeout=500) as sig:
        QTest.keyClick(popup, Qt.Key.Key_Return)
    assert sig.args == ["alpha"]


def test_popup_tab_emits_chosen(qtbot):
    popup = _popup(qtbot, [("alpha", "alpha")])
    with qtbot.waitSignal(popup.chosen, timeout=500) as sig:
        QTest.keyClick(popup, Qt.Key.Key_Tab)
    assert sig.args == ["alpha"]


def test_popup_typed_chars_filter_via_keypress(qtbot):
    popup = _popup(qtbot, [("alpha", "alpha"), ("beta", "beta")])
    QTest.keyClick(popup, Qt.Key.Key_A)
    assert popup.visible_keys() == ["alpha"]
    QTest.keyClick(popup, Qt.Key.Key_Backspace)
    assert popup.visible_keys() == ["alpha", "beta"]


def test_popup_ctrl_key_not_swallowed_into_filter(qtbot):
    popup = _popup(qtbot, [("alpha", "alpha"), ("beta", "beta")])
    QTest.keyClick(popup, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert popup.visible_keys() == ["alpha", "beta"]  # filter unchanged


def test_popup_escape_emits_cancelled(qtbot):
    popup = _popup(qtbot, [("alpha", "alpha")])
    with qtbot.waitSignal(popup.cancelled, timeout=500):
        QTest.keyClick(popup, Qt.Key.Key_Escape)


def _model_attrs(tag_chain, names):
    model = Model()
    model.paths[tag_chain] = {
        "attributes": {
            n: {
                "type": "integer",
                "values": [],
                "overflowed": False,
                "attr_seen_count": 1,
                "labels": {},
            }
            for n in names
        },
        "children": {},
        "instance_count": 1,
        "order": [],
        "order_stable": True,
        "has_text": False,
    }
    return model


def _editor_in_tag(qtbot, text, model, marker):
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(text)
    editor.set_schema_model(model)
    cursor = editor.textCursor()
    cursor.setPosition(text.index(marker))
    editor.setTextCursor(cursor)
    return editor


def test_ctrl_space_opens_attribute_popup(qtbot):
    text = '<Page editFormMode="1"></Page>'
    model = _model_attrs("Page", ["editFormMode", "pageMode", "layout"])
    editor = _editor_in_tag(qtbot, text, model, "Page")
    QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
    popup = editor._completion_popup
    assert popup is not None and popup.isVisible()
    assert popup.visible_keys() == ["layout", "pageMode"]  # present editFormMode excluded


def test_ctrl_space_no_popup_without_model(qtbot):
    text = '<Page editFormMode="1"></Page>'
    editor = XmlEditor()
    qtbot.addWidget(editor)
    editor.setPlainText(text)
    cursor = editor.textCursor()
    cursor.setPosition(text.index("Page"))
    editor.setTextCursor(cursor)
    QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
    assert editor._completion_popup is None or not editor._completion_popup.isVisible()


def test_ctrl_space_no_popup_when_read_only(qtbot):
    text = '<Page editFormMode="1"></Page>'
    model = _model_attrs("Page", ["pageMode"])
    editor = _editor_in_tag(qtbot, text, model, "Page")
    editor.setReadOnly(True)
    QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
    assert editor._completion_popup is None or not editor._completion_popup.isVisible()


def test_ctrl_space_no_popup_outside_tag(qtbot):
    text = "<Page>body</Page>"
    model = _model_attrs("Page", ["pageMode"])
    editor = _editor_in_tag(qtbot, text, model, "body")
    QTest.keyClick(editor, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
    assert editor._completion_popup is None or not editor._completion_popup.isVisible()


def test_choosing_attribute_inserts_name_equals_quotes(qtbot):
    text = '<Page editFormMode="1"></Page>'
    model = _model_attrs("Page", ["pageMode"])
    editor = _editor_in_tag(qtbot, text, model, "Page")
    editor._show_attribute_completions()
    editor._completion_popup.chosen.emit("pageMode")
    new_text = editor.toPlainText()
    assert new_text == '<Page editFormMode="1" pageMode=""></Page>'
    caret = editor.textCursor().position()
    assert new_text[caret - 1] == '"' and new_text[caret] == '"'
    assert not editor._completion_popup.isVisible()  # popup dismissed after choose


def test_attribute_insert_is_single_undo(qtbot):
    text = '<Page editFormMode="1"></Page>'
    model = _model_attrs("Page", ["pageMode"])
    editor = _editor_in_tag(qtbot, text, model, "Page")
    editor._show_attribute_completions()
    editor._completion_popup.chosen.emit("pageMode")
    assert "pageMode" in editor.toPlainText()
    editor.undo()
    assert editor.toPlainText() == text
