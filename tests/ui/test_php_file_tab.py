"""Tests for `ui/php_file_tab.py` -- §21 Phase 1 (the "Notepad++ baseline")
plus §22's advisory lint hook."""
from pathlib import Path

import pytest

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


def test_ctrl_s_in_the_editor_is_dead_and_writes_nothing(qtbot, tmp_path):
    """FQ-020: this filter's `Key_S` branch is REMOVED. It was a real per-tab
    save, independent of the deleted `File ▸ Save`, so it would have survived by
    accident and left the PHP tab as the one place in the app where Ctrl+S saves
    -- owner's ruling: *"Dies at all, inconsistency is a bad driver."*

    The event must not be claimed (so nothing else is suppressed either) and
    nothing may be written: no file, no dirty-flag change, no status message.
    Saving a PHP file is `Deployment ▸ Save PHP File`.
    """
    written = []
    tab = PhpFileTab(
        None,
        "x",
        resolve_save_path=lambda: tmp_path / "o.php",
        writer=lambda path, text: written.append(text),
    )
    qtbot.addWidget(tab)
    tab.editor.insertPlainText("y")
    for event_type in (QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride):
        event = QKeyEvent(
            event_type, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier
        )
        assert tab.eventFilter(tab.editor, event) is False
    assert written == []
    assert tab.is_dirty() is True
    assert not (tmp_path / "o.php").exists()


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


def test_ctrl_y_is_stated_here_rather_than_left_to_qts_platform_table(qtbot):
    """BUG-056/DEC-015: `Ctrl+Y` is a Qt `StandardKey.Redo` binding on the
    **Windows** keyboard scheme only, so a surface that leans on Qt's native
    handler redoes on Windows and is a dead key on Linux -- measured in the
    Sandbox SQL Console. This tab states the answer itself, so it is the same on
    both systems. Asserted through the FILTER, never through a native redo: the
    offscreen platform runs the Windows scheme, so the native path would be green
    for the wrong reason."""
    tab = PhpFileTab(None, "x")
    qtbot.addWidget(tab)
    tab.editor.insertPlainText("yz")
    assert (
        tab.eventFilter(
            tab.editor,
            QKeyEvent(
                QEvent.Type.KeyPress, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier
            ),
        )
        is True
    )
    assert tab.text() == "x"

    event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier
    )

    assert tab.eventFilter(tab.editor, event) is True
    assert tab.text() == "yzx"


def test_ctrl_shift_z_is_claimed_here_and_is_not_a_redo(qtbot):
    """DEC-015 freed `Ctrl+Shift+Z` from redo, and this tab must still CLAIM it:
    Qt binds the chord as native Redo under `KB_Win | KB_X11`, so a tab that
    stopped claiming it would keep redoing on both platforms and silently defeat
    the reassignment. Both halves are asserted -- the override is accepted, and
    the key press runs nothing."""
    tab = PhpFileTab(None, "x")
    qtbot.addWidget(tab)
    tab.editor.insertPlainText("yz")
    tab.editor.undo()
    assert tab.text() == "x"
    mods = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier

    override = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_Z, mods)
    assert tab.eventFilter(tab.editor, override) is True
    assert override.isAccepted() is True

    assert (
        tab.eventFilter(tab.editor, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Z, mods))
        is True
    )
    assert tab.text() == "x"  # NOT redone


def test_the_windows_only_alt_backspace_pair_is_suppressed(qtbot):
    """Owner rule: a chord means the same thing on both systems or is not bound
    at all. Qt binds `Alt+Backspace` (Undo) and `Alt+Shift+Backspace` (Redo)
    under `KB_Win` **only**, so leaving them to Qt ships two different keyboards.
    They are suppressed: consumed here, running nothing, on every platform."""
    tab = PhpFileTab(None, "x")
    qtbot.addWidget(tab)
    tab.editor.insertPlainText("yz")
    alt = Qt.KeyboardModifier.AltModifier
    alt_shift = Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier

    for mods in (alt, alt_shift):
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Backspace, mods)
        assert tab.eventFilter(tab.editor, event) is True
        assert tab.text() == "yzx"  # neither undone nor redone


