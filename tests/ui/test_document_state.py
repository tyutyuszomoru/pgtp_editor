"""Sub-project A -- document state foundation: dirty tracking, Close, Revert."""
from tests.ui._sample_project import build_sample_project
from tests.ui._menu_helpers import find_action, find_top_menu

from pgtp_editor.ui.main_window import MainWindow

_MINIMAL_PGTP = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Project fileName="demo">\n'
    '  <Page fileName="p1" tableName="pr.equipment" caption="Equipment"/>\n'
    "</Project>\n"
)


def _window(qtbot, tmp_path):
    window = MainWindow(generator_config_dir=tmp_path)
    qtbot.addWidget(window)
    return window


def _make_project(tmp_path, name="demo.pgtp"):
    path = tmp_path / name
    path.write_text(_MINIMAL_PGTP, encoding="utf-8", newline="")
    return path


# -- dirty tracking ---------------------------------------------------------


def test_editing_editor_sets_dirty_and_title_star(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    assert window._dirty is False
    assert " *" not in window.windowTitle()

    window.center_stage.xml_editor.setPlainText("edited by user")

    assert window._dirty is True
    assert window.windowTitle().endswith(" *")


def test_load_clears_dirty(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window._set_dirty(True)
    path = _make_project(tmp_path)

    window.open_project_file(str(path))

    assert window._dirty is False
    assert " *" not in window.windowTitle()
    assert "demo.pgtp" in window.windowTitle()


def test_title_shows_filename_when_open(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    assert "demo.pgtp" in window.windowTitle()
    assert "PGTP Editor" in window.windowTitle()


def test_successful_save_clears_dirty(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    window.center_stage.xml_editor.setPlainText("dirty edit")
    assert window._dirty is True

    window._save_project()

    assert window._dirty is False


# -- .bak on save -----------------------------------------------------------


def test_save_over_existing_makes_bak_with_presave_content(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    target = tmp_path / "existing.pgtp"
    target.write_text("PRE-SAVE", encoding="utf-8")
    window._current_project_path = str(target)
    window.center_stage.xml_editor.setPlainText("POST-SAVE")

    window._save_project()

    assert target.read_text(encoding="utf-8") == "POST-SAVE"
    assert (tmp_path / "existing.pgtp.bak").read_text(encoding="utf-8") == "PRE-SAVE"


def test_save_as_new_path_makes_no_bak(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    target = tmp_path / "brand_new.pgtp"
    window.center_stage.xml_editor.setPlainText("data")

    window._write_project_text(str(target))

    assert not (tmp_path / "brand_new.pgtp.bak").exists()


# -- Close ------------------------------------------------------------------


def test_close_discard_clears_state(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    window.center_stage.xml_editor.setPlainText("dirty")

    window._close_project(confirm="discard")

    assert window._current_project is None
    assert window._current_project_path is None
    assert window._dirty is False
    assert window.project_tree.topLevelItemCount() == 0
    assert window.center_stage.xml_editor.toPlainText() == ""
    assert " *" not in window.windowTitle()


def test_close_cancel_preserves_state(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    window.center_stage.xml_editor.setPlainText("dirty edit")
    tree_count_before = window.project_tree.topLevelItemCount()

    window._close_project(confirm="cancel")

    assert window._current_project is not None
    assert window._current_project_path == str(path)
    assert window._dirty is True
    assert window.project_tree.topLevelItemCount() == tree_count_before
    assert window.center_stage.xml_editor.toPlainText() == "dirty edit"


def test_close_not_dirty_treated_as_discard(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    assert window._dirty is False

    window._close_project()  # confirm is None but not dirty -> discard

    assert window._current_project is None
    assert window._current_project_path is None


def test_close_save_writes_and_closes(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    window.center_stage.xml_editor.setPlainText("saved on close")

    window._close_project(confirm="save")

    assert path.read_text(encoding="utf-8") == "saved on close"
    assert window._current_project is None
    assert window._current_project_path is None
    assert window._dirty is False


def test_close_save_aborts_if_still_dirty(qtbot, tmp_path):
    """If Save routes to Save-As and the user cancels, close aborts."""
    window = _window(qtbot, tmp_path)
    window._current_project = build_sample_project()
    window._current_project_path = None  # forces Save -> Save-As
    window.center_stage.xml_editor.setPlainText("unsaved")
    assert window._dirty is True

    from unittest.mock import patch

    with patch(
        "pgtp_editor.ui.main_window.QFileDialog.getSaveFileName",
        return_value=("", ""),
    ):
        window._close_project(confirm="save")

    # Save-As was cancelled -> still dirty -> close aborted, state intact.
    assert window._dirty is True
    assert window._current_project is not None


def test_close_menu_action_wired(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    file_menu = find_top_menu(window, "File")

    # not dirty -> discard path, no modal
    find_action(file_menu, "Close").trigger()

    assert window._current_project is None


# -- Revert -----------------------------------------------------------------


def test_revert_restores_bak_and_marks_dirty(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    # Create a .bak by saving over the file (pre-save content becomes .bak).
    window.center_stage.xml_editor.setPlainText(_MINIMAL_PGTP)
    window._save_project()  # writes .bak = _MINIMAL_PGTP (pre-save on-disk)
    bak = tmp_path / "demo.pgtp.bak"
    assert bak.exists()
    # Now edit further and revert.
    window.center_stage.xml_editor.setPlainText("something else entirely")

    window._revert_project()

    assert window.center_stage.xml_editor.toPlainText() == bak.read_text(encoding="utf-8")
    assert window._current_project_path == str(path)
    assert window._current_project is not None
    assert window._dirty is True


def test_revert_no_bak_shows_message(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    assert not (tmp_path / "demo.pgtp.bak").exists()
    editor_before = window.center_stage.xml_editor.toPlainText()

    window._revert_project()

    assert window.statusBar().currentMessage() == "Nothing to revert to."
    assert window.center_stage.xml_editor.toPlainText() == editor_before


def test_revert_no_project_path_shows_message(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    assert window._current_project_path is None

    window._revert_project()

    assert window.statusBar().currentMessage() == "Nothing to revert to."


def test_revert_menu_action_wired(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    file_menu = find_top_menu(window, "File")
    # No project loaded -> message path, no modal, no crash.
    find_action(file_menu, "Revert").trigger()
    assert window.statusBar().currentMessage() == "Nothing to revert to."
