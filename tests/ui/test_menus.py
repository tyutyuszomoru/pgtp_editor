# tests/ui/test_menus.py
from pgtp_editor.ui.main_window import MainWindow
from tests.ui._menu_helpers import action_labels, find_action, find_top_menu


def test_file_menu_contents(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    file_menu = find_top_menu(window, "File")
    assert file_menu is not None
    labels = action_labels(file_menu)
    assert labels == [
        "New Project", "Open...", "Open Recent", "Save", "Save As...", "Close", "―", "Exit",
    ]


def test_open_recent_is_an_empty_submenu(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    file_menu = find_top_menu(window, "File")
    open_recent_action = find_action(file_menu, "Open Recent")
    open_recent_menu = open_recent_action.menu()
    assert open_recent_menu is not None
    assert open_recent_menu.actions() == []


def test_exit_action_closes_window(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    file_menu = find_top_menu(window, "File")
    find_action(file_menu, "Exit").trigger()
    assert window.isVisible() is False


def test_other_file_actions_show_stub_message(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    file_menu = find_top_menu(window, "File")
    find_action(file_menu, "New Project").trigger()
    assert window.statusBar().currentMessage() == "Not yet implemented: New Project"
