from unittest.mock import patch

from pgtp_editor.ui.main_window import MainWindow


def _window(qtbot, tmp_path):
    window = MainWindow(generator_config_dir=tmp_path)
    qtbot.addWidget(window)
    return window


def test_write_project_text_writes_editor_buffer_verbatim(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText("<Project/>\n")
    target = tmp_path / "out.pgtp"

    window._write_project_text(str(target))

    assert target.read_text(encoding="utf-8") == "<Project/>\n"


def test_write_project_text_makes_bak_on_overwrite(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    target = tmp_path / "out.pgtp"
    target.write_text("OLD CONTENT", encoding="utf-8")
    window.center_stage.xml_editor.setPlainText("NEW CONTENT")

    window._write_project_text(str(target))

    assert target.read_text(encoding="utf-8") == "NEW CONTENT"
    assert (tmp_path / "out.pgtp.bak").read_text(encoding="utf-8") == "OLD CONTENT"


def test_write_project_text_no_bak_when_file_absent(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    target = tmp_path / "fresh.pgtp"
    window.center_stage.xml_editor.setPlainText("data")

    window._write_project_text(str(target))

    assert not (tmp_path / "fresh.pgtp.bak").exists()


def test_save_with_no_current_path_routes_to_save_as(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    assert window._current_project_path is None
    window.center_stage.xml_editor.setPlainText("data")
    target = tmp_path / "saved.pgtp"

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getSaveFileName",
        return_value=(str(target), "PGTP files (*.pgtp)"),
    ):
        window._save_project()

    assert target.read_text(encoding="utf-8") == "data"
    assert window._current_project_path == str(target)


def test_save_with_existing_path_writes_without_dialog(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    target = tmp_path / "existing.pgtp"
    target.write_text("old", encoding="utf-8")
    window._current_project_path = str(target)
    window.center_stage.xml_editor.setPlainText("updated")

    # No dialog should be invoked; if it were, the test would hang -- so the
    # absence of a patch here is itself the assertion that none is shown.
    window._save_project()

    assert target.read_text(encoding="utf-8") == "updated"
    assert window.statusBar().currentMessage() == "Saved existing.pgtp"


def test_save_as_adopts_the_new_path(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText("data")
    target = tmp_path / "as.pgtp"

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getSaveFileName",
        return_value=(str(target), "PGTP files (*.pgtp)"),
    ):
        window._save_project_as()

    assert window._current_project_path == str(target)
    assert window.statusBar().currentMessage() == "Saved as as.pgtp"


def test_save_as_cancel_is_a_noop(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._current_project_path = None
    window.center_stage.xml_editor.setPlainText("data")

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getSaveFileName",
        return_value=("", ""),
    ):
        window._save_project_as()

    assert window._current_project_path is None


def test_save_surfaces_os_error_and_leaves_buffer_untouched(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._current_project_path = str(tmp_path / "x.pgtp")
    window.center_stage.xml_editor.setPlainText("keep me")

    with patch(
        "pgtp_editor.ui.main_window.MainWindow._write_project_text",
        side_effect=OSError("disk full"),
    ), patch("pgtp_editor.ui.main_window.QMessageBox.critical") as mock_critical:
        window._save_project()

    assert mock_critical.called
    assert window.center_stage.xml_editor.toPlainText() == "keep me"


def test_file_menu_save_actions_are_wired(qtbot, tmp_path):
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = _window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText("data")
    target = tmp_path / "menu.pgtp"
    file_menu = find_top_menu(window, "File")

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getSaveFileName",
        return_value=(str(target), "PGTP files (*.pgtp)"),
    ):
        find_action(file_menu, "Save").trigger()

    assert target.read_text(encoding="utf-8") == "data"
