import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pgtp_editor.ui.main_window import MainWindow


def test_manual_populated_and_show_manual_reveals(qtbot):
    win = MainWindow()
    qtbot.addWidget(win)
    win.show()  # top-level must be shown for dock isVisible() to be meaningful
    # Contents populated once at construction.
    assert win.manual_contents.tree.topLevelItemCount() >= 1
    # Manual panel has rendered content.
    assert win.center_stage.manual_panel.document().characterCount() > 100

    win._show_manual()
    cs = win.center_stage
    assert cs.isTabVisible(cs.manual_tab_index) is True
    assert cs.currentIndex() == cs.manual_tab_index
    assert win.tree_dock.isVisible() is True
    # Contents tab selected in the left dock.
    assert win.left_tabs.currentWidget() is win.manual_contents


def test_contents_tab_rides_with_manual(qtbot):
    win = MainWindow()
    qtbot.addWidget(win)
    lt = win.left_tabs
    cs = win.center_stage
    # Hidden by default.
    assert lt.isTabVisible(win.contents_tab_index) is False
    # Opening the Manual reveals + focuses Contents.
    win._show_manual()
    assert lt.isTabVisible(win.contents_tab_index) is True
    assert lt.currentWidget() is win.manual_contents
    # Closing the Manual (e.g. its ✕) hides Contents and falls back to Project.
    cs.hide_manual()
    assert lt.isTabVisible(win.contents_tab_index) is False
    assert lt.currentIndex() == win.project_tab_index


def test_show_manual_toggles_off_when_already_focused(qtbot):
    win = MainWindow()
    qtbot.addWidget(win)
    cs = win.center_stage
    # First trigger reveals it.
    win._show_manual()
    assert cs.isTabVisible(cs.manual_tab_index) is True
    assert cs.currentIndex() == cs.manual_tab_index
    # Second trigger, while it's the focused tab, hides it again.
    win._show_manual()
    assert cs.isTabVisible(cs.manual_tab_index) is False
    assert cs.currentIndex() == cs.raw_xml_tab_index


def test_show_manual_brings_forward_when_visible_but_not_focused(qtbot):
    win = MainWindow()
    qtbot.addWidget(win)
    cs = win.center_stage
    win._show_manual()
    # User clicks away to Raw XML while the Manual tab stays open.
    cs.setCurrentIndex(cs.raw_xml_tab_index)
    # F1 should bring the Manual forward, not hide it.
    win._show_manual()
    assert cs.isTabVisible(cs.manual_tab_index) is True
    assert cs.currentIndex() == cs.manual_tab_index


def test_chapter_click_scrolls_manual(qtbot):
    win = MainWindow()
    qtbot.addWidget(win)
    win._show_manual()
    # Emit a chapter selection; panel cursor should move to that heading block.
    from pgtp_editor.ui.manual_panel import parse_chapters, load_manual_text
    chapters = parse_chapters(load_manual_text())
    target = min(3, len(chapters) - 1)
    win.manual_contents.chapter_selected.emit(target)
    assert win.center_stage.manual_panel.textCursor().block().text() == chapters[target].title
