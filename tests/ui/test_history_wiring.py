"""Sub-project C -- SnapshotHistory wired into MainWindow."""
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

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
    window.center_stage.xml_editor.setPlainText("third")
    window._capture_snapshot_now()

    entries = window._history_entries()  # newest-first, edits only

    # Two edits, newest first; the "Opened" baseline is NOT listed.
    assert [label for _i, label in entries] == ["Edit", "Edit"]
    assert not any("demo.pgtp" in label for _i, label in entries)


def test_open_baseline_is_not_an_undo_item(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    # Right after opening: nothing to undo, and the jump list is empty
    # (the "Opened" baseline is the floor, not an item).
    assert window._history_entries() == []
    assert window._history.can_undo() is False
    # But the baseline still exists internally as the undo floor.
    assert window._history.entries() == [(0, "Opened demo.pgtp")]


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


def test_ctrl_shift_z_in_editor_does_not_redo_anything(qtbot, tmp_path):
    """DEC-015: *"Redo is always, on all systems Ctrl+Y"*, so Ctrl+Shift+Z is no
    longer a second redo chord anywhere — and this is the case that proves it,
    because `XmlEditor` must keep INTERCEPTING the chord to make it true. Qt
    binds Ctrl+Shift+Z to `StandardKey.Redo` under `KB_Win | KB_X11`, so simply
    deleting the old redo branch would have left the editor's own native redo
    firing (a char-level one, at that). It is claimed and answers nothing until
    FQ-034's shrink-selection lands."""
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
    reverted = _text(window)

    QTest.keyClick(
        editor,
        Qt.Key.Key_Z,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )

    assert window._history.current_index == 0
    assert _text(window) == reverted

    # The operation the chord lost is still one keystroke away, by its one
    # spelling.
    QTest.keyClick(editor, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)

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

    with patch("pgtp_editor.ui.modals.QMessageBox.critical"):
        window.open_project_file(str(path))

    entries = window._history.entries()
    assert len(entries) == 1
    assert window._history.current_index == 0
    assert "broken.pgtp" in entries[0][1]
    assert window._history._texts()[0] == _text(window)


# -- M2: Discard Changes seeds a snapshot (FQ-020: was Revert) ---------------


def test_discard_changes_seeds_snapshot(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    window.center_stage.xml_editor.setPlainText("something else entirely")
    window._capture_snapshot_now()
    n_before = len(window._history._texts())

    window._doc_ui.discard_changes(confirm=True)

    # A discard pushes exactly one snapshot whose text is the shown (reloaded)
    # buffer, and it becomes the current head -- the same contract `revert` had,
    # only the source is the file on disk rather than a `.bak`.
    assert len(window._history._texts()) == n_before + 1
    assert window._history.current_index == len(window._history._texts()) - 1
    assert window._history._texts()[-1] == _text(window)
    assert "Discarded changes" in window._history.entries()[-1][1]


def test_undo_redo_actions_exist_with_shortcuts(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    # On the Editor menu bar's History menu since FQ-016 (was Edit), and named
    # for their PROJECT scope since BUG-064 -- they are not the menu twin of
    # Ctrl+Z, they are a different command.
    history_menu = find_top_menu(window, "History")
    undo = find_action(history_menu, "Undo Project Edit")
    redo = find_action(history_menu, "Redo Project Edit")
    assert undo is not None
    assert redo is not None
    # Ctrl+Z / Ctrl+Y single-step shortcuts bound somewhere on the window.
    seqs = {s.key().toString() for s in window.findChildren(type(window._undo_shortcut))}
    assert QKeySequence("Ctrl+Z").toString() in seqs
    assert QKeySequence("Ctrl+Y").toString() in seqs


def test_the_two_commands_named_undo_are_kept_apart(qtbot, tmp_path):
    """BUG-064: the menu entries and the chord are TWO commands, and the fix was
    to say so rather than to merge them (merging would reverse §18.5 carve-out 1
    and re-open BUG-048).

    Three assertions, one per half of the shape: the menu actions carry no chord
    at all, their labels state the project scope, and `Ctrl+Z` still works — via
    the tab-scoped slot, which is a different callable from the menu's."""
    window = _window(qtbot, tmp_path)
    history_menu = find_top_menu(window, "History")
    undo = find_action(history_menu, "Undo Project Edit")
    redo = find_action(history_menu, "Redo Project Edit")

    assert undo.shortcut().isEmpty()
    assert redo.shortcut().isEmpty()
    # Neither is labelled the same as the operation the chord performs.
    assert find_action(history_menu, "Undo") is None
    assert find_action(history_menu, "Redo") is None
    # The menu click is the UNSCOPED command; the keystroke path is the scoped
    # one. Two distinct callables, deliberately.
    assert undo is window._undo_action
    assert window._undo != window._undo_raw_xml_history


def _make_project_named(tmp_path, name, table):
    path = tmp_path / name
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<Project fileName="{name}">\n'
        f'  <Page fileName="p1" tableName="{table}" caption="C"/>\n'
        "</Project>\n",
        encoding="utf-8",
        newline="",
    )
    return path


def test_opening_second_project_resets_history(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    a = _make_project_named(tmp_path, "a.pgtp", "t.aaa")
    b = _make_project_named(tmp_path, "b.pgtp", "t.bbb")
    window.open_project_file(str(a))
    window.open_project_file(str(b))
    # History holds only project B's seed -- undo cannot cross into A.
    assert window._history.can_undo() is False
    assert [label for _i, label in window._history.entries()] == ["Opened b.pgtp"]
    assert "t.aaa" not in window.center_stage.xml_editor.toPlainText()


def test_close_project_clears_history(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    window._doc_ui.close(confirm="discard")
    assert window._history.entries() == []
    assert window._history.can_undo() is False


def test_history_menu_undo_and_redo_step_distinctly(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    window.center_stage.xml_editor.setPlainText("edit one")
    window._capture_snapshot_now()
    history_menu = find_top_menu(window, "History")

    # History ▸ Undo Project Edit steps back to the opened text.
    find_action(history_menu, "Undo Project Edit").trigger()
    assert window.center_stage.xml_editor.toPlainText() != "edit one"
    # History ▸ Redo Project Edit steps forward again.
    find_action(history_menu, "Redo Project Edit").trigger()
    assert window.center_stage.xml_editor.toPlainText() == "edit one"
    # History… exists as the combined navigator (opens non-modally).
    assert find_action(history_menu, "History…") is not None


# -- BUG-048: the project history writes only where it may -------------------
#
# `Ctrl+Z` used to revert the **Raw XML project buffer** from tabs that show a
# different document, and through FQ-021's read-only Compare/Merge lock. Two
# independent causes: a read-only `QPlainTextEdit` does not claim the
# `ShortcutOverride` for undo/redo, so the window-level `QShortcut` fired; and
# `_apply_history_text` writes with `setPlainText`, which `setReadOnly` never
# gates. Both are closed, and both are asserted below.
#
# Delivery matters: `QTest.keyClick(widget, …)` posts straight at the widget and
# never reaches Qt's shortcut map, so it CANNOT observe this bug. The key goes to
# `window.windowHandle()` on a `show()`n window — which is what a real key press
# does, and it works fine under the offscreen platform.


def _armed_history_window(qtbot, tmp_path):
    """A shown window whose Raw XML history has something to undo."""
    window = _window(qtbot, tmp_path)
    path = _make_project(tmp_path)
    window.open_project_file(str(path))
    window.center_stage.xml_editor.setPlainText("edit one")
    window._capture_snapshot_now()
    window.show()
    QApplication.processEvents()
    assert window.windowHandle() is not None
    assert window._history.can_undo()
    return window


def _press_ctrl_z(window):
    QApplication.processEvents()
    QTest.keyClick(window.windowHandle(), Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()


def test_ctrl_z_on_the_ddl_explorer_tab_never_touches_the_raw_xml_buffer(
    qtbot, tmp_path
):
    """§18.5 carve-out 1's hazard at the sibling site nobody filtered: the DDL
    Explorer's buffer is read-only, so the window shortcut used to fire here and
    revert a document the user is not even looking at."""
    window = _armed_history_window(qtbot, tmp_path)
    before = _text(window)
    stage = window.center_stage
    index = stage.ddl_explorer_tab_index()
    stage.setTabVisible(index, True)
    stage.setCurrentIndex(index)
    assert stage.currentIndex() == index
    panel = stage.ddl_explorer_panel()
    panel.editor.setPlainText("CREATE FUNCTION pr.f() ...")
    panel.editor.setFocus()

    _press_ctrl_z(window)

    assert _text(window) == before  # byte-identical
    assert window._history.current_index == 1


def test_ctrl_z_on_the_sandbox_sql_console_never_touches_the_raw_xml_buffer(
    qtbot, tmp_path
):
    """The same unscoped path from the other sandbox tab — reached whenever
    focus is on anything in the console that is not the editor itself."""
    window = _armed_history_window(qtbot, tmp_path)
    before = _text(window)
    panel = window.center_stage.open_sandbox_sql_tab()
    panel.results.setFocus()

    _press_ctrl_z(window)

    assert _text(window) == before
    assert window._history.current_index == 1


def test_ctrl_z_does_not_walk_through_the_compare_merge_read_only_lock(
    qtbot, tmp_path
):
    """FQ-021 holds Raw XML read-only for the whole of Compare/Merge as a
    DATA-LOSS guard. A read-only editor does not claim the ShortcutOverride, so
    Ctrl+Z walked straight through the lock and rewrote the buffer mid-merge."""
    window = _armed_history_window(qtbot, tmp_path)
    before = _text(window)
    stage = window.center_stage
    stage.enter_diff_merge_mode()
    stage.setCurrentIndex(stage.raw_xml_tab_index)
    stage.xml_editor.setFocus()
    assert stage.xml_editor.isReadOnly()

    _press_ctrl_z(window)

    assert _text(window) == before
    assert window._history.current_index == 1


def test_the_history_menu_also_refuses_a_locked_raw_xml_buffer(qtbot, tmp_path):
    """The lock is not a view state, so the explicit menu click is refused too —
    with a stated reason, never silently. (The TAB scope is different: History ▸
    Undo from another tab is a deliberate "undo the project" and still works.)"""
    window = _armed_history_window(qtbot, tmp_path)
    before = _text(window)
    window.center_stage.enter_diff_merge_mode()
    history_menu = find_top_menu(window, "History")

    find_action(history_menu, "Undo Project Edit").trigger()

    assert _text(window) == before
    assert "compare/merge mode" in window.statusBar().currentMessage()


def test_every_keystroke_path_into_the_history_is_tab_scoped(qtbot, tmp_path):
    """BUG-064 part (C): `Ctrl+Z` had TWO entry points with different guards.

    The window `QShortcut` reached the tab-scoped slot, but the Raw XML editor's
    `undo_requested` re-emission reached the UNSCOPED `_undo`. They were
    equivalent only because `QStackedWidget` hides the departed page and Qt
    clears focus from a hidden widget — an invariant nothing stated or tested,
    and one that dies the day an `XmlEditor` is hosted in a dock beside another
    tab. This pins it: the editor's signal lands on the scoped slot.
    """
    window = _armed_history_window(qtbot, tmp_path)
    calls = []
    window._undo_raw_xml_history = lambda: calls.append("scoped")

    window.center_stage.xml_editor.undo_requested.emit()

    assert calls == ["scoped"]


def test_a_real_ctrl_z_in_the_raw_xml_editor_still_undoes(qtbot, tmp_path):
    """The other half of part (C): re-pointing the signal must not cost the
    keystroke its behaviour. A real key press, delivered the way BUG-048's block
    delivers them."""
    window = _armed_history_window(qtbot, tmp_path)
    stage = window.center_stage
    stage.setCurrentIndex(stage.raw_xml_tab_index)
    stage.xml_editor.setFocus()
    assert window._history.current_index == 1

    _press_ctrl_z(window)

    assert window._history.current_index == 0


def test_the_menu_command_still_undoes_from_another_tab(qtbot, tmp_path):
    """The unscoped meaning survives, which is the thing a careless part-(C)
    change would silently delete: a CLICK means "undo the project", wherever the
    user is (§18.5 carve-out 1). Only keystrokes are tab-scoped."""
    window = _armed_history_window(qtbot, tmp_path)
    stage = window.center_stage
    index = stage.ddl_explorer_tab_index()
    stage.setTabVisible(index, True)
    stage.setCurrentIndex(index)
    assert window._history.current_index == 1
    history_menu = find_top_menu(window, "History")

    find_action(history_menu, "Undo Project Edit").trigger()

    assert window._history.current_index == 0


def test_apply_history_text_refuses_a_read_only_buffer_on_its_own(qtbot, tmp_path):
    """BUG-048's SECOND independent cause, closed at its own level: `setPlainText`
    is a QTextCursor-level write that `setReadOnly(True)` does not gate, so the
    last-ditch check lives here — no caller can write a locked buffer even by
    calling this directly."""
    window = _armed_history_window(qtbot, tmp_path)
    window.center_stage.enter_diff_merge_mode()
    before = _text(window)

    window._apply_history_text("something else entirely")

    assert _text(window) == before


def test_ctrl_z_still_undoes_on_a_writable_raw_xml_tab(qtbot, tmp_path):
    """The positive half — the scope guard must not turn Ctrl+Z into a dead key
    where it belongs."""
    window = _armed_history_window(qtbot, tmp_path)
    stage = window.center_stage
    stage.setCurrentIndex(stage.raw_xml_tab_index)
    # Focus something that is NOT the editor, so the WINDOW shortcut is the path
    # under test rather than the editor's own key handling.
    window._undo_shortcut.activated.emit()

    assert _text(window) != "edit one"
    assert window._history.current_index == 0


def test_a_drafts_ctrl_z_never_reaches_the_raw_xml_buffer(qtbot, tmp_path):
    """The negative half of BUG-049: a draft tab's undo is its own editor's, so
    wiring it can never regress into BUG-048's wrong-document mutation."""
    window = _armed_history_window(qtbot, tmp_path)
    before = _text(window)
    tab = window.center_stage.open_draft_fragment_tab("page", "customers", "<Page/>")
    tab.editor.setFocus()
    tab.editor.insertPlainText("<Extra/>")

    _press_ctrl_z(window)

    assert _text(window) == before
    assert window._history.current_index == 1
