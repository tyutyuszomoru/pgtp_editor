# tests/ui/test_schema_menu_entry_point.py
"""Tests for the Schema menu's "Annotate Value at Cursor" / "Next Unlabeled
Value" entry points wired into MainWindow. The old "Annotate Schema
Values..." dialog entry point (and its _open_annotate_schema_values method)
was retired in favor of the at-cursor AnnotatePopover flow; see
tests/ui/test_annotate_wiring.py for the popover/persistence coverage.
"""
from unittest.mock import patch

from tests.ui._menu_helpers import find_action, find_top_menu

from pgtp_editor.ui.main_window import MainWindow


def test_annotate_value_at_cursor_action_triggers_handler(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)

    with patch.object(window, "_annotate_value_at_cursor") as mock_handler:
        menu = find_top_menu(window, "Schema")
        find_action(menu, "Annotate Value at Cursor").trigger()

    mock_handler.assert_called_once()


def test_next_unlabeled_value_action_triggers_handler(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)

    with patch.object(window, "_goto_next_unlabeled_value") as mock_handler:
        menu = find_top_menu(window, "Schema")
        find_action(menu, "Next Unlabeled Value").trigger()

    mock_handler.assert_called_once()


def test_annotate_value_at_cursor_with_no_schema_shows_status_message(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)
    assert window.center_stage.xml_editor.schema_model() is None

    window._annotate_value_at_cursor()

    assert window.statusBar().currentMessage() == window._NO_SCHEMA_MESSAGE


def test_next_unlabeled_value_with_no_matches_shows_status_message(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)

    with patch.object(
        window.center_stage.xml_editor, "goto_next_unlabeled_value", return_value=False
    ):
        window._goto_next_unlabeled_value()

    assert window.statusBar().currentMessage() == (
        "No unlabeled enum values in this document."
    )
