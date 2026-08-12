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

from pgtp_editor.schema_learning.storage import (
    bundled_curated_xsd_text,
    curated_xsd_path,
)
from pgtp_editor.ui import modals
from pgtp_editor.ui import xsd_controller
from pgtp_editor.ui.main_window import MainWindow


def test_export_xsd_action_triggers_export_xsd(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)

    with patch.object(window._xsd_ui, "export") as mock_handler:
        menu = find_top_menu(window, "Schema")
        find_action(menu, "Export XSD").trigger()

    mock_handler.assert_called_once()


def test_import_xsd_action_triggers_import_xsd(qtbot, tmp_path):
    storage_dir = tmp_path / "storage"
    window = MainWindow(schema_storage_dir=storage_dir)
    qtbot.addWidget(window)

    with patch.object(window._xsd_ui, "import_") as mock_handler:
        menu = find_top_menu(window, "Schema")
        find_action(menu, "Import XSD").trigger()

    mock_handler.assert_called_once()


# --- BUG-260812002307 part C: Restore Bundled Curated Schema… ----------------
#
# Driven through the menu's own QAction, not just the handler: a correctly
# implemented method reached by no menu entry is the failure mode this file
# exists to catch.

RESTORE_LABEL = "Restore Bundled Curated Schema…"


def _restore_action(window):
    return find_action(find_top_menu(window, "Schema"), RESTORE_LABEL)


def test_restore_bundled_action_triggers_the_handler(qtbot, tmp_path):
    window = MainWindow(schema_storage_dir=tmp_path / "storage")
    qtbot.addWidget(window)

    with patch.object(window._xsd_ui, "restore_bundled") as mock_handler:
        _restore_action(window).trigger()

    mock_handler.assert_called_once()


def test_restore_bundled_action_carries_no_shortcut(qtbot, tmp_path):
    """DEC-012: a menu command form has exactly one keyboard host, so a chord
    here would have to clear `docs/KEYBINDINGS.md` first. It ships with none."""
    window = MainWindow(schema_storage_dir=tmp_path / "storage")
    qtbot.addWidget(window)
    assert _restore_action(window).shortcut().isEmpty()


def test_restore_overwrites_the_app_data_copy_and_reloads(qtbot, tmp_path, monkeypatch):
    """The one sanctioned exception to §11's "curated.xsd is never overwritten":
    user-initiated and confirmed. `ensure_bootstrap`'s refusal is untouched --
    which is exactly why a corrupted app-data copy had no way back before this."""
    window = MainWindow(schema_storage_dir=tmp_path / "storage")
    qtbot.addWidget(window)
    path = curated_xsd_path(window._schema_storage_dir)
    path.write_text("<broken", encoding="utf-8")
    window._xsd_ui.curated_schema = None

    questions = []
    monkeypatch.setattr(
        modals.QMessageBox, "question",
        staticmethod(
            lambda *a, **k: (
                questions.append(a), modals.QMessageBox.StandardButton.Yes
            )[1]
        ),
    )
    _restore_action(window).trigger()

    assert path.read_text(encoding="utf-8") == bundled_curated_xsd_text()
    # ...and the feed is live again, from the restored file.
    assert window._xsd_ui.curated_schema is not None
    assert window.center_stage.xml_editor.schema_model() is not None
    # The old file is not simply gone.
    assert (path.parent / "curated.xsd.bak").read_text(encoding="utf-8") == "<broken"
    # The confirmation names the path and says what it destroys.
    body = " ".join(str(arg) for arg in questions[0])
    assert str(path) in body
    assert "DESTROYED" in body
    assert any(
        "Restored curated.xsd" in line and str(path) in line
        for line in window.activity_panel.row_texts()
    )


def test_restore_declined_leaves_the_file_alone(qtbot, tmp_path, monkeypatch):
    window = MainWindow(schema_storage_dir=tmp_path / "storage")
    qtbot.addWidget(window)
    path = curated_xsd_path(window._schema_storage_dir)
    path.write_text("<hand-edited", encoding="utf-8")

    monkeypatch.setattr(
        modals.QMessageBox, "question",
        staticmethod(lambda *a, **k: modals.QMessageBox.StandardButton.No),
    )
    _restore_action(window).trigger()

    assert path.read_text(encoding="utf-8") == "<hand-edited"
    assert not (path.parent / "curated.xsd.bak").exists()


def test_restore_refreshes_the_open_edit_xsd_tab(qtbot, tmp_path, monkeypatch):
    """The tab shows the file; after a restore it must not still show the text
    that was just replaced."""
    window = MainWindow(schema_storage_dir=tmp_path / "storage")
    qtbot.addWidget(window)
    window._xsd_ui.open()
    window.center_stage.xsd_editor.setPlainText("<hand-edited")
    assert window._xsd_ui.dirty is True

    monkeypatch.setattr(
        modals.QMessageBox, "question",
        staticmethod(lambda *a, **k: modals.QMessageBox.StandardButton.Yes),
    )
    _restore_action(window).trigger()

    assert window.center_stage.xsd_editor.toPlainText() == bundled_curated_xsd_text()
    assert window._xsd_ui.dirty is False
    assert any(
        "unsaved XSD tab edits were replaced" in line
        for line in window.activity_panel.row_texts()
    )


def test_restore_reports_a_build_with_no_bundled_schema(qtbot, tmp_path, monkeypatch):
    window = MainWindow(schema_storage_dir=tmp_path / "storage")
    qtbot.addWidget(window)
    path = curated_xsd_path(window._schema_storage_dir)
    path.write_text("<hand-edited", encoding="utf-8")

    monkeypatch.setattr(
        xsd_controller, "bundled_curated_xsd_text", lambda: None
    )
    criticals = []
    monkeypatch.setattr(
        modals.QMessageBox, "critical",
        staticmethod(lambda *a, **k: criticals.append(a)),
    )
    monkeypatch.setattr(
        modals.QMessageBox, "question",
        staticmethod(lambda *a, **k: modals.QMessageBox.StandardButton.Yes),
    )
    _restore_action(window).trigger()

    assert criticals
    assert path.read_text(encoding="utf-8") == "<hand-edited"
