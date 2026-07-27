# tests/ui/test_schema_menu_entry_point.py
"""Tests for the Schema menu's Export/Import entry points: verify that the
menu actions are wired to the right handler methods. The "Edit XSD" and
"Verify XSD" menu actions' behavior is tested in tests/ui/test_edit_xsd_tab.py;
the Export/Import behavior (file dialogs, verification, etc.) is tested there
as well. This file just verifies the menu wiring.
The old at-cursor annotate popover / team-sync / schema viewer entry points
(and their tests) were retired as part of the curated-XSD pivot's big
deletion.
"""
from unittest.mock import patch

from tests.ui._menu_helpers import find_action, find_top_menu

from pgtp_editor.ui.main_window import MainWindow


def test_export_xsd_action_triggers_export_xsd(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)

    with patch.object(window, "_export_xsd") as mock_handler:
        menu = find_top_menu(window, "Schema")
        find_action(menu, "Export XSD").trigger()

    mock_handler.assert_called_once()


def test_import_xsd_action_triggers_import_xsd(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)

    with patch.object(window, "_import_xsd") as mock_handler:
        menu = find_top_menu(window, "Schema")
        find_action(menu, "Import XSD").trigger()

    mock_handler.assert_called_once()
