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


def test_popup_escape_emits_cancelled(qtbot):
    popup = _popup(qtbot, [("alpha", "alpha")])
    with qtbot.waitSignal(popup.cancelled, timeout=500):
        QTest.keyClick(popup, Qt.Key.Key_Escape)
