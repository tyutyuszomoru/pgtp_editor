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
