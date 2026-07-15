"""Sub-project E -- customizable toolbar wiring in MainWindow.

QSettings is isolated via an injected temp ini file.
"""
from PySide6.QtCore import QSettings

from pgtp_editor.ui.main_window import MainWindow
from pgtp_editor.ui.toolbar_registry import DEFAULT_TOOLBAR_IDS
from tests.ui._menu_helpers import find_action, find_top_menu


def _ini_settings(tmp_path, name="s.ini"):
    return QSettings(str(tmp_path / name), QSettings.Format.IniFormat)


def _toolbar_labels(window):
    return [a.text() for a in window._toolbar.actions()]


def test_default_toolbar_has_seven_actions_in_order(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    assert _toolbar_labels(window) == [
        "Open",
        "Save",
        "Undo",
        "Redo",
        "Find",
        "Validate",
        "Generate",
    ]
    assert window._toolbar.objectName() == "main_toolbar"


def test_apply_toolbar_ids_reorders_and_subsets(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window._apply_toolbar_ids(["save", "open"])
    assert _toolbar_labels(window) == ["Save", "Open"]
    assert window._toolbar_ids == ["save", "open"]


def test_apply_toolbar_ids_drops_unknowns(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window._apply_toolbar_ids(["validate", "bogus", "find"])
    assert _toolbar_labels(window) == ["Validate", "Find"]


def test_toolbar_action_triggers_slot(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    called = []
    window._validate_project = lambda: called.append(True)
    # Rebuild so the action rewires to the patched slot.
    window._apply_toolbar_ids(["validate"])
    window._toolbar.actions()[0].trigger()
    assert called == [True]


def test_apply_and_save_persists_and_round_trips(qtbot, tmp_path):
    settings = _ini_settings(tmp_path)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window._apply_and_save_toolbar_ids(["find", "save"])
    assert _toolbar_labels(window) == ["Find", "Save"]

    # A new window reading the same store restores that toolbar.
    settings2 = _ini_settings(tmp_path)
    window2 = MainWindow(settings=settings2)
    qtbot.addWidget(window2)
    assert _toolbar_labels(window2) == ["Find", "Save"]


def test_stored_comma_string_is_restored(qtbot, tmp_path):
    settings = _ini_settings(tmp_path)
    settings.setValue("toolbarIds", "undo,redo")
    settings.sync()
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    assert _toolbar_labels(window) == ["Undo", "Redo"]


def test_unknown_stored_ids_are_dropped(qtbot, tmp_path):
    settings = _ini_settings(tmp_path)
    settings.setValue("toolbarIds", ["save", "bogus", "open"])
    settings.sync()
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    assert _toolbar_labels(window) == ["Save", "Open"]


def test_empty_stored_ids_fall_back_to_default(qtbot, tmp_path):
    settings = _ini_settings(tmp_path)
    settings.setValue("toolbarIds", ["bogus", "nope"])
    settings.sync()
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    assert window._toolbar_ids == DEFAULT_TOOLBAR_IDS


def test_no_stored_ids_uses_default(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    assert window._toolbar_ids == DEFAULT_TOOLBAR_IDS


def test_customize_toolbar_action_in_view_menu(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    view_menu = find_top_menu(window, "View")
    action = find_action(view_menu, "Customize Toolbar…")
    assert action is not None


def test_opening_customize_toolbar_does_not_block(qtbot, tmp_path):
    window = MainWindow(settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    window._open_customize_toolbar()  # non-modal show(), must not raise/block
    assert window._customize_toolbar_dialog is not None
    assert window._customize_toolbar_dialog.selected_ids() == window._toolbar_ids
