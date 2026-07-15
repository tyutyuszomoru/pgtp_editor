"""Sub-project C -- SnapshotHistory wired into MainWindow."""
from PySide6.QtGui import QKeySequence

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


def _text(window):
    return window.center_stage.xml_editor.toPlainText()


def test_open_pushes_initial_snapshot(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))

    assert window._history.current_index == 0
    entries = window._history.entries()
    assert len(entries) == 1
    assert "demo.pgtp" in entries[0][1]


def test_edit_then_capture_pushes_snapshot(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))

    window.center_stage.xml_editor.setPlainText("user edit A")
    window._capture_snapshot_now()

    assert window._history.current_index == 1
    assert window._history._texts()[-1] == "user edit A"


def test_identical_capture_does_not_push(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))

    window.center_stage.xml_editor.setPlainText("edit once")
    window._capture_snapshot_now()
    n = len(window._history._texts())
    # Firing again with no further change must not push.
    window._capture_snapshot_now()

    assert len(window._history._texts()) == n


def test_capture_skipped_while_loading(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    before = len(window._history._texts())

    window._loading = True
    try:
        window.center_stage.xml_editor.setPlainText("programmatic load")
        window._capture_snapshot_now()
    finally:
        window._loading = False

    assert len(window._history._texts()) == before


def test_undo_restores_text_without_repushing(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    original = _text(window)

    window.center_stage.xml_editor.setPlainText("edit B")
    window._capture_snapshot_now()
    n_after_edit = len(window._history._texts())

    window._undo()

    assert _text(window) == original
    # undo must NOT create a new snapshot
    assert len(window._history._texts()) == n_after_edit
    # a spurious debounced capture after restore must also not push
    window._capture_snapshot_now()
    assert len(window._history._texts()) == n_after_edit


def test_redo_returns_forward(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))

    window.center_stage.xml_editor.setPlainText("edit C")
    window._capture_snapshot_now()
    edited = _text(window)

    window._undo()
    window._redo()

    assert _text(window) == edited


def test_history_entries_reflects_order_newest_first(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    window.center_stage.xml_editor.setPlainText("second")
    window._capture_snapshot_now()

    entries = window._history_entries()  # newest-first

    assert entries[0][1] == "Edit"
    assert "demo.pgtp" in entries[-1][1]


def test_history_jump_sets_editor_to_snapshot(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    initial = _text(window)
    window.center_stage.xml_editor.setPlainText("changed")
    window._capture_snapshot_now()
    n = len(window._history._texts())

    window._history_jump(0)  # oldest = initial snapshot

    assert _text(window) == initial
    assert len(window._history._texts()) == n  # jump does not push


def test_undo_redo_actions_exist_with_shortcuts(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    edit_menu = find_top_menu(window, "Edit")
    undo = find_action(edit_menu, "Undo")
    redo = find_action(edit_menu, "Redo")
    assert undo is not None
    assert redo is not None
    # Ctrl+Z / Ctrl+Y single-step shortcuts bound somewhere on the window.
    seqs = {s.key().toString() for s in window.findChildren(type(window._undo_shortcut))}
    assert QKeySequence("Ctrl+Z").toString() in seqs
    assert QKeySequence("Ctrl+Y").toString() in seqs
