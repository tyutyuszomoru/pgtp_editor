"""Tests for `ui/php_file_tab.py` -- §21 Phase 1, the "Notepad++ baseline"."""
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent

from pgtp_editor.ui.center_stage import CenterStage
from pgtp_editor.ui.code_editor import CodeEditor
from pgtp_editor.ui.find_replace_bar import FindReplaceBar
from pgtp_editor.ui.php_file_tab import PhpFileTab, php_tab_key


def _write(tmp_path, name="page.php", text="<?php echo 'hi';\n"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# --- The tab widget itself --------------------------------------------------
def test_tab_hosts_the_existing_code_editor_in_php_mode(qtbot):
    tab = PhpFileTab(None, "<?php\n")
    qtbot.addWidget(tab)
    # Reuse, not a new editor widget (§21).
    assert isinstance(tab.editor, CodeEditor)
    assert tab.editor._language == "php"
    assert tab.editor._highlighter._language == "php"
    assert tab.editor.isReadOnly() is False


def test_tab_has_its_own_find_replace_bar(qtbot):
    tab = PhpFileTab(None, "x")
    qtbot.addWidget(tab)
    assert isinstance(tab.find_replace_bar, FindReplaceBar)
    assert tab.find_replace_bar.parent() is tab


def test_open_loads_text_without_marking_dirty(qtbot, tmp_path):
    path = _write(tmp_path)
    tab = PhpFileTab(path, path.read_text(encoding="utf-8"))
    qtbot.addWidget(tab)
    assert tab.text() == "<?php echo 'hi';\n"
    assert tab.is_dirty() is False
    assert tab.tab_title() == "page.php"
    assert tab.tab_tooltip() == str(path)


def test_editing_marks_dirty_and_emits_the_transition_once(qtbot):
    tab = PhpFileTab(None, "a")
    qtbot.addWidget(tab)
    seen = []
    tab.dirty_changed.connect(seen.append)
    tab.editor.insertPlainText("bcd")
    assert tab.is_dirty() is True
    assert seen == [True]  # transition only, not per keystroke
    tab.mark_clean()
    assert seen == [True, False]


def test_dirty_tab_title_carries_the_star(qtbot, tmp_path):
    path = _write(tmp_path)
    tab = PhpFileTab(path, "x")
    qtbot.addWidget(tab)
    tab.editor.insertPlainText("y")
    assert tab.tab_title() == "page.php *"


def test_untitled_tab_when_opened_from_text_only(qtbot):
    tab = PhpFileTab(None, "x")
    qtbot.addWidget(tab)
    assert tab.tab_title() == "Untitled"
    assert tab.path is None
    assert tab.key is None


def test_php_tab_key_normalizes_to_the_resolved_absolute_path(tmp_path):
    path = _write(tmp_path)
    assert php_tab_key(path) == str(path.resolve())
    assert php_tab_key(tmp_path / "sub" / ".." / "page.php") == php_tab_key(path)


# --- The save seam ----------------------------------------------------------
def test_save_writes_through_the_injected_writer_and_resolver(qtbot, tmp_path):
    target = tmp_path / "out.php"
    written = []
    tab = PhpFileTab(
        None,
        "<?php\n",
        resolve_save_path=lambda: target,
        writer=lambda path, text: written.append((path, text)),
    )
    qtbot.addWidget(tab)
    tab.editor.insertPlainText("echo 1;")
    saved = []
    tab.saved.connect(saved.append)

    assert tab.save() is True
    assert written == [(target, tab.text())]
    assert saved == [str(target)]
    assert tab.is_dirty() is False
    # Save As… adopted the path: the tab renamed itself.
    assert tab.path == target
    assert tab.tab_title() == "out.php"
    # No file was touched behind the caller's back.
    assert not target.exists()


def test_save_defaults_to_the_path_the_file_was_opened_from(qtbot, tmp_path):
    path = _write(tmp_path)
    tab = PhpFileTab(path, path.read_text(encoding="utf-8"))
    qtbot.addWidget(tab)
    tab.editor.insertPlainText("// edited\n")
    assert tab.save() is True
    assert path.read_text(encoding="utf-8") == tab.text()
    assert tab.is_dirty() is False


def test_save_returns_false_and_stays_dirty_when_the_resolver_cancels(qtbot):
    tab = PhpFileTab(None, "x", resolve_save_path=lambda: None)
    qtbot.addWidget(tab)
    tab.editor.insertPlainText("y")
    assert tab.save() is False
    assert tab.is_dirty() is True


def test_save_reports_oserror_instead_of_raising_or_marking_clean(qtbot, tmp_path):
    def boom(path, text):
        raise OSError("disk on fire")

    tab = PhpFileTab(None, "x", resolve_save_path=lambda: tmp_path / "o.php", writer=boom)
    qtbot.addWidget(tab)
    tab.editor.insertPlainText("y")
    failures = []
    tab.save_failed.connect(failures.append)
    assert tab.save() is False
    assert failures == ["disk on fire"]
    assert tab.is_dirty() is True


def test_ctrl_s_in_the_editor_saves_this_tab(qtbot, tmp_path):
    written = []
    tab = PhpFileTab(
        None,
        "x",
        resolve_save_path=lambda: tmp_path / "o.php",
        writer=lambda path, text: written.append(text),
    )
    qtbot.addWidget(tab)
    tab.editor.insertPlainText("y")
    event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier
    )
    assert tab.eventFilter(tab.editor, event) is True
    assert written == [tab.text()]
    assert tab.is_dirty() is False


