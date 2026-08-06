# PGTP Editor — companion editor for SQL Maestro PostgreSQL PHP Generator .pgtp files
# Copyright (C) 2026  Botond Zalai-Ruzsics
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""`ui/php_tab_controller.py` — the §21 entry points that were missing.

Everything here runs **headless**: the controller takes a `UiShell` built from a
bare `QWidget` (dialog parent), a real `CenterStage` and a real `QListWidget`,
never a `MainWindow`. Every modal is behind an injected seam (`confirm_close`,
`choose_open_paths`) or a patched `pgtp_editor.ui.modals` attribute, and no test
here touches a `php` process — this lane never spawns one.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QSettings, QUrl
from PySide6.QtWidgets import QListWidget, QWidget

from pgtp_editor.ui import modals
from pgtp_editor.ui.center_stage import CenterStage
from pgtp_editor.ui.php_file_tab import PhpFileTab, php_tab_key
from pgtp_editor.ui.php_tab_controller import (
    PhpTabController,
    looks_like_text,
    read_php_text,
)
from pgtp_editor.ui.ui_shell import UiShell


def _sync_run(fn, on_result=None, on_error=None, **kwargs):
    try:
        result = fn(**kwargs)
    except BaseException as exc:  # noqa: BLE001 -- mirrors run_async's contract
        if on_error is not None:
            on_error(exc)
        return
    if on_result is not None:
        on_result(result)


@pytest.fixture
def shell(qtbot, tmp_path):
    """A `UiShell` with real widgets and recording seams, no `MainWindow`."""
    parent = QWidget()
    qtbot.addWidget(parent)
    stage = CenterStage()
    qtbot.addWidget(stage)
    audit = QListWidget()
    qtbot.addWidget(audit)
    messages: list[str] = []
    built = UiShell(
        window=parent,
        stage=stage,
        audit=audit,
        status=lambda text="", *rest: messages.append(str(text)),
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat),
        run_async=_sync_run,
        default_dir=lambda: "",
        reveal_left_panel=lambda widget: None,
        set_left_panel_visible=lambda widget, visible: None,
        reveal_raw_xml=lambda: None,
        is_light_theme=lambda: False,
    )
    return built, messages


@pytest.fixture
def controller(shell):
    built, messages = shell
    ctl = PhpTabController(built)
    return ctl, built, messages


def _edit(tab, text):
    """Replace a tab's buffer AND mark it dirty.

    `QTextDocument.setPlainText` resets the modified flag (it is the *load*
    gesture, which is exactly why `PhpFileTab.set_text` uses it), so a test that
    only called it would assert against a permanently clean tab.
    """
    tab.editor.setPlainText(text)
    tab.editor.document().setModified(True)


