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


def test_only_manual_and_xsd_tabs_are_closable(qtbot):
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
    # The Manual and Edit XSD tabs keep a close button (whichever side the
    # style uses, BUG-001).
    for index in (cs.manual_tab_index, cs.xsd_tab_index):
        assert (bar.tabButton(index, right) is not None
                or bar.tabButton(index, left) is not None)


def test_xsd_tab_close_button_emits_xsd_close_requested(qtbot):
    """The Edit XSD tab's ✕ must NOT hide the tab directly (BUG-001) --
    closing has to go through MainWindow's unsaved-changes prompt first, so
    the tab-close mechanism only signals intent."""
    cs = CenterStage()
    qtbot.addWidget(cs)
    cs.show_edit_xsd()
    got = []
    cs.xsd_close_requested.connect(lambda: got.append(True))

    cs.tabCloseRequested.emit(cs.xsd_tab_index)

    assert got == [True]
    assert cs.isTabVisible(cs.xsd_tab_index) is True  # unchanged by the signal alone


def test_hide_edit_xsd_hides_tab_and_returns_to_raw_xml(qtbot):
    cs = CenterStage()
    qtbot.addWidget(cs)
    cs.show_edit_xsd()

    cs.hide_edit_xsd()

    assert cs.isTabVisible(cs.xsd_tab_index) is False
    assert cs.currentIndex() == cs.raw_xml_tab_index


def test_hide_edit_xsd_when_not_current_tab_does_not_change_current_index(qtbot):
    """If the user switched away to another tab (e.g. Manual) while the Edit
    XSD tab stayed visible, hiding it must not steal focus back to Raw XML --
    mirrors hide_manual's same not-current guard."""
    cs = CenterStage()
    qtbot.addWidget(cs)
    cs.show_edit_xsd()
    cs.show_manual()  # switches current tab away from xsd_tab_index
    assert cs.currentIndex() == cs.manual_tab_index
    assert cs.isTabVisible(cs.xsd_tab_index) is True  # still visible, just not current

    cs.hide_edit_xsd()

    assert cs.isTabVisible(cs.xsd_tab_index) is False
    assert cs.currentIndex() == cs.manual_tab_index  # unchanged, not forced to Raw XML
