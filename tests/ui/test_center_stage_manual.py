import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pgtp_editor.ui.center_stage import CenterStage


def test_manual_tab_hidden_until_shown(qtbot):
    cs = CenterStage()
    qtbot.addWidget(cs)
    assert cs.isTabVisible(cs.manual_tab_index) is False
    cs.show_manual()
    assert cs.isTabVisible(cs.manual_tab_index) is True
    assert cs.currentIndex() == cs.manual_tab_index


def test_hide_manual_hides_tab_and_returns_to_raw_xml(qtbot):
    cs = CenterStage()
    qtbot.addWidget(cs)
    cs.show_manual()
    cs.hide_manual()
    assert cs.isTabVisible(cs.manual_tab_index) is False
    assert cs.currentIndex() == cs.raw_xml_tab_index


def test_manual_tab_close_button_hides_it(qtbot):
    cs = CenterStage()
    qtbot.addWidget(cs)
    cs.show_manual()
    # The Manual tab's ✕ emits tabCloseRequested with its index.
    cs.tabCloseRequested.emit(cs.manual_tab_index)
    assert cs.isTabVisible(cs.manual_tab_index) is False
    assert cs.currentIndex() == cs.raw_xml_tab_index


def test_only_manual_tab_is_closable(qtbot):
    from PySide6.QtWidgets import QTabBar

    cs = CenterStage()
    qtbot.addWidget(cs)
    assert cs.tabsClosable() is True
    bar = cs.tabBar()
    right = QTabBar.ButtonPosition.RightSide
    left = QTabBar.ButtonPosition.LeftSide
    # Structural tabs have no close button on either side.
    for index in (cs.raw_xml_tab_index, cs.diff_merge_tab_index,
                  cs.caption_management_tab_index):
        assert bar.tabButton(index, right) is None
        assert bar.tabButton(index, left) is None
    # The Manual tab keeps a close button (on whichever side the style uses).
    assert (bar.tabButton(cs.manual_tab_index, right) is not None
            or bar.tabButton(cs.manual_tab_index, left) is not None)