def _php(tmp_path, name="thing.php", text="<?php echo 1;"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# -- File ▸ Open PHP File… ----------------------------------------------------


def test_open_path_creates_a_tab_hosting_the_file_text(controller, tmp_path):
    ctl, built, _messages = controller
    path = _php(tmp_path)

    tab = ctl.open_path(path)

    assert isinstance(tab, PhpFileTab)
    assert tab.text() == "<?php echo 1;"
    assert built.stage.php_file_tab(php_tab_key(path)) is tab
    assert built.stage.currentWidget() is tab
    assert tab.is_dirty() is False


def test_open_dialog_opens_every_chosen_file(controller, tmp_path):
    ctl, built, _messages = controller
    first, second = _php(tmp_path, "a.php"), _php(tmp_path, "b.php")
    ctl._choose_open_paths = lambda: [str(first), str(second)]

    tabs = ctl.open_php_file_dialog()

    assert len(tabs) == 2
    assert len(built.stage.php_file_tabs()) == 2


def test_open_dialog_cancelled_opens_nothing(controller):
    ctl, built, _messages = controller
    ctl._choose_open_paths = lambda: []

    assert ctl.open_php_file_dialog() == []
    assert built.stage.php_file_tabs() == {}


def test_reopening_focuses_the_existing_tab_without_rereading_from_disk(
    controller, tmp_path
):
    """The crucial correctness point: a second Open of a DIRTY file must not
    reload from disk and silently discard the user's edits."""
    ctl, built, _messages = controller
    path = _php(tmp_path)
    reads: list[Path] = []
    ctl._reader = lambda p: reads.append(p) or read_php_text(p)

    tab = ctl.open_path(path)
    _edit(tab, "<?php echo 'edited';")
    again = ctl.open_path(path)

    assert again is tab
    assert tab.text() == "<?php echo 'edited';"
    assert len(reads) == 1


def test_a_relative_and_an_absolute_path_land_on_one_tab(controller, tmp_path, monkeypatch):
    ctl, built, _messages = controller
    path = _php(tmp_path)
    monkeypatch.chdir(tmp_path)

    first = ctl.open_path(path)
    second = ctl.open_path(Path("thing.php"))

    assert first is second
    assert len(built.stage.php_file_tabs()) == 1


def test_an_unreadable_file_is_refused_out_loud_and_opens_no_tab(controller, tmp_path):
    ctl, built, messages = controller

    tab = ctl.open_path(tmp_path / "missing.php")

    assert tab is None
    assert built.stage.php_file_tabs() == {}
    assert any("Cannot open missing.php" in m for m in messages)


def test_a_non_utf8_file_is_refused_rather_than_lossily_decoded(controller, tmp_path):
    """Opening it with errors="replace" would make the tab's very first Ctrl+S
    write replacement characters over the user's file -- data loss dressed up as
    convenience."""
    ctl, built, messages = controller
    path = tmp_path / "latin.php"
    path.write_bytes(b"<?php $x = '\xe9';")

    assert ctl.open_path(path) is None
    assert built.stage.php_file_tabs() == {}
    assert any("not valid UTF-8" in m for m in messages)


# -- lint seams (wired by the host, never imported here) ----------------------


def test_the_lint_settings_seam_reaches_the_new_tab(controller, tmp_path):
    ctl, _built, _messages = controller
    sentinel = object()
    ctl.lint_settings = lambda: (sentinel, True)

    tab = ctl.open_path(_php(tmp_path))

    assert tab.lint_service is sentinel
    assert tab.lint_on_save is True


def test_a_broken_lint_seam_degrades_to_an_unlinted_tab(controller, tmp_path):
    """§22 is advisory: a broken lint lane must cost linting, never PHP editing."""
    ctl, _built, _messages = controller

    def boom():
        raise RuntimeError("no lint lane")

    ctl.lint_settings = boom

    tab = ctl.open_path(_php(tmp_path))

    assert isinstance(tab, PhpFileTab)
    assert tab.lint_service is None
    assert tab.lint_on_save is False


def test_tab_opened_announces_the_tab_and_its_stage_key(controller, tmp_path):
    ctl, _built, _messages = controller
    path = _php(tmp_path)
    seen = []
    ctl.tab_opened.connect(lambda tab, key: seen.append((tab, key)))

    tab = ctl.open_path(path)

    assert seen == [(tab, php_tab_key(path))]


def test_tab_opened_fires_once_per_file_not_once_per_open(controller, tmp_path):
    ctl, _built, _messages = controller
    path = _php(tmp_path)
    seen = []
    ctl.tab_opened.connect(lambda tab, key: seen.append(key))

    ctl.open_path(path)
    ctl.open_path(path)

    assert len(seen) == 1


# -- save reporting -----------------------------------------------------------


def test_dirtying_a_tab_marks_its_title_and_saving_clears_it(controller, tmp_path):
    ctl, built, _messages = controller
    path = _php(tmp_path)
    tab = ctl.open_path(path)
    index = built.stage.indexOf(tab)

    _edit(tab, "<?php echo 2;")
    assert built.stage.tabText(index).endswith(" *")

    assert tab.save() is True
    assert built.stage.tabText(index) == "thing.php"
    assert path.read_text(encoding="utf-8") == "<?php echo 2;"


def test_a_successful_save_reports_the_path_in_the_status_bar(controller, tmp_path):
    ctl, _built, messages = controller
    path = _php(tmp_path)
    tab = ctl.open_path(path)
    messages.clear()

    _edit(tab, "x")
    tab.save()

    assert any(m == f"Saved {path}" for m in messages)


def test_a_failed_save_shows_the_hosts_modal_and_keeps_the_tab_dirty(
    controller, tmp_path, monkeypatch
):
    ctl, _built, _messages = controller
    shown = []
    monkeypatch.setattr(
        modals.QMessageBox,
        "critical",
        classmethod(lambda cls, *args, **kwargs: shown.append(args)),
    )

    def exploding_writer(path, text):
        raise OSError("read-only filesystem")

    ctl._writer = exploding_writer
    tab = ctl.open_path(_php(tmp_path))
    _edit(tab, "x")

    assert tab.save() is False
    assert tab.is_dirty() is True
    assert shown and "read-only filesystem" in shown[0][-1]


def test_save_active_tab_is_a_no_op_when_no_php_tab_is_active(controller):
    ctl, _built, _messages = controller
    assert ctl.save_active_tab() is False


def test_save_active_tab_saves_the_focused_tab(controller, tmp_path):
    ctl, _built, _messages = controller
    path = _php(tmp_path)
    tab = ctl.open_path(path)
    _edit(tab, "<?php echo 'via router';")

    assert ctl.save_active_tab() is True
    assert path.read_text(encoding="utf-8") == "<?php echo 'via router';"


# -- the ✕ on a PHP tab (previously wired to nothing at all) ------------------


def test_closing_a_clean_tab_does_not_prompt(controller, tmp_path):
    ctl, built, _messages = controller
    path = _php(tmp_path)
    ctl.open_path(path)
    ctl._confirm_close = lambda name: pytest.fail("a clean tab must not prompt")

    ctl.on_close_requested(php_tab_key(path))

    assert built.stage.php_file_tabs() == {}


def test_the_stage_close_signal_reaches_the_controller(controller, tmp_path):
    """The gap this lane closes: `php_file_close_requested` was emitted into the
    void, so the ✕ on a PHP tab did nothing at all."""
    ctl, built, _messages = controller
    built.stage.php_file_close_requested.connect(ctl.on_close_requested)
    path = _php(tmp_path)
    tab = ctl.open_path(path)

    built.stage.tabCloseRequested.emit(built.stage.indexOf(tab))

    assert built.stage.php_file_tabs() == {}


def test_cancelling_the_prompt_keeps_a_dirty_tab_open(controller, tmp_path):
    ctl, built, _messages = controller
    path = _php(tmp_path)
    tab = ctl.open_path(path)
    _edit(tab, "dirty")
    ctl._confirm_close = lambda name: "cancel"

    ctl.on_close_requested(php_tab_key(path))

    assert built.stage.php_file_tab(php_tab_key(path)) is tab
    assert path.read_text(encoding="utf-8") == "<?php echo 1;"


def test_discarding_closes_without_writing(controller, tmp_path):
    ctl, built, _messages = controller
    path = _php(tmp_path)
    tab = ctl.open_path(path)
    _edit(tab, "dirty")
    ctl._confirm_close = lambda name: "discard"

    ctl.on_close_requested(php_tab_key(path))

    assert built.stage.php_file_tabs() == {}
    assert path.read_text(encoding="utf-8") == "<?php echo 1;"


def test_choosing_save_writes_then_closes(controller, tmp_path):
    ctl, built, _messages = controller
    path = _php(tmp_path)
    tab = ctl.open_path(path)
    _edit(tab, "<?php echo 'saved on close';")
    ctl._confirm_close = lambda name: "save"

    ctl.on_close_requested(php_tab_key(path))

    assert built.stage.php_file_tabs() == {}
    assert path.read_text(encoding="utf-8") == "<?php echo 'saved on close';"


def test_a_failed_save_from_the_prompt_aborts_the_close(controller, tmp_path, monkeypatch):
    """`_on_ddl_object_close_requested`'s rule: a save that did not happen must
    be treated exactly like Cancel, never as grounds to discard the buffer."""
    ctl, built, _messages = controller
    monkeypatch.setattr(
        modals.QMessageBox, "critical", classmethod(lambda cls, *a, **k: None)
    )

    def exploding_writer(path, text):
        raise OSError("nope")

    ctl._writer = exploding_writer
    path = _php(tmp_path)
    tab = ctl.open_path(path)
    _edit(tab, "dirty")
    ctl._confirm_close = lambda name: "save"

    ctl.on_close_requested(php_tab_key(path))

    assert built.stage.php_file_tab(php_tab_key(path)) is tab


def test_closing_an_unknown_key_is_harmless(controller):
    ctl, _built, _messages = controller
    ctl.on_close_requested("untitled:404")  # no exception


def test_a_reopened_file_still_closes_after_having_been_closed_once(
    controller, tmp_path
):
    """Regression guard on the one-shot wiring set: the `_wired` bookkeeping
    must be released on close, or a reopened file's signals never reconnect."""
    ctl, built, _messages = controller
    path = _php(tmp_path)
    key = php_tab_key(path)
    ctl.open_path(path)
    ctl.on_close_requested(key)

    tab = ctl.open_path(path)
    _edit(tab, "dirty again")
    index = built.stage.indexOf(tab)

    assert built.stage.tabText(index).endswith(" *")


# -- drag and drop ------------------------------------------------------------


def _mime(*paths):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    return mime


def test_dropped_paths_reads_local_files_out_of_the_mime_data(tmp_path):
    path = _php(tmp_path)
    assert PhpTabController.dropped_paths(_mime(path)) == [path]


def test_dropped_paths_ignores_mime_data_without_urls():
    assert PhpTabController.dropped_paths(QMimeData()) == []
    assert PhpTabController.dropped_paths(None) == []


def test_a_drag_of_an_existing_file_is_accepted_and_a_folder_is_not(tmp_path):
    path = _php(tmp_path)
    assert PhpTabController.can_accept_drop([path]) is True
    assert PhpTabController.can_accept_drop([tmp_path]) is False
    assert PhpTabController.can_accept_drop([tmp_path / "gone.php"]) is False


def test_dropping_a_php_file_opens_it(controller, tmp_path):
    ctl, built, _messages = controller
    path = _php(tmp_path)

    ctl.handle_dropped_paths([path])

    assert built.stage.php_file_tab(php_tab_key(path)) is not None


def test_dropping_a_pgtp_goes_to_the_project_open_path_not_a_php_tab(
    controller, tmp_path
):
    """§18.2's New Project / Open Project / Edit Standalone chooser owns a
    `.pgtp`; opening it as text here would silently strand the user."""
    ctl, built, _messages = controller
    project = tmp_path / "app.pgtp"
    project.write_text("<Project/>", encoding="utf-8")
    routed = []
    ctl.open_pgtp = routed.append

    ctl.handle_dropped_paths([project])

    assert routed == [project]
    assert built.stage.php_file_tabs() == {}


def test_dropping_a_pgtp_with_no_project_seam_is_refused_not_mis_opened(
    controller, tmp_path
):
    ctl, built, messages = controller
    project = tmp_path / "app.pgtp"
    project.write_text("<Project/>", encoding="utf-8")
    ctl.open_pgtp = None

    ctl.handle_dropped_paths([project])

    assert built.stage.php_file_tabs() == {}
    assert any("Cannot open app.pgtp" in m for m in messages)


def test_dropping_a_binary_file_is_refused_out_loud(controller, tmp_path):
    ctl, built, messages = controller
    blob = tmp_path / "logo.png"
    blob.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

    ctl.handle_dropped_paths([blob])

    assert built.stage.php_file_tabs() == {}
    assert any("binary" in m for m in messages)


def test_dropping_a_folder_is_refused(controller, tmp_path):
    ctl, built, messages = controller
    (tmp_path / "src").mkdir()

    ctl.handle_dropped_paths([tmp_path / "src"])

    assert built.stage.php_file_tabs() == {}
    assert any("folder" in m for m in messages)


def test_dropping_a_mixed_batch_opens_the_good_ones_and_refuses_the_rest(
    controller, tmp_path
):
    ctl, built, messages = controller
    good = _php(tmp_path, "ok.php")
    blob = tmp_path / "x.bin"
    blob.write_bytes(b"\x00\x01\x02")

    ctl.handle_dropped_paths([good, blob])

    assert len(built.stage.php_file_tabs()) == 1
    assert any("Cannot open x.bin" in m for m in messages)


def test_looks_like_text_accepts_source_and_rejects_nul_bytes(tmp_path):
    assert looks_like_text(_php(tmp_path)) is True
    blob = tmp_path / "b.dat"
    blob.write_bytes(b"aaa\x00bbb")
    assert looks_like_text(blob) is False
    assert looks_like_text(tmp_path / "nope") is False
    assert looks_like_text(tmp_path) is False


# -- [Lint] click-to-navigate -------------------------------------------------


def test_navigate_to_focuses_the_tab_and_places_the_caret(controller, tmp_path):
    ctl, built, _messages = controller
    path = _php(tmp_path, "many.php", "one\ntwo\nthree\nfour\n")
    tab = ctl.open_path(path)
    built.stage.setCurrentIndex(built.stage.raw_xml_tab_index)

    ctl.navigate_to(php_tab_key(path), 3)

    assert built.stage.currentWidget() is tab
    assert tab.editor.textCursor().blockNumber() == 2


def test_navigate_to_a_closed_tab_does_nothing(controller, tmp_path):
    ctl, built, _messages = controller
    before = built.stage.currentIndex()

    ctl.navigate_to("untitled:99", 4)
    ctl.navigate_to(None, 4)
    ctl.navigate_to(php_tab_key(tmp_path / "a.php"), None)

    assert built.stage.currentIndex() == before


# -- host wiring: the gestures that make §21 reachable in the real window -----
#
# These construct a real `MainWindow` because what is under test is precisely
# the HOST side (a menu item, three dispatch routers, two QMainWindow drag/drop
# overrides) -- there is nowhere else it could live.


def _window(qtbot, tmp_path):
    from pgtp_editor.ui.main_window import MainWindow

    window = MainWindow(
        settings=QSettings(str(tmp_path / "w.ini"), QSettings.Format.IniFormat),
        generator_config_dir=tmp_path / "cfg",
    )
    qtbot.addWidget(window)
    return window


def test_file_menu_open_php_file_opens_a_tab(qtbot, tmp_path):
    """The gap that made the whole feature dark: before this, nothing but a test
    could open a PHP tab."""
    from tests.ui._menu_helpers import find_action, find_top_menu

    window = _window(qtbot, tmp_path)
    path = _php(tmp_path)
    window._php_tabs._choose_open_paths = lambda: [str(path)]

    action = find_action(find_top_menu(window, "File"), "Open PHP File…")
    assert action is not None
    action.trigger()

    assert window.center_stage.php_file_tab(php_tab_key(path)) is not None


def test_ctrl_s_with_a_php_tab_focused_saves_the_file_not_the_project(
    qtbot, tmp_path, monkeypatch
):
    window = _window(qtbot, tmp_path)
    saved_project = []
    monkeypatch.setattr(
        window._doc_ui, "save_project", lambda: saved_project.append(True)
    )
    path = _php(tmp_path)
    tab = window._php_tabs.open_path(path)
    _edit(tab, "<?php echo 'from the router';")

    window._save_active_tab()

    assert saved_project == []
    assert path.read_text(encoding="utf-8") == "<?php echo 'from the router';"


def test_ctrl_f_with_a_php_tab_focused_uses_that_tabs_own_find_bar(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    tab = window._php_tabs.open_path(_php(tmp_path))

    assert window._find_ui.active_find_bar() is tab.find_replace_bar
    # ... and it did NOT yank the user over to Raw XML on the way.
    assert window.center_stage.currentWidget() is tab


def test_the_bookmarks_menu_follows_a_php_tab(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    tab = window._php_tabs.open_path(_php(tmp_path))

    assert window._find_ui.active_bookmark_editor() is tab.editor


def test_the_window_accepts_drops_and_routes_them(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    assert window.acceptDrops() is True
    path = _php(tmp_path)

    window._php_tabs.handle_dropped_paths(
        PhpTabController.dropped_paths(_mime(path))
    )

    assert window.center_stage.php_file_tab(php_tab_key(path)) is not None


def test_a_dropped_pgtp_reaches_the_project_open_path(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    prompted = []
    monkeypatch.setattr(
        window._doc_ui, "prompt_open_mode", lambda p: prompted.append(p)
    )
    project = tmp_path / "app.pgtp"
    project.write_text("<Project/>", encoding="utf-8")

    window._php_tabs.handle_dropped_paths([project])

    assert prompted == [str(project)]
    assert window.center_stage.php_file_tabs() == {}


def test_the_php_tab_close_button_is_wired_in_the_real_window(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    path = _php(tmp_path)
    tab = window._php_tabs.open_path(path)

    window.center_stage.tabCloseRequested.emit(window.center_stage.indexOf(tab))

    assert window.center_stage.php_file_tabs() == {}
