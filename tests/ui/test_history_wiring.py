"""Sub-project C -- SnapshotHistory wired into MainWindow."""
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtTest import QTest

from tests.ui._menu_helpers import find_action, find_top_menu

from pgtp_editor.ui.main_window import MainWindow

_MINIMAL_PGTP = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Project fileName="demo">\n'
    '  <Page fileName="p1" tableName="pr.equipment" caption="Equipment"/>\n'
    "</Project>\n"
)

_MALFORMED_PGTP = (
    "<Project><Presentation><Pages><Page></Pages></Presentation></Project>"
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


# -- C1: Ctrl+Z/Ctrl+Y route through the editor (not native char undo) ------


def test_ctrl_z_in_editor_triggers_snapshot_undo(qtbot, tmp_path):
    """With the editor focused, a real Ctrl+Z key must run the SNAPSHOT undo
    (restore the previous snapshot), not the editor's native one-char undo."""
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    original = _text(window)

    window.show()
    editor = window.center_stage.xml_editor
    editor.setFocus()
    editor.setPlainText("edited body text")
    window._capture_snapshot_now()
    assert window._history.current_index == 1

    QTest.keyClick(editor, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)

    # Snapshot undo moved the cursor back to the initial snapshot and restored
    # the whole previous text -- not merely a one-character native undo.
    assert window._history.current_index == 0
    assert _text(window) == original


def test_ctrl_y_in_editor_triggers_snapshot_redo(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))

    window.show()
    editor = window.center_stage.xml_editor
    editor.setFocus()
    editor.setPlainText("edited body text")
    window._capture_snapshot_now()
    edited = _text(window)
    window._undo()
    assert window._history.current_index == 0

    QTest.keyClick(editor, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)

    assert window._history.current_index == 1
    assert _text(window) == edited


def test_ctrl_shift_z_in_editor_triggers_snapshot_redo(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))

    window.show()
    editor = window.center_stage.xml_editor
    editor.setFocus()
    editor.setPlainText("edited body text")
    window._capture_snapshot_now()
    edited = _text(window)
    window._undo()
    assert window._history.current_index == 0

    QTest.keyClick(
        editor,
        Qt.Key.Key_Z,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )

    assert window._history.current_index == 1
    assert _text(window) == edited


def test_ctrl_z_in_editor_fires_undo_exactly_once(qtbot, tmp_path):
    """The window QShortcut and the editor's keyPressEvent both target _undo;
    a single Ctrl+Z with the editor focused must not double-fire (the focused
    editor consumes the key, so the window shortcut doesn't also run)."""
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))

    window.show()
    editor = window.center_stage.xml_editor
    editor.setFocus()
    # Build a history with three entries so a double-undo would be observable
    # (index would drop by 2 instead of 1).
    editor.setPlainText("edit one")
    window._capture_snapshot_now()
    editor.setPlainText("edit two")
    window._capture_snapshot_now()
    assert window._history.current_index == 2

    # Spy on the shared restore path (_apply_history_text is hit once per undo
    # step). A double-fire from the coexisting window QShortcut would call it
    # twice and move the index by two.
    calls = []
    original_apply = window._apply_history_text

    def _counting_apply(text):
        calls.append(text)
        original_apply(text)

    window._apply_history_text = _counting_apply

    QTest.keyClick(editor, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)

    assert len(calls) == 1
    assert window._history.current_index == 1


def test_editor_undo_signal_wired_to_undo(qtbot, tmp_path):
    """Mechanism-level guard independent of key delivery: emitting the editor's
    undo_requested / redo_requested drives the snapshot undo/redo."""
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    original = _text(window)
    editor = window.center_stage.xml_editor
    editor.setPlainText("edited")
    window._capture_snapshot_now()
    edited = _text(window)

    editor.undo_requested.emit()
    assert _text(window) == original

    editor.redo_requested.emit()
    assert _text(window) == edited


# -- M1: parse-failure fallback seeds a snapshot ----------------------------


def test_parse_failure_seeds_single_snapshot(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = tmp_path / "broken.pgtp"
    path.write_text(_MALFORMED_PGTP, encoding="utf-8", newline="")

    with patch("pgtp_editor.ui.main_window.QMessageBox.critical"):
        window.open_project_file(str(path))

    entries = window._history.entries()
    assert len(entries) == 1
    assert window._history.current_index == 0
    assert "broken.pgtp" in entries[0][1]
    assert window._history._texts()[0] == _text(window)


# -- M2: revert seeds a snapshot --------------------------------------------


def test_revert_seeds_snapshot(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    # Create a .bak by saving over the file (pre-save content becomes .bak).
    window.center_stage.xml_editor.setPlainText(_MINIMAL_PGTP)
    window._save_project()
    assert (tmp_path / "demo.pgtp.bak").exists()
    window.center_stage.xml_editor.setPlainText("something else entirely")
    window._capture_snapshot_now()
    n_before = len(window._history._texts())

    window._revert_project()

    # A revert pushes exactly one snapshot whose text is the shown (reverted)
    # buffer, and it becomes the current head.
    assert len(window._history._texts()) == n_before + 1
    assert window._history.current_index == len(window._history._texts()) - 1
    assert window._history._texts()[-1] == _text(window)
    assert "Reverted" in window._history.entries()[-1][1]


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