def test_ctrl_z_is_claimed_so_the_window_level_shortcut_never_fires(qtbot):
    tab = PhpFileTab(None, "x")
    qtbot.addWidget(tab)
    override = QKeyEvent(
        QEvent.Type.ShortcutOverride, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier
    )
    assert tab.eventFilter(tab.editor, override) is True
    assert override.isAccepted() is True


def test_ctrl_z_undoes_this_tabs_own_stack(qtbot):
    tab = PhpFileTab(None, "x")
    qtbot.addWidget(tab)
    tab.editor.insertPlainText("yz")
    event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier
    )
    assert tab.eventFilter(tab.editor, event) is True
    assert tab.text() == "x"


def test_navigate_to_line_delegates_to_the_code_editor(qtbot):
    tab = PhpFileTab(None, "a\nb\nc\n")
    qtbot.addWidget(tab)
    tab.navigate_to_line(3)
    assert tab.editor.textCursor().blockNumber() == 2


def test_folding_is_inert_for_php_until_a_host_installs_regions(qtbot):
    """§21 follow-up #1, not a bug: the fold machinery exists but no host
    computes PHP regions yet."""
    tab = PhpFileTab(None, "<?php function f() {\n  return 1;\n}\n")
    qtbot.addWidget(tab)
    assert tab.editor._fold_regions == {}


# --- CenterStage hosting ----------------------------------------------------
def test_open_php_file_tab_appends_after_the_fixed_set(qtbot, tmp_path):
    stage = CenterStage()
    qtbot.addWidget(stage)
    fixed = stage.count()
    path = _write(tmp_path)
    tab = stage.open_php_file_tab(path, path.read_text(encoding="utf-8"))
    assert isinstance(tab, PhpFileTab)
    assert stage.count() == fixed + 1
    assert stage.indexOf(tab) == fixed
    assert stage.currentWidget() is tab
    assert stage.tabText(fixed) == "page.php"
    assert stage.tabToolTip(fixed) == str(path)
    assert stage.php_file_tab(php_tab_key(path)) is tab


def test_opening_the_same_path_twice_focuses_the_one_tab(qtbot, tmp_path):
    stage = CenterStage()
    qtbot.addWidget(stage)
    fixed = stage.count()
    path = _write(tmp_path)
    first = stage.open_php_file_tab(path, "one")
    stage.setCurrentIndex(stage.raw_xml_tab_index)
    again = stage.open_php_file_tab(tmp_path / "sub" / ".." / "page.php", "two")
    assert again is first
    assert stage.count() == fixed + 1
    assert stage.currentWidget() is first
    assert first.text() == "one"  # not reloaded over the user's buffer


def test_multiple_files_open_concurrently_as_ordinary_tabs(qtbot, tmp_path):
    stage = CenterStage()
    qtbot.addWidget(stage)
    fixed = stage.count()
    a = stage.open_php_file_tab(_write(tmp_path, "a.php"), "a")
    b = stage.open_php_file_tab(_write(tmp_path, "b.php"), "b")
    assert stage.count() == fixed + 2
    assert a is not b
    assert set(stage.php_file_tabs().values()) == {a, b}
    assert stage.active_php_file_tab() is b


def test_php_tabs_are_closable_and_route_through_the_host_prompt(qtbot, tmp_path):
    stage = CenterStage()
    qtbot.addWidget(stage)
    path = _write(tmp_path)
    tab = stage.open_php_file_tab(path, "x")
    requested = []
    stage.php_file_close_requested.connect(requested.append)
    stage.tabCloseRequested.emit(stage.indexOf(tab))
    # Signals intent -- the tab is still open until the host resolves it.
    assert requested == [php_tab_key(path)]
    assert stage.php_file_tab(php_tab_key(path)) is tab


