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

    window._doc_ui._write_project_text(str(target))

    assert target.read_text(encoding="utf-8") == "<Project/>\n"


def test_write_project_text_preserves_lf_no_crlf_translation(qtbot, tmp_path):
    """Regression: Path.write_text opens in text mode, so on Windows it
    translates \\n -> \\r\\n, silently corrupting LF-lined .pgtp files. The
    editor holds LF; the file on disk must hold LF byte-for-byte."""
    window = _window(qtbot, tmp_path)
    text = "<a>\n  <b/>\n</a>\n"
    window.center_stage.xml_editor.setPlainText(text)
    target = tmp_path / "x.pgtp"

    window._doc_ui._write_project_text(str(target))

    data = target.read_bytes()
    assert b"\r\n" not in data
    assert b"\r" not in data
    assert data == text.encode("utf-8")


def test_write_project_text_makes_bak_on_overwrite(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    target = tmp_path / "out.pgtp"
    target.write_text("OLD CONTENT", encoding="utf-8")
    window.center_stage.xml_editor.setPlainText("NEW CONTENT")

    window._doc_ui._write_project_text(str(target))

    assert target.read_text(encoding="utf-8") == "NEW CONTENT"
    assert (tmp_path / "out.pgtp.bak").read_text(encoding="utf-8") == "OLD CONTENT"


def test_write_project_text_no_bak_when_file_absent(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    target = tmp_path / "fresh.pgtp"
    window.center_stage.xml_editor.setPlainText("data")

    window._doc_ui._write_project_text(str(target))

    assert not (tmp_path / "fresh.pgtp.bak").exists()


def test_save_with_no_current_path_routes_to_save_as(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    assert window._current_project_path is None
    window.center_stage.xml_editor.setPlainText("data")
    target = tmp_path / "saved.pgtp"

    with patch(
        "pgtp_editor.ui.modals.QFileDialog.getSaveFileName",
        return_value=(str(target), "PGTP files (*.pgtp)"),
    ):
        window._doc_ui.save_project()

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
    window._doc_ui.save_project()

    assert target.read_text(encoding="utf-8") == "updated"
    assert window.statusBar().currentMessage() == "Saved existing.pgtp"


def test_save_as_adopts_the_new_path(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText("data")
    target = tmp_path / "as.pgtp"

    with patch(
        "pgtp_editor.ui.modals.QFileDialog.getSaveFileName",
        return_value=(str(target), "PGTP files (*.pgtp)"),
    ):
        window._doc_ui.save_as()

    assert window._current_project_path == str(target)
    assert window.statusBar().currentMessage() == "Saved as as.pgtp"


def test_save_as_cancel_is_a_noop(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._current_project_path = None
    window.center_stage.xml_editor.setPlainText("data")

    with patch(
        "pgtp_editor.ui.modals.QFileDialog.getSaveFileName",
        return_value=("", ""),
    ):
        window._doc_ui.save_as()

    assert window._current_project_path is None


def test_save_surfaces_os_error_and_leaves_buffer_untouched(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._current_project_path = str(tmp_path / "x.pgtp")
    window.center_stage.xml_editor.setPlainText("keep me")

    with patch(
        "pgtp_editor.ui.pgtp_document_controller.PgtpDocumentController._write_project_text",
        side_effect=OSError("disk full"),
    ), patch("pgtp_editor.ui.modals.QMessageBox.critical") as mock_critical:
        window._doc_ui.save_project()

    assert mock_critical.called
    assert window.center_stage.xml_editor.toPlainText() == "keep me"


def test_deployment_menu_save_actions_are_wired(qtbot, tmp_path):
    """FQ-020: this WAS `test_file_menu_save_actions_are_wired`, driving
    `File ▸ Save`. Saving the `.pgtp` is now `Deployment ▸ Save pgtp` (in place)
    and `Deployment ▸ Save as new pgtp` (Save As), both on the Raw XML tab. With
    no path yet, `save_project` still falls through to Save As -- the mechanism
    is unchanged, only the trigger moved."""
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = _window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText("data")
    target = tmp_path / "menu.pgtp"
    menu = find_top_menu(window, "Deployment")
    save_pgtp = find_action(menu, "Save pgtp")
    assert save_pgtp is not None and save_pgtp.isVisible()

    with patch(
        "pgtp_editor.ui.modals.QFileDialog.getSaveFileName",
        return_value=(str(target), "PGTP files (*.pgtp)"),
    ):
        save_pgtp.trigger()

    assert target.read_text(encoding="utf-8") == "data"

    # ...and `Save as new pgtp` writes to a freshly chosen path.
    other = tmp_path / "other.pgtp"
    window.center_stage.xml_editor.setPlainText("data 2")
    with patch(
        "pgtp_editor.ui.modals.QFileDialog.getSaveFileName",
        return_value=(str(other), "PGTP files (*.pgtp)"),
    ):
        find_action(menu, "Save as new pgtp").trigger()

    assert other.read_text(encoding="utf-8") == "data 2"


def test_the_file_menu_no_longer_offers_save_at_all(qtbot, tmp_path):
    """FQ-020: `File ▸ Save` / `Save As…` are deleted outright, not relabelled or
    hidden -- two homes for one capability is the ambiguity being removed."""
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = _window(qtbot, tmp_path)
    file_menu = find_top_menu(window, "File")
    assert find_action(file_menu, "Save") is None
    assert find_action(file_menu, "Save As...") is None


# --- FQ-010: the `recentFiles` STORE is gone, not just its menu -------------
#
# `tests/ui/test_menus.py` and `tests/ui/test_toolbar.py` assert the *menu* and
# the *pinnable command* are gone. Neither touches the QSettings store, and the
# store had exactly two writers -- `open_file` and `save_as`. Without these, a
# re-added `remember_recent_file()` call would silently start recording the
# user's file history again and every existing test would still pass.


def _ini_settings(tmp_path):
    from PySide6.QtCore import QSettings

    return QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)


def _recent_shaped_keys(settings):
    settings.sync()
    return [key for key in settings.allKeys() if "recent" in key.lower()]


def test_save_as_records_nothing_recent_shaped_in_settings(qtbot, tmp_path):
    settings = _ini_settings(tmp_path)
    window = MainWindow(generator_config_dir=tmp_path, settings=settings)
    qtbot.addWidget(window)
    window.center_stage.xml_editor.setPlainText("<Project/>\n")
    target = tmp_path / "as.pgtp"

    with patch(
        "pgtp_editor.ui.modals.QFileDialog.getSaveFileName",
        return_value=(str(target), "PGTP files (*.pgtp)"),
    ):
        window._doc_ui.save_as()

    assert window._current_project_path == str(target)  # the save really happened
    assert _recent_shaped_keys(settings) == []


def test_open_file_records_nothing_recent_shaped_in_settings(qtbot, tmp_path):
    settings = _ini_settings(tmp_path)
    window = MainWindow(generator_config_dir=tmp_path, settings=settings)
    qtbot.addWidget(window)
    source = tmp_path / "in.pgtp"
    source.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<Project fileName="demo"/>\n',
        encoding="utf-8",
    )

    window._doc_ui.open_file(str(source))

    assert window._current_project_path == str(source)  # the open really happened
    assert _recent_shaped_keys(settings) == []


def test_the_document_controller_has_no_recent_files_api_left(qtbot, tmp_path):
    """Deleted, not left inert: FQ-010 removed the reader, the writer and the
    menu rebuilder along with the key constant."""
    from pgtp_editor.ui import pgtp_document_controller as mod

    window = MainWindow(generator_config_dir=tmp_path, settings=_ini_settings(tmp_path))
    qtbot.addWidget(window)
    for gone in ("recent_files", "remember_recent_file", "rebuild_recent_menu"):
        assert not hasattr(window._doc_ui, gone), gone
    for gone in ("_RECENT_FILES_KEY", "_RECENT_FILES_MAX"):
        assert not hasattr(mod, gone), gone
