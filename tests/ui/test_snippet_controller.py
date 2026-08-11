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
"""`ui/snippet_controller.py` — the store's location, its startup load, and the
Export / Import gestures with their collision question (FQ-030).

`config_dir` is a `tmp_path` in EVERY test, so the real per-user config
directory is never read and never written — the injection exists for exactly
that. Every `QFileDialog`/`QMessageBox` is monkeypatched through
`pgtp_editor.ui.modals`, and the dialog is only ever `show()`n, never `exec`d.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QDialogButtonBox, QListWidget, QWidget

from pgtp_editor.sql.snippet_store import (
    SNIPPETS_FILENAME,
    load_snippets,
    save_snippets,
    serialize_snippets,
)
from pgtp_editor.sql.templates import DEFAULT_SNIPPETS, Snippet
from pgtp_editor.ui import modals
from pgtp_editor.ui.center_stage import CenterStage
from pgtp_editor.ui.snippet_controller import SnippetController, snippets_path
from pgtp_editor.ui.ui_shell import UiShell

MINE = Snippet("upd", "an update", "UPDATE {{1:t}} SET {{0}};")
THEIRS = Snippet("case", "theirs", "THEIR CASE")


def _sync_run(fn, on_result=None, on_error=None, **kwargs):
    result = fn(**kwargs)
    if on_result is not None:
        on_result(result)


@pytest.fixture
def lane(qtbot, tmp_path):
    parent = QWidget()
    qtbot.addWidget(parent)
    stage = CenterStage()
    qtbot.addWidget(stage)
    audit = QListWidget()
    qtbot.addWidget(audit)
    messages: list[str] = []
    shell = UiShell(
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
    cfg = tmp_path / "cfg"
    controller = SnippetController(shell, parent=parent, config_dir=cfg)
    return controller, shell, audit, messages, cfg


def _rows(audit):
    return [audit.item(i).text() for i in range(audit.count())]


def _open(qtbot, controller):
    dialog = controller.open_editor()
    qtbot.addWidget(dialog)
    return dialog


# -- where the store lives -----------------------------------------------------


def test_the_store_is_one_json_file_in_the_injected_config_dir(lane, tmp_path):
    controller, _shell, _audit, _messages, cfg = lane
    assert controller.path == cfg / SNIPPETS_FILENAME
    assert controller.path.suffix == ".json"


def test_without_an_override_the_path_is_the_app_data_dir():
    """The same per-user folder §19/§22 already use — and nothing here writes
    to it, this only asserts the resolution."""
    assert snippets_path().name == SNIPPETS_FILENAME
    assert snippets_path().parent != snippets_path()


# -- startup load, and the fan-out into the editors ----------------------------


def test_a_missing_store_leaves_the_defaults_in_force_silently(lane):
    controller, _shell, audit, _messages, _cfg = lane
    controller.load()
    assert controller.snippets() == DEFAULT_SNIPPETS
    assert controller.load_error() is None
    assert _rows(audit) == []


def test_a_saved_store_reaches_the_sql_editors_that_already_exist(lane):
    controller, shell, _audit, _messages, cfg = lane
    save_snippets(cfg / SNIPPETS_FILENAME, (MINE,))
    controller.load()
    assert shell.stage.snippets() == (MINE,)
    assert shell.stage.ddl_explorer_panel().editor.snippets() == (MINE,)


def test_a_saved_store_reaches_sql_tabs_opened_later(lane):
    controller, shell, _audit, _messages, cfg = lane
    save_snippets(cfg / SNIPPETS_FILENAME, (MINE,))
    controller.load()
    panel = shell.stage.open_sandbox_sql_tab()
    assert panel.editor.snippets() == (MINE,)


def test_php_editors_are_left_on_their_own_set(lane):
    """The set is plpgsql — `CodeEditor` gates Ctrl+Alt+E on the same
    `language` for the same reason."""
    controller, shell, _audit, _messages, cfg = lane
    save_snippets(cfg / SNIPPETS_FILENAME, (MINE,))
    controller.load()
    tab = shell.stage.open_php_file_tab(None, "<?php echo 1;")
    assert tab.editor.snippets() == DEFAULT_SNIPPETS


def test_saving_from_the_editor_is_live_without_a_restart(qtbot, lane):
    controller, shell, _audit, _messages, cfg = lane
    controller.load()
    dialog = _open(qtbot, controller)
    dialog.set_snippets((MINE,))
    dialog.accept()
    assert shell.stage.ddl_explorer_panel().editor.snippets() == (MINE,)
    assert (cfg / SNIPPETS_FILENAME).exists()
    assert SnippetController(shell, config_dir=cfg).path.exists()


# -- a corrupt store is never silently discarded -------------------------------


def test_a_corrupt_store_keeps_the_defaults_and_says_why(lane):
    controller, _shell, audit, _messages, cfg = lane
    cfg.mkdir(parents=True)
    (cfg / SNIPPETS_FILENAME).write_text("{ nonsense", encoding="utf-8")
    controller.load()
    assert controller.snippets() == DEFAULT_SNIPPETS
    assert controller.load_error() is not None
    assert any("[Snippets]" in row and "not be overwritten" in row for row in _rows(audit))


def test_a_corrupt_store_is_never_written_over(qtbot, lane):
    controller, _shell, _audit, _messages, cfg = lane
    cfg.mkdir(parents=True)
    path = cfg / SNIPPETS_FILENAME
    path.write_text("{ nonsense", encoding="utf-8")
    controller.load()
    assert controller.save((MINE,)) is False
    assert path.read_text(encoding="utf-8") == "{ nonsense"


def test_the_editor_opens_read_only_over_a_corrupt_store(qtbot, lane):
    controller, _shell, _audit, _messages, cfg = lane
    cfg.mkdir(parents=True)
    (cfg / SNIPPETS_FILENAME).write_text("{ nonsense", encoding="utf-8")
    controller.load()
    dialog = _open(qtbot, controller)
    assert dialog.add_snippet() == -1
    assert SNIPPETS_FILENAME in dialog.note()


# -- the editor is single-instance --------------------------------------------


def test_reopening_focuses_the_open_editor(qtbot, lane):
    controller, _shell, _audit, _messages, _cfg = lane
    controller.load()
    first = _open(qtbot, controller)
    assert controller.open_editor() is first
    first.reject()
    assert controller.dialog() is None


# -- export --------------------------------------------------------------------


def test_export_writes_the_rows_as_they_currently_stand(qtbot, lane, tmp_path, monkeypatch):
    controller, _shell, _audit, _messages, _cfg = lane
    controller.load()
    dialog = _open(qtbot, controller)
    dialog.set_snippets((MINE,))
    target = tmp_path / "share.json"
    monkeypatch.setattr(
        modals.QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), "")
    )
    dialog.export_requested.emit()
    assert target.read_text(encoding="utf-8") == serialize_snippets((MINE,))
    assert "share.json" in dialog.message()


def test_a_cancelled_export_writes_nothing(qtbot, lane, tmp_path, monkeypatch):
    controller, _shell, _audit, _messages, _cfg = lane
    controller.load()
    dialog = _open(qtbot, controller)
    monkeypatch.setattr(
        modals.QFileDialog, "getSaveFileName", lambda *a, **k: ("", "")
    )
    dialog.export_requested.emit()
    assert list(tmp_path.glob("*.json")) == []


# -- import, and the collision rule --------------------------------------------


def _incoming(tmp_path, snippets):
    path = tmp_path / "incoming.json"
    path.write_text(serialize_snippets(snippets), encoding="utf-8")
    return path


def _pick(monkeypatch, path):
    monkeypatch.setattr(
        modals.QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), "")
    )


def test_non_colliding_snippets_import_without_a_question(
    qtbot, lane, tmp_path, monkeypatch
):
    controller, _shell, _audit, _messages, _cfg = lane
    controller.load()
    dialog = _open(qtbot, controller)
    _pick(monkeypatch, _incoming(tmp_path, (MINE,)))
    monkeypatch.setattr(
        modals.QMessageBox, "question", lambda *a, **k: pytest.fail("asked")
    )
    dialog.import_requested.emit()
    assert dialog.result_snippets()[-1] == MINE
    assert len(dialog.result_snippets()) == len(DEFAULT_SNIPPETS) + 1


def test_a_colliding_snippet_is_never_applied_without_a_yes(
    qtbot, lane, tmp_path, monkeypatch
):
    controller, _shell, _audit, _messages, _cfg = lane
    controller.load()
    dialog = _open(qtbot, controller)
    _pick(monkeypatch, _incoming(tmp_path, (THEIRS, MINE)))
    asked = []

    def _no(*args, **kwargs):
        asked.append(args[2] if len(args) > 2 else "")
        return modals.QMessageBox.StandardButton.No

    monkeypatch.setattr(modals.QMessageBox, "question", _no)
    dialog.import_requested.emit()
    result = dialog.result_snippets()
    assert asked and "case" in asked[0]
    assert result[0] == DEFAULT_SNIPPETS[0]  # ours survived
    assert MINE in result  # the new one still arrived
    assert THEIRS not in result


def test_yes_replaces_the_colliding_ones_in_place(qtbot, lane, tmp_path, monkeypatch):
    controller, _shell, _audit, _messages, _cfg = lane
    controller.load()
    dialog = _open(qtbot, controller)
    _pick(monkeypatch, _incoming(tmp_path, (THEIRS,)))
    monkeypatch.setattr(
        modals.QMessageBox,
        "question",
        lambda *a, **k: modals.QMessageBox.StandardButton.Yes,
    )
    dialog.import_requested.emit()
    assert dialog.result_snippets()[0] == THEIRS
    assert len(dialog.result_snippets()) == len(DEFAULT_SNIPPETS)


def test_cancelling_the_collision_question_changes_nothing(
    qtbot, lane, tmp_path, monkeypatch
):
    controller, _shell, _audit, _messages, _cfg = lane
    controller.load()
    dialog = _open(qtbot, controller)
    _pick(monkeypatch, _incoming(tmp_path, (THEIRS, MINE)))
    monkeypatch.setattr(
        modals.QMessageBox,
        "question",
        lambda *a, **k: modals.QMessageBox.StandardButton.Cancel,
    )
    dialog.import_requested.emit()
    assert dialog.result_snippets() == DEFAULT_SNIPPETS
    assert "cancelled" in dialog.message()


def test_an_import_is_not_persisted_until_ok(qtbot, lane, tmp_path, monkeypatch):
    """Import lands in the ROWS, so Cancel is a working undo for it."""
    controller, _shell, _audit, _messages, cfg = lane
    controller.load()
    dialog = _open(qtbot, controller)
    _pick(monkeypatch, _incoming(tmp_path, (MINE,)))
    dialog.import_requested.emit()
    assert not (cfg / SNIPPETS_FILENAME).exists()
    dialog.reject()
    assert not (cfg / SNIPPETS_FILENAME).exists()
    assert controller.snippets() == DEFAULT_SNIPPETS


def test_a_broken_import_file_is_refused_and_the_rows_are_untouched(
    qtbot, lane, tmp_path, monkeypatch
):
    controller, _shell, _audit, _messages, _cfg = lane
    controller.load()
    dialog = _open(qtbot, controller)
    bad = tmp_path / "bad.json"
    bad.write_text("{ nope", encoding="utf-8")
    _pick(monkeypatch, bad)
    refusals = []
    monkeypatch.setattr(
        modals.QMessageBox, "critical", lambda *a, **k: refusals.append(a)
    )
    dialog.import_requested.emit()
    assert refusals
    assert dialog.result_snippets() == DEFAULT_SNIPPETS


def test_a_cancelled_file_chooser_imports_nothing(qtbot, lane, monkeypatch):
    controller, _shell, _audit, _messages, _cfg = lane
    controller.load()
    dialog = _open(qtbot, controller)
    monkeypatch.setattr(
        modals.QFileDialog, "getOpenFileName", lambda *a, **k: ("", "")
    )
    dialog.import_requested.emit()
    assert dialog.result_snippets() == DEFAULT_SNIPPETS


def test_a_trigger_word_that_differs_only_in_case_still_collides(
    qtbot, lane, tmp_path, monkeypatch
):
    """`find_snippet` matches case-insensitively, so `CASE` and `case` are the
    same typing shortcut — importing one over the other must ASK."""
    controller, _shell, _audit, _messages, _cfg = lane
    controller.load()
    dialog = _open(qtbot, controller)
    shouty = Snippet(DEFAULT_SNIPPETS[0].prefix.upper(), "theirs", "THEIRS")
    _pick(monkeypatch, _incoming(tmp_path, (shouty,)))
    asked = []

    def _no(*args, **kwargs):
        asked.append(args[2] if len(args) > 2 else "")
        return modals.QMessageBox.StandardButton.No

    monkeypatch.setattr(modals.QMessageBox, "question", _no)
    dialog.import_requested.emit()
    assert asked
    assert dialog.result_snippets() == DEFAULT_SNIPPETS


def test_an_import_file_holding_no_snippets_says_so_and_asks_nothing(
    qtbot, lane, tmp_path, monkeypatch
):
    controller, _shell, _audit, _messages, _cfg = lane
    controller.load()
    dialog = _open(qtbot, controller)
    _pick(monkeypatch, _incoming(tmp_path, ()))
    monkeypatch.setattr(
        modals.QMessageBox, "question", lambda *a, **k: pytest.fail("asked")
    )
    dialog.import_requested.emit()
    assert dialog.result_snippets() == DEFAULT_SNIPPETS
    assert "no snippets" in dialog.message()


def test_an_unreadable_import_file_is_reported_not_raised(
    qtbot, lane, tmp_path, monkeypatch
):
    controller, _shell, _audit, _messages, _cfg = lane
    controller.load()
    dialog = _open(qtbot, controller)
    missing = tmp_path / "gone.json"
    _pick(monkeypatch, missing)
    refusals = []
    monkeypatch.setattr(
        modals.QMessageBox, "critical", lambda *a, **k: refusals.append(a)
    )
    dialog.import_requested.emit()
    assert refusals
    assert dialog.result_snippets() == DEFAULT_SNIPPETS


# -- the export file IS the store file -----------------------------------------


def test_an_exported_file_loads_back_as_a_store(qtbot, lane, tmp_path, monkeypatch):
    """"Mail this file to a colleague" only works if what export writes is what
    the store reader accepts — one format, not an encoding of its own."""
    controller, _shell, _audit, _messages, _cfg = lane
    controller.load()
    dialog = _open(qtbot, controller)
    dialog.set_snippets((MINE, THEIRS))
    target = tmp_path / "share.json"
    monkeypatch.setattr(
        modals.QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), "")
    )
    dialog.export_requested.emit()
    loaded = load_snippets(target)
    assert loaded.ok and loaded.snippets == (MINE, THEIRS)


def test_a_failed_export_is_reported_and_the_rows_are_untouched(
    qtbot, lane, tmp_path, monkeypatch
):
    controller, _shell, _audit, _messages, _cfg = lane
    controller.load()
    dialog = _open(qtbot, controller)
    blocked = tmp_path / "dir.json"
    blocked.mkdir()
    monkeypatch.setattr(
        modals.QFileDialog, "getSaveFileName", lambda *a, **k: (str(blocked), "")
    )
    failures = []
    monkeypatch.setattr(
        modals.QMessageBox, "critical", lambda *a, **k: failures.append(a)
    )
    dialog.export_requested.emit()
    assert failures
    assert dialog.result_snippets() == DEFAULT_SNIPPETS


# -- saving: failures are said out loud, and Cancel undoes everything ----------


def test_a_save_that_could_not_be_written_is_reported_and_changes_nothing(
    qtbot, lane, monkeypatch
):
    """Unlike loading, a save the user asked for and that failed is never
    silent — and the set in force must not pretend it took."""
    controller, shell, _audit, _messages, cfg = lane
    controller.load()
    cfg.write_text("I am a file where the config directory should be")
    failures = []
    monkeypatch.setattr(
        modals.QMessageBox, "critical", lambda *a, **k: failures.append(a)
    )
    assert controller.save((MINE,)) is False
    assert failures
    assert controller.snippets() == DEFAULT_SNIPPETS
    assert shell.stage.ddl_explorer_panel().editor.snippets() == DEFAULT_SNIPPETS


def test_cancelling_the_editor_undoes_every_edit_in_it(qtbot, lane, tmp_path):
    """Nothing persists until OK — the rows are a scratch copy, so Cancel is a
    working undo for adds, deletes and body edits alike."""
    controller, shell, _audit, _messages, cfg = lane
    save_snippets(cfg / SNIPPETS_FILENAME, (MINE, THEIRS))
    controller.load()
    dialog = _open(qtbot, controller)
    dialog.remove_row(0)
    dialog.add_snippet("brandnew", "mine", "SELECT {{0}};")
    dialog.reject()
    assert controller.snippets() == (MINE, THEIRS)
    assert shell.stage.ddl_explorer_panel().editor.snippets() == (MINE, THEIRS)
    assert load_snippets(cfg / SNIPPETS_FILENAME).snippets == (MINE, THEIRS)


def test_clicking_add_then_ok_persists_the_new_snippet(qtbot, lane):
    """The whole path a user actually has: click Add, press OK, and the row is
    in the file and live in the editors. Every other add test in this lane calls
    `add_snippet()` directly, which is how a dead Add button stayed green
    (BUG-260812001455)."""
    controller, shell, _audit, _messages, cfg = lane
    save_snippets(cfg / SNIPPETS_FILENAME, (MINE,))
    controller.load()
    dialog = _open(qtbot, controller)
    dialog.add_button.click()
    assert len(dialog.result_snippets()) == 2
    dialog.button_box.button(QDialogButtonBox.StandardButton.Ok).click()
    persisted = load_snippets(cfg / SNIPPETS_FILENAME).snippets
    assert len(persisted) == 2 and persisted[0] == MINE
    assert controller.snippets() == persisted
    assert shell.stage.ddl_explorer_panel().editor.snippets() == persisted


def test_clicking_delete_then_ok_persists_the_removal(qtbot, lane):
    controller, shell, _audit, _messages, cfg = lane
    save_snippets(cfg / SNIPPETS_FILENAME, (MINE, THEIRS))
    controller.load()
    dialog = _open(qtbot, controller)
    dialog.table.setCurrentCell(0, 0)
    dialog.delete_button.click()
    dialog.button_box.button(QDialogButtonBox.StandardButton.Ok).click()
    assert load_snippets(cfg / SNIPPETS_FILENAME).snippets == (THEIRS,)
    assert shell.stage.ddl_explorer_panel().editor.snippets() == (THEIRS,)


def test_clicking_restore_then_ok_persists_the_built_ins(qtbot, lane):
    controller, _shell, _audit, _messages, cfg = lane
    save_snippets(cfg / SNIPPETS_FILENAME, (MINE,))
    controller.load()
    dialog = _open(qtbot, controller)
    dialog.restore_button.click()
    dialog.button_box.button(QDialogButtonBox.StandardButton.Ok).click()
    persisted = load_snippets(cfg / SNIPPETS_FILENAME).snippets
    assert persisted[0] == MINE
    assert set(DEFAULT_SNIPPETS).issubset(set(persisted))


def test_a_corrupt_store_still_leaves_the_defaults_live_in_the_editors(lane):
    """Read-only is not "no snippets": the lane must still push the defaults
    into the SQL editors, or a broken file would disable the gesture."""
    controller, shell, _audit, _messages, cfg = lane
    cfg.mkdir(parents=True)
    (cfg / SNIPPETS_FILENAME).write_text("{ nonsense", encoding="utf-8")
    controller.load()
    assert shell.stage.ddl_explorer_panel().editor.snippets() == DEFAULT_SNIPPETS


def test_the_editor_over_a_corrupt_store_cannot_be_accepted(qtbot, lane):
    """The OK button is disabled, and even a programmatic accept must not write
    over a file we could not understand."""
    controller, _shell, _audit, _messages, cfg = lane
    cfg.mkdir(parents=True)
    path = cfg / SNIPPETS_FILENAME
    path.write_text("{ nonsense", encoding="utf-8")
    controller.load()
    dialog = _open(qtbot, controller)
    dialog.accept()
    assert path.read_text(encoding="utf-8") == "{ nonsense"
    assert controller.snippets() == DEFAULT_SNIPPETS
