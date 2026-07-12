# tests/ui/test_schema_menu_entry_point.py
"""Tests for the "Annotate Schema Values..." menu entry point wired into
MainWindow — the trigger that constructs and opens AnnotateSchemaValuesDialog.
"""
from unittest.mock import MagicMock, patch

from pgtp_editor.ui.main_window import MainWindow


def test_open_annotate_schema_values_constructs_dialog_with_schema_storage_dir(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)

    mock_dialog_instance = MagicMock()
    with patch(
        "pgtp_editor.ui.main_window.AnnotateSchemaValuesDialog",
        return_value=mock_dialog_instance,
    ) as mock_dialog_class:
        window._open_annotate_schema_values()

    mock_dialog_class.assert_called_once_with(window, schema_storage_dir=storage_dir)
    mock_dialog_instance.exec.assert_called_once()


def test_open_annotate_schema_values_available_with_no_project_open(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)
    assert window._current_project is None

    with patch("pgtp_editor.ui.main_window.AnnotateSchemaValuesDialog") as mock_dialog_class:
        mock_dialog_class.return_value = MagicMock()
        window._open_annotate_schema_values()

    mock_dialog_class.assert_called_once()