def test_the_x11_only_editing_chords_are_answered_by_this_tab(qtbot):
    """The owner's 2026-08-10 ruling: `Ctrl+Shift+Insert` (paste) and
    `Ctrl+D`/`Ctrl+K`/`Ctrl+U` are implemented by the app on BOTH platforms, at
    all six editing surfaces. Qt binds them on the Linux/KDE scheme only, and the
    offscreen platform runs the **Windows** scheme — so asserting the filter's
    answer is the only way to test them at all, and a native-answer assertion
    would be green for the wrong reason on the one platform the suite can see.

    This tab's buffer is editable, so the answer is the edit itself."""
    ctrl = Qt.KeyboardModifier.ControlModifier

    def press(tab, key, mods=ctrl):
        override = QKeyEvent(QEvent.Type.ShortcutOverride, key, mods)
        assert tab.eventFilter(tab.editor, override) is True
        assert override.isAccepted() is True
        event = QKeyEvent(QEvent.Type.KeyPress, key, mods)
        assert tab.eventFilter(tab.editor, event) is True

    def tab_at(text, position):
        tab = PhpFileTab(None, text)
        qtbot.addWidget(tab)
        cursor = tab.editor.textCursor()
        cursor.setPosition(position)
        tab.editor.setTextCursor(cursor)
        return tab

    deleted_char = tab_at("one\ntwo", 0)
    press(deleted_char, Qt.Key.Key_D)
    assert deleted_char.text() == "ne\ntwo"

    to_eol = tab_at("one\ntwo", 1)
    press(to_eol, Qt.Key.Key_K)
    assert to_eol.text() == "o\ntwo"

    whole_line = tab_at("one\ntwo", 1)
    press(whole_line, Qt.Key.Key_U)
    assert whole_line.text() == "two"

    from PySide6.QtWidgets import QApplication

    QApplication.clipboard().setText("!")
    pasted = tab_at("one\ntwo", 0)
    press(
        pasted,
        Qt.Key.Key_Insert,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    assert pasted.text() == "!one\ntwo"


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


# --- Lint integration (§22) -------------------------------------------------
# The service is injected and `_run_async` is replaced with a synchronous
# stand-in (the project's convention), so no test here spawns `php`, threads,
# or waits on anything.
from pgtp_editor.lint.findings import (  # noqa: E402
    EXTERNAL_TOOLS_SETTINGS_PATH,
    LINT_PREFIX,
    LintOutcome,
    LintStatus,
)
from pgtp_editor.lint.runner import LintProcessResult  # noqa: E402
from pgtp_editor.lint.service import LintService  # noqa: E402

_CLEAN = "No syntax errors detected in /tmp/pgtp_lint_x/buffer.php\n"
_BROKEN = "Parse error: syntax error, unexpected ';' in /tmp/x/buffer.php on line 4\n"


def _sync(tab):
    """Replace the threading seam with a synchronous call."""
    def _run(fn, on_result, on_error=None, **kwargs):
        try:
            value = fn()
        except BaseException as exc:  # noqa: BLE001
            if on_error is not None:
                on_error(exc)
            return None
        on_result(value)
        return None

    tab._run_async = _run
    return tab


def _service(process_result, executable="/usr/bin/php"):
    return LintService(
        executable_provider=lambda: executable,
        runner=lambda exe, text, timeout: process_result,
        resolver=lambda path: path,
    )


def _lint_texts(tab):
    captured = []
    tab.lint_reported.connect(lambda lines: captured.extend(lines))
    tab.request_lint()
    return captured


def test_lint_is_off_and_unwired_by_default(qtbot):
    tab = PhpFileTab(None, "<?php\n")
    qtbot.addWidget(tab)
    assert tab.lint_on_save is False
    assert tab.lint_service is None


def test_request_lint_with_no_service_still_reports_a_lint_line(qtbot):
    """A silent no-op would read as 'the file is clean' (§22)."""
    tab = _sync(PhpFileTab(None, "<?php\n"))
    qtbot.addWidget(tab)
    lines = _lint_texts(tab)
    assert lines
    assert lines[0].text.startswith(LINT_PREFIX)
    # The remedy moved with the setting (FQ-260812025705).
    assert EXTERNAL_TOOLS_SETTINGS_PATH in lines[0].text


def test_clean_lint_reports_ok(qtbot, tmp_path):
    path = _write(tmp_path)
    tab = _sync(PhpFileTab(path, "<?php\n"))
    qtbot.addWidget(tab)
    tab.set_lint_service(_service(LintProcessResult(exit_code=0, stdout=_CLEAN)))
    lines = _lint_texts(tab)
    assert len(lines) == 1
    assert lines[0].text.startswith(LINT_PREFIX + "OK")
    assert "page.php" in lines[0].text  # the tab's name, not the temp path
    assert lines[0].line is None


def test_findings_are_navigable_and_lint_prefixed(qtbot, tmp_path):
    path = _write(tmp_path)
    tab = _sync(PhpFileTab(path, "<?php ;;"))
    qtbot.addWidget(tab)
    tab.set_lint_service(_service(LintProcessResult(exit_code=255, stdout=_BROKEN)))
    lines = _lint_texts(tab)
    navigable = [ln for ln in lines if ln.line is not None]
    assert [ln.line for ln in navigable] == [4]
    assert all(ln.text.startswith(LINT_PREFIX) for ln in lines)
    # The line number the host navigates to must actually work on this editor.
    tab.navigate_to_line(navigable[0].line)


def test_lint_never_emits_the_check_or_sql_prefixes(qtbot, tmp_path):
    """`[Lint]` is PHP-only; `[Check]` is §18.5's and `[SQL]` is §18.4's."""
    path = _write(tmp_path)
    for result in (
        LintProcessResult(exit_code=0, stdout=_CLEAN),
        LintProcessResult(exit_code=255, stdout=_BROKEN),
        LintProcessResult(exit_code=139, stderr="Segmentation fault"),
        LintProcessResult(exit_code=0),
        LintProcessResult(exit_code=None, timed_out=True),
    ):
        tab = _sync(PhpFileTab(path, "<?php\n"))
        qtbot.addWidget(tab)
        tab.set_lint_service(_service(result))
        for line in _lint_texts(tab):
            assert line.text.startswith(LINT_PREFIX)
            assert "[Check]" not in line.text
            assert "[SQL]" not in line.text


def test_lint_runs_on_the_current_buffer_not_the_file_on_disk(qtbot, tmp_path):
    path = _write(tmp_path, text="<?php\n")
    seen = {}

    def _runner(exe, text, timeout):
        seen["text"] = text
        return LintProcessResult(exit_code=0, stdout=_CLEAN)

    service = LintService(
        executable_provider=lambda: "/usr/bin/php",
        runner=_runner,
        resolver=lambda p: p,
    )
    tab = _sync(PhpFileTab(path, "<?php\n"))
    qtbot.addWidget(tab)
    tab.set_lint_service(service)
    tab.editor.insertPlainText("echo 'unsaved';")
    tab.request_lint()
    assert "unsaved" in seen["text"]
    assert "unsaved" not in path.read_text(encoding="utf-8")


def test_an_untitled_tab_lints_under_its_placeholder_name(qtbot):
    tab = _sync(PhpFileTab(None, "<?php ;;"))
    qtbot.addWidget(tab)
    tab.set_lint_service(_service(LintProcessResult(exit_code=255, stdout=_BROKEN)))
    assert any("Untitled" in ln.text for ln in _lint_texts(tab))


# --- Lint on save: advisory, never blocking ---------------------------------
def test_lint_on_save_lints_after_a_successful_save(qtbot, tmp_path):
    path = _write(tmp_path)
    tab = _sync(PhpFileTab(path, "<?php\n"))
    qtbot.addWidget(tab)
    tab.set_lint_service(_service(LintProcessResult(exit_code=0, stdout=_CLEAN)))
    tab.set_lint_on_save(True)
    captured = []
    tab.lint_reported.connect(lambda lines: captured.extend(lines))
    tab.editor.insertPlainText("// x\n")
    assert tab.save() is True
    assert captured and captured[0].text.startswith(LINT_PREFIX + "OK")


def test_lint_on_save_off_by_default_does_not_lint(qtbot, tmp_path):
    path = _write(tmp_path)
    tab = _sync(PhpFileTab(path, "<?php\n"))
    qtbot.addWidget(tab)
    tab.set_lint_service(_service(LintProcessResult(exit_code=0, stdout=_CLEAN)))
    captured = []
    tab.lint_reported.connect(lambda lines: captured.extend(lines))
    tab.editor.insertPlainText("// x\n")
    assert tab.save() is True
    assert captured == []


def test_a_lint_finding_does_not_block_or_undo_the_save(qtbot, tmp_path):
    """§22: advisory only. Broken PHP still saves, and stays saved."""
    path = _write(tmp_path)
    tab = _sync(PhpFileTab(path, "<?php\n"))
    qtbot.addWidget(tab)
    tab.set_lint_service(_service(LintProcessResult(exit_code=255, stdout=_BROKEN)))
    tab.set_lint_on_save(True)
    tab.editor.insertPlainText("<?php ;;")
    assert tab.save() is True
    assert tab.is_dirty() is False
    assert path.read_text(encoding="utf-8") == tab.text()


def test_a_crashing_lint_service_does_not_break_the_save(qtbot, tmp_path):
    class _Exploding:
        def lint_text(self, text, name):
            raise RuntimeError("linter subsystem on fire")

    path = _write(tmp_path)
    tab = _sync(PhpFileTab(path, "<?php\n"))
    qtbot.addWidget(tab)
    tab.set_lint_service(_Exploding())
    tab.set_lint_on_save(True)
    captured = []
    tab.lint_reported.connect(lambda lines: captured.extend(lines))
    tab.editor.insertPlainText("// x\n")
    assert tab.save() is True
    assert tab.is_dirty() is False
    assert path.read_text(encoding="utf-8") == tab.text()
    # ...and the crash is reported, not swallowed into silence.
    assert captured and "could not be started" in captured[0].text


def test_a_timing_out_linter_does_not_block_the_save(qtbot, tmp_path):
    path = _write(tmp_path)
    tab = _sync(PhpFileTab(path, "<?php\n"))
    qtbot.addWidget(tab)
    tab.set_lint_service(_service(LintProcessResult(exit_code=None, timed_out=True)))
    tab.set_lint_on_save(True)
    captured = []
    tab.lint_reported.connect(lambda lines: captured.extend(lines))
    tab.editor.insertPlainText("// x\n")
    assert tab.save() is True
    assert captured and "timed out" in captured[0].text


def test_a_missing_linter_does_not_block_the_save(qtbot, tmp_path):
    path = _write(tmp_path)
    tab = _sync(PhpFileTab(path, "<?php\n"))
    qtbot.addWidget(tab)
    tab.set_lint_service(
        LintService(
            executable_provider=lambda: "/usr/bin/nope",
            runner=lambda *a: pytest.fail("must not run a missing linter"),
            resolver=lambda p: None,
        )
    )
    tab.set_lint_on_save(True)
    captured = []
    tab.lint_reported.connect(lambda lines: captured.extend(lines))
    tab.editor.insertPlainText("// x\n")
    assert tab.save() is True
    assert captured and "missing or not" in captured[0].text


def test_a_failed_save_does_not_lint(qtbot, tmp_path):
    """Nothing was written, so there is nothing to report on."""
    def _boom(path, text):
        raise OSError("read-only filesystem")

    tab = _sync(PhpFileTab(tmp_path / "page.php", "<?php\n", writer=_boom))
    qtbot.addWidget(tab)
    tab.set_lint_service(_service(LintProcessResult(exit_code=0, stdout=_CLEAN)))
    tab.set_lint_on_save(True)
    captured = []
    tab.lint_reported.connect(lambda lines: captured.extend(lines))
    tab.editor.insertPlainText("// x\n")
    assert tab.save() is False
    assert captured == []


def test_a_broken_threading_seam_still_reports(qtbot, tmp_path):
    path = _write(tmp_path)
    tab = PhpFileTab(path, "<?php\n")
    qtbot.addWidget(tab)
    tab.set_lint_service(_service(LintProcessResult(exit_code=0, stdout=_CLEAN)))

    def _explode(*args, **kwargs):
        raise RuntimeError("no threadpool")

    tab._run_async = _explode
    captured = []
    tab.lint_reported.connect(lambda lines: captured.extend(lines))
    assert tab.request_lint() is False
    assert captured and "could not be started" in captured[0].text


def test_a_service_returning_junk_is_reported_not_dropped(qtbot, tmp_path):
    class _Junk:
        def lint_text(self, text, name):
            return "not an outcome"

    tab = _sync(PhpFileTab(_write(tmp_path), "<?php\n"))
    qtbot.addWidget(tab)
    tab.set_lint_service(_Junk())
    lines = _lint_texts(tab)
    assert lines and lines[0].text.startswith(LINT_PREFIX)


def test_lint_runs_off_the_gui_thread_via_the_run_async_seam(qtbot, tmp_path):
    """The seam must actually be used -- a direct call would freeze the window
    for the whole `php -l` timeout on a slow filesystem."""
    tab = PhpFileTab(_write(tmp_path), "<?php\n")
    qtbot.addWidget(tab)
    tab.set_lint_service(_service(LintProcessResult(exit_code=0, stdout=_CLEAN)))
    used = []
    tab._run_async = lambda fn, on_result, on_error=None, **kw: used.append(fn)
    tab.request_lint()
    assert len(used) == 1
    # Nothing was reported yet: the work has not been executed.
    assert callable(used[0])


def test_outcome_construction_is_importable_for_hosts():
    outcome = LintOutcome(status=LintStatus.CLEAN, display_name="x.php")
    assert outcome.ok is True
