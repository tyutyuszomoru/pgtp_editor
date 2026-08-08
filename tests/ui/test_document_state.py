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
    window._doc_ui.set_dirty(True)
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

    window._doc_ui.save_project()

    assert window._dirty is False


# -- .bak on save -----------------------------------------------------------


def test_save_over_existing_makes_bak_with_presave_content(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    target = tmp_path / "existing.pgtp"
    target.write_text("PRE-SAVE", encoding="utf-8")
    window._current_project_path = str(target)
    window.center_stage.xml_editor.setPlainText("POST-SAVE")

    window._doc_ui.save_project()

    assert target.read_text(encoding="utf-8") == "POST-SAVE"
    assert (tmp_path / "existing.pgtp.bak").read_text(encoding="utf-8") == "PRE-SAVE"


def test_save_as_new_path_makes_no_bak(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    target = tmp_path / "brand_new.pgtp"
    window.center_stage.xml_editor.setPlainText("data")

    window._doc_ui._write_project_text(str(target))

    assert not (tmp_path / "brand_new.pgtp.bak").exists()


# -- Close ------------------------------------------------------------------


def test_close_discard_clears_state(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    window.center_stage.xml_editor.setPlainText("dirty")

    window._doc_ui.close(confirm="discard")

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

    window._doc_ui.close(confirm="cancel")

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

    window._doc_ui.close()  # confirm is None but not dirty -> discard

    assert window._current_project is None
    assert window._current_project_path is None


def test_close_save_writes_and_closes(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    window.center_stage.xml_editor.setPlainText("saved on close")

    window._doc_ui.close(confirm="save")

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
        "pgtp_editor.ui.modals.QFileDialog.getSaveFileName",
        return_value=("", ""),
    ):
        window._doc_ui.close(confirm="save")

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


# -- Discard Changes (FQ-020: was Revert) ------------------------------------
#
# These six tests were `revert()`'s. FQ-020 replaced that command outright: it
# reloaded `<path>.bak` ("undo my last save") and left the buffer DIRTY, where
# `Discard Changes` reloads from DISK and leaves it CLEAN, gated on the dirty flag
# rather than on a `.bak` existing. So they are re-pointed at the new contract
# rather than deleted -- each one still asserts the same *kind* of thing (the
# happy path, the two nothing-to-do paths, the menu gate, the close reset and the
# runtime second guard).


def test_discard_changes_reloads_from_disk_and_marks_clean(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    on_disk = path.read_text(encoding="utf-8")
    window.center_stage.xml_editor.setPlainText(_MINIMAL_PGTP)
    assert window._dirty is True

    window._doc_ui.discard_changes(confirm=True)

    assert window.center_stage.xml_editor.toPlainText() == on_disk
    assert window._current_project_path == str(path)
    assert window._current_project is not None
    # The opposite of `revert()`, which left the buffer dirty because it had
    # loaded a DIFFERENT file: the buffer now IS what is on disk.
    assert window._dirty is False
    assert "Discarded changes in demo.pgtp" in window.statusBar().currentMessage()


def test_discard_changes_writes_no_bak_of_its_own(qtbot, tmp_path):
    """FQ-020: the `.bak` is out of this command entirely -- neither read (the
    old `revert`) nor written."""
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    window.center_stage.xml_editor.setPlainText(_MINIMAL_PGTP)

    window._doc_ui.discard_changes(confirm=True)

    assert not (tmp_path / "demo.pgtp.bak").exists()
    assert not hasattr(window._doc_ui, "backup_path")
    assert not hasattr(window._doc_ui, "revert")


def test_discard_changes_cancelled_keeps_the_edits(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    window.center_stage.xml_editor.setPlainText("something else entirely")

    window._doc_ui.discard_changes(confirm=False)

    assert window.center_stage.xml_editor.toPlainText() == "something else entirely"
    assert window._dirty is True


def test_discard_changes_with_a_clean_buffer_shows_message(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    editor_before = window.center_stage.xml_editor.toPlainText()

    window._doc_ui.discard_changes()

    assert window.statusBar().currentMessage() == "No unsaved changes to discard."
    assert window.center_stage.xml_editor.toPlainText() == editor_before


def test_discard_changes_no_project_path_shows_message(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    assert window._current_project_path is None

    window._doc_ui.discard_changes()

    assert window.statusBar().currentMessage() == "No file is open — nothing to discard."


def test_discard_changes_menu_action_is_gated_on_the_dirty_flag_and_wired(
    qtbot, tmp_path, monkeypatch
):
    """§7/FQ-020: the gate is the DIRTY FLAG, not a `.bak` -- which is what lets
    it ride on `set_dirty` (every keystroke) instead of `stat`-ing a possibly
    sshfs-mounted path on each one."""
    window = _window(qtbot, tmp_path)
    file_menu = find_top_menu(window, "File")
    discard = find_action(file_menu, "Discard Changes")
    assert find_action(file_menu, "Revert") is None
    # No file at all -> nothing to discard.
    assert discard.isEnabled() is False

    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    # A file, but a clean buffer -- and note there is no `.bak` anywhere, which
    # the old gate would have required.
    assert discard.isEnabled() is False
    assert not (tmp_path / "demo.pgtp.bak").exists()

    window.center_stage.xml_editor.setPlainText(_MINIMAL_PGTP)
    assert discard.isEnabled() is True

    monkeypatch.setattr(window._doc_ui, "confirm_discard_changes", lambda: True)
    discard.trigger()
    assert window.statusBar().currentMessage().startswith("Discarded changes in ")
    # ...and having discarded, there is nothing left to discard.
    assert discard.isEnabled() is False


def test_closing_the_project_disables_discard_changes_again(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    window.center_stage.xml_editor.setPlainText(_MINIMAL_PGTP)
    assert window._doc_ui.discard_changes_action.isEnabled() is True

    window._doc_ui.close(confirm="discard")

    assert window._doc_ui.discard_changes_action.isEnabled() is False


def test_discard_changes_still_defends_at_runtime_when_the_buffer_is_clean(
    qtbot, tmp_path
):
    """The enable gate is not the only guard: the toolbar mirrors the action, so a
    pinned button can be clicked between refreshes."""
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    window.center_stage.xml_editor.setPlainText(_MINIMAL_PGTP)
    window._doc_ui.save_project()
    assert window._doc_ui.discard_changes_action.isEnabled() is False

    window._doc_ui.discard_changes(confirm=True)

    assert window.statusBar().currentMessage() == "No unsaved changes to discard."


# -- failed open must not mark dirty (C1 regression) ------------------------


def test_failed_open_does_not_mark_dirty(qtbot, tmp_path):
    from unittest.mock import patch

    window = _window(qtbot, tmp_path)
    # Open a good project first so there is a tracked path to protect.
    good = _make_project(tmp_path, "good.pgtp")
    window.open_project_file(str(good))
    assert window._dirty is False

    bad = tmp_path / "bad.pgtp"
    bad.write_text("<Project><oops>", encoding="utf-8", newline="")
    with patch("pgtp_editor.ui.modals.QMessageBox.critical"):
        window.open_project_file(str(bad))

    # The failed open showed the fallback text but must NOT mark the document
    # dirty, and must leave the tracked project pointing at the good file.
    assert window._dirty is False
    assert window._current_project_path == str(good)
