"""§8/§13 — the Navigation menu is disabled during Caption Mode.

Caption Mode makes the Raw XML editor read-only, but the bookmark actions and their
four shortcuts stayed live. The gate is a lane seam
(`FindValidateController.set_bookmarks_enabled`), not a reach-in: the lane owns
the menu, so it owns disabling it.

Both halves are asserted deliberately. Disabling only the `QMenu` grays out the
menu-bar entry but leaves Ctrl+F2 / F2 / Shift+F2 firing -- Qt drops a shortcut
only when the ACTION is disabled -- which is exactly the bug this closes.
"""
from pgtp_editor.ui.main_window import MainWindow
from tests.ui._menu_helpers import action_labels, find_top_menu

_MINIMAL_PGTP = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Project fileName="demo">\n'
    '  <Page fileName="p1" tableName="pr.equipment" caption="Equipment"/>\n'
    "</Project>\n"
)


def _window(qtbot, tmp_path):
    window = MainWindow(generator_config_dir=tmp_path)
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText(_MINIMAL_PGTP)
    return window


def test_the_lane_retains_its_menu_and_five_actions(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    menu = find_top_menu(window, "Navigation")

    assert window._find_ui.navigation_menu is menu
    assert [action.text() for action in window._find_ui.bookmark_actions] == [
        "Toggle Bookmark",
        "Next Bookmark",
        "Previous Bookmark",
        "Clear All Bookmarks",
        "List All Bookmarks",
    ]
    # The separator is not one of them.
    assert "―" in action_labels(menu)


def test_bookmarks_are_enabled_outside_caption_mode(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    assert find_top_menu(window, "Navigation").isEnabled() is True
    for action in window._find_ui.bookmark_actions:
        assert action.isEnabled() is True


def test_entering_caption_mode_disables_the_menu_and_every_action(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)

    assert window._enter_caption_mode() is True

    assert find_top_menu(window, "Navigation").isEnabled() is False
    for action in window._find_ui.bookmark_actions:
        assert action.isEnabled() is False, action.text()


def test_leaving_caption_mode_restores_them(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._enter_caption_mode()

    window._close_caption_mode()

    assert find_top_menu(window, "Navigation").isEnabled() is True
    for action in window._find_ui.bookmark_actions:
        assert action.isEnabled() is True, action.text()


def test_a_refused_caption_entry_leaves_bookmarks_alone(qtbot, tmp_path):
    """Entering fails on an empty Raw XML buffer -- and then nothing was gated."""
    window = MainWindow(generator_config_dir=tmp_path)
    qtbot.addWidget(window)

    assert window._enter_caption_mode() is False

    assert find_top_menu(window, "Navigation").isEnabled() is True
    for action in window._find_ui.bookmark_actions:
        assert action.isEnabled() is True


def test_gutter_bookmark_toggling_is_not_gated(qtbot, tmp_path):
    """§8, explicitly: bookmarks are a UI overlay independent of the editor's
    read-only state -- only the MENU (and therefore its shortcuts) is gated."""
    window = _window(qtbot, tmp_path)
    editor = window.center_stage.xml_editor
    window._enter_caption_mode()

    editor.toggle_bookmark(1)

    assert 1 in editor.bookmarked_lines()


def test_set_bookmarks_enabled_is_safe_before_the_menu_is_built(qtbot):
    """The host may gate before `build_navigation_menu` has run."""
    from pgtp_editor.ui.find_controller import FindValidateController

    controller = FindValidateController(
        shell=None, project=lambda: None, project_path=lambda: None
    )
    assert controller.navigation_menu is None
    assert controller.bookmark_actions == ()
    controller.set_bookmarks_enabled(False)  # must not raise