def test_close_php_file_tab_removes_it(qtbot, tmp_path):
    stage = CenterStage()
    qtbot.addWidget(stage)
    fixed = stage.count()
    path = _write(tmp_path)
    stage.open_php_file_tab(path, "x")
    stage.close_php_file_tab(php_tab_key(path))
    assert stage.count() == fixed
    assert stage.php_file_tab(php_tab_key(path)) is None
    assert stage.php_file_tabs() == {}
    # Closing then reopening works and does not resurrect a stale key.
    reopened = stage.open_php_file_tab(path, "y")
    assert stage.php_file_tab(php_tab_key(path)) is reopened


def test_update_php_file_tab_refreshes_the_dirty_marker(qtbot, tmp_path):
    stage = CenterStage()
    qtbot.addWidget(stage)
    path = _write(tmp_path)
    key = php_tab_key(path)
    tab = stage.open_php_file_tab(path, "x")
    tab.editor.insertPlainText("y")
    stage.update_php_file_tab(key)
    assert stage.tabText(stage.indexOf(tab)) == "page.php *"
    tab.mark_clean()
    stage.update_php_file_tab(key)
    assert stage.tabText(stage.indexOf(tab)) == "page.php"


def test_php_file_tab_key_round_trips_from_the_widget(qtbot, tmp_path):
    stage = CenterStage()
    qtbot.addWidget(stage)
    path = _write(tmp_path)
    tab = stage.open_php_file_tab(path, "x")
    assert stage.php_file_tab_key(tab) == php_tab_key(path)
    assert stage.php_file_tab_key(PhpFileTab(None, "")) is None


def test_text_only_tabs_get_distinct_minted_keys(qtbot):
    stage = CenterStage()
    qtbot.addWidget(stage)
    first = stage.open_php_file_tab(None, "a")
    second = stage.open_php_file_tab(None, "b")
    keys = stage.php_file_tabs()
    assert len(keys) == 2
    assert stage.php_file_tab_key(first) != stage.php_file_tab_key(second)


# --- Independence from the project document (§21) ---------------------------
def test_dirtying_a_php_tab_does_not_mark_the_project_document_dirty(qtbot, tmp_path):
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.xml_editor.setPlainText("<project/>")
    stage.xml_editor.document().setModified(False)
    tab = stage.open_php_file_tab(_write(tmp_path), "x")
    tab.editor.insertPlainText("edited")
    assert tab.is_dirty() is True
    assert stage.xml_editor.document().isModified() is False
    # ...and the reverse: a dirty project buffer does not dirty the PHP tab.
    stage.xml_editor.insertPlainText("<!-- -->")
    tab.mark_clean()
    assert stage.xml_editor.document().isModified() is True
    assert tab.is_dirty() is False


def test_undo_stacks_are_independent(qtbot, tmp_path):
    stage = CenterStage()
    qtbot.addWidget(stage)
    stage.xml_editor.setPlainText("<project/>")
    tab = stage.open_php_file_tab(_write(tmp_path), "<?php\n")
    tab.editor.insertPlainText("echo 1;")
    tab.editor.undo()
    assert tab.text() == "<?php\n"
    assert stage.xml_editor.toPlainText() == "<project/>"
    stage.xml_editor.insertPlainText("<!-- x -->")
    stage.xml_editor.undo()
    assert tab.text() == "<?php\n"


def test_php_tabs_open_with_no_project_loaded(qtbot, tmp_path):
    """No structural tie to a `.pgtp` project (§21) -- a bare CenterStage with
    an empty project buffer opens files just the same."""
    stage = CenterStage()
    qtbot.addWidget(stage)
    assert stage.xml_editor.toPlainText() == ""
    tab = stage.open_php_file_tab(_write(tmp_path), "<?php\n")
    assert stage.currentWidget() is tab
    assert stage.xml_editor.toPlainText() == ""


def test_save_defaults_to_the_opened_path_via_the_stage(qtbot, tmp_path):
    stage = CenterStage()
    qtbot.addWidget(stage)
    path = _write(tmp_path)
    tab = stage.open_php_file_tab(path, path.read_text(encoding="utf-8"))
    tab.editor.insertPlainText("// note\n")
    assert tab.save() is True
    assert Path(path).read_text(encoding="utf-8") == tab.text()
