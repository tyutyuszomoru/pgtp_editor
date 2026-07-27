# tests/ui/test_schema_menu_entry_point.py
"""Tests for the Schema menu's remaining placeholder entry points wired into
MainWindow: "Export XSD", "Import XSD". Each is a stub wired to
MainWindow._not_implemented("<name>") until Task 11 gives them real
behavior. "Edit XSD" got its real behavior in Task 8 (see
tests/ui/test_edit_xsd_tab.py); "Verify XSD" got its real behavior in Task 10
(see tests/ui/test_edit_xsd_tab.py::test_verify_menu_action_wired); their
"not_implemented" tests were retired here.
The old at-cursor annotate popover / team-sync / schema viewer entry points
(and their tests) were retired as part of the curated-XSD pivot's big
deletion.
"""
from unittest.mock import patch

from tests.ui._menu_helpers import find_action, find_top_menu

from pgtp_editor.ui.main_window import MainWindow


def test_export_xsd_action_triggers_not_implemented(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)

    with patch.object(window, "_not_implemented") as mock_handler:
        menu = find_top_menu(window, "Schema")
        find_action(menu, "Export XSD").trigger()

    mock_handler.assert_called_once_with("Export XSD")


def test_import_xsd_action_triggers_not_implemented(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)

    with patch.object(window, "_not_implemented") as mock_handler:
        menu = find_top_menu(window, "Schema")
        find_action(menu, "Import XSD").trigger()

    mock_handler.assert_called_once_with("Import XSD")
