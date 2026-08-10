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
"""§8 / FQ-013 — bookmark persistence, wired.

The store itself is covered by `tests/db/test_bookmark_store.py`; this module
covers the **hookup**, which is where the design decisions live:

* the gate is the CAPABILITY fact "a §18.2 project is open"
  (`DdlProjectController.folder`), so the projectless path must be bit-for-bit
  the status quo -- session-only, wiped by `setPlainText`, and **no file written
  anywhere**;
* the gutter mixin stays ignorant of projects: it publishes
  `(editor, reason)` notifications through `ui/editor_gutter.py`'s module-level
  registry and the HOST decides what they mean;
* saves are coarse (a debounce plus a flush on project transition / app close),
  never synchronous inside the gutter click;
* restores happen at the one moment the set is wiped -- a document load;
* editors with no file identity (the read-only DDL Explorer buffer, an FQ-006
  draft tab) stay session-only even with a project open.
"""
import json

from pgtp_editor.db.bookmark_store import bookmarks_path
from pgtp_editor.db.ddl_project import SETTINGS_DIRNAME
from pgtp_editor.ui.ddl_object_editor import DdlObjectRef
from pgtp_editor.ui import editor_gutter
from pgtp_editor.ui.main_window import MainWindow

_MINIMAL_PGTP = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Project fileName="demo">\n'
    '  <Page fileName="p1" tableName="pr.equipment" caption="Equipment"/>\n'
    "</Project>\n"
)


def _window(qtbot, tmp_path):
    window = MainWindow(generator_config_dir=tmp_path / "gen")
    qtbot.addWidget(window)
    return window


def _project(tmp_path):
    """A §18.2 project folder holding a working-copy `.pgtp`."""
    folder = tmp_path / "project"
    folder.mkdir()
    document = folder / "app.pgtp"
    document.write_text(_MINIMAL_PGTP, encoding="utf-8")
    return folder, document


def _open_project(window, folder, document):
    window._ddl_project_ui.folder = folder
    window._doc_ui.project_path = str(document)


def _stored(folder):
    return json.loads(bookmarks_path(folder).read_text(encoding="utf-8"))["files"]


# --- The projectless path is untouched --------------------------------------


def test_projectless_bookmarks_are_session_only_and_write_nothing(qtbot, tmp_path):
    """The explicit decision: with no project open, behaviour is EXACTLY what it
    was -- so nothing may be written and nothing may come back."""
    window = _window(qtbot, tmp_path)
    editor = window.center_stage.xml_editor
    editor.setPlainText("a\nb\nc")

    editor.toggle_bookmark(1)
    window._flush_bookmark_writes()
    editor.setPlainText("a\nb\nc")

    assert editor.bookmarked_lines() == []  # wiped, as before
    assert not list(tmp_path.rglob("bookmarks.json"))


def test_projectless_toggle_schedules_no_write_at_all(qtbot, tmp_path):
    """Not merely "the write is a no-op": the debounce never even starts, so the
    projectless path costs one attribute read."""
    window = _window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText("a\nb")

    window.center_stage.xml_editor.toggle_bookmark(0)

    assert window._bookmark_writes == {}
    assert not window._bookmark_write_timer.isActive()


# --- Project mode: save + restore ------------------------------------------


def test_a_toggle_in_project_mode_is_written_on_the_debounce(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    folder, document = _project(tmp_path)
    _open_project(window, folder, document)
    editor = window.center_stage.xml_editor
    editor.setPlainText("a\nb\nc\nd")

    editor.toggle_bookmark(2)

    # Recorded, but NOT yet on disk: a gutter click must not do disk I/O.
    assert window._bookmark_write_timer.isActive()
    assert not bookmarks_path(folder).exists()

    window._flush_bookmark_writes()

    assert _stored(folder) == {"app.pgtp": [2]}
    assert window._bookmark_writes == {}
    assert not window._bookmark_write_timer.isActive()


def test_bookmarks_come_back_when_the_document_is_reloaded(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    folder, document = _project(tmp_path)
    _open_project(window, folder, document)
    editor = window.center_stage.xml_editor
    editor.setPlainText("a\nb\nc\nd")
    editor.toggle_bookmark(1)
    editor.toggle_bookmark(3)
    window._flush_bookmark_writes()

    editor.setPlainText("a\nb\nc\nd")  # a reload / revert / re-checkout

    assert editor.bookmarked_lines() == [1, 3]


def test_bookmarks_come_back_in_a_new_window_an_app_restart(qtbot, tmp_path):
    folder, document = _project(tmp_path)
    first = _window(qtbot, tmp_path)
    _open_project(first, folder, document)
    first.center_stage.xml_editor.setPlainText("a\nb\nc")
    first.center_stage.xml_editor.toggle_bookmark(2)
    first.close()  # closeEvent flushes what the debounce has not written

    second = _window(qtbot, tmp_path)
    _open_project(second, folder, document)
    second.center_stage.xml_editor.setPlainText("a\nb\nc")

    assert second.center_stage.xml_editor.bookmarked_lines() == [2]


def test_clear_all_bookmarks_is_persisted_as_an_empty_set(qtbot, tmp_path):
    """Clearing is a chosen set too, and an empty set REMOVES its key rather
    than storing `[]` -- so a reload does not resurrect what was cleared."""
    window = _window(qtbot, tmp_path)
    folder, document = _project(tmp_path)
    _open_project(window, folder, document)
    editor = window.center_stage.xml_editor
    editor.setPlainText("a\nb\nc")
    editor.toggle_bookmark(0)
    window._flush_bookmark_writes()

    editor.clear_bookmarks()
    window._flush_bookmark_writes()

    assert _stored(folder) == {}
    editor.setPlainText("a\nb\nc")
    assert editor.bookmarked_lines() == []


def test_a_shortened_document_keeps_its_out_of_range_lines_on_disk(qtbot, tmp_path):
    """The load never rewrites, so a temporarily shorter document does not lose
    the lines beyond its end (v1 has no content anchoring)."""
    window = _window(qtbot, tmp_path)
    folder, document = _project(tmp_path)
    _open_project(window, folder, document)
    editor = window.center_stage.xml_editor
    editor.setPlainText("a\nb\nc\nd\ne")
    editor.toggle_bookmark(4)
    window._flush_bookmark_writes()

    editor.setPlainText("a\nb")  # shorter: line 4 does not exist right now

    assert editor.bookmarked_lines() == []
    assert _stored(folder) == {"app.pgtp": [4]}

    editor.setPlainText("a\nb\nc\nd\ne")  # grown back

    assert editor.bookmarked_lines() == [4]


def test_the_store_is_a_sibling_of_settings_json_and_is_gitignored(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    folder, document = _project(tmp_path)
    _open_project(window, folder, document)
    editor = window.center_stage.xml_editor
    editor.setPlainText("a\nb")

    editor.toggle_bookmark(0)
    window._flush_bookmark_writes()

    assert bookmarks_path(folder) == folder / SETTINGS_DIRNAME / "bookmarks.json"
    assert not (folder / "settings.json").exists()  # never a ProjectSettings key
    assert f"{SETTINGS_DIRNAME}/" in (folder / ".gitignore").read_text()


# --- Which editors persist -------------------------------------------------


def test_a_ddl_object_tab_persists_by_its_save_path(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    folder, document = _project(tmp_path)
    _open_project(window, folder, document)
    ddl_path = folder / "ddl" / "pr.recalc.sql"
    ddl_path.parent.mkdir()
    ddl_path.write_text("CREATE FUNCTION pr.recalc() ...", encoding="utf-8")
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")
    panel = window.center_stage.open_ddl_object_tab(
        ref, "one\ntwo\nthree", resolve_save_path=lambda: ddl_path
    )
    panel.remember_save_path(ddl_path)

    panel.editor.toggle_bookmark(1)
    window._flush_bookmark_writes()

    assert _stored(folder) == {"ddl/pr.recalc.sql": [1]}

    panel.editor.setPlainText("one\ntwo\nthree")

    assert panel.editor.bookmarked_lines() == [1]


def test_a_php_file_tab_persists_by_its_path(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    folder, document = _project(tmp_path)
    _open_project(window, folder, document)
    php_path = folder / "custom" / "hooks.php"
    php_path.parent.mkdir()
    php_path.write_text("<?php\n", encoding="utf-8")
    tab = window.center_stage.open_php_file_tab(php_path, "<?php\n$a = 1;\n")

    tab.editor.toggle_bookmark(1)
    window._flush_bookmark_writes()

    assert _stored(folder) == {"custom/hooks.php": [1]}


def test_the_identity_less_editors_stay_session_only(qtbot, tmp_path):
    """The read-only DDL Explorer buffer and an FQ-006 draft tab have no file to
    key against, so they persist nothing even with a project open -- and, being
    unkeyable, they cannot pollute the store either."""
    window = _window(qtbot, tmp_path)
    folder, document = _project(tmp_path)
    _open_project(window, folder, document)
    explorer = window.center_stage.ddl_editor_panel.editor
    explorer.setPlainText("a\nb\nc")
    draft = window.center_stage.open_draft_fragment_tab("trigger", "pr.equipment", "x\ny")

    explorer.toggle_bookmark(1)
    draft.editor.toggle_bookmark(0)
    window._flush_bookmark_writes()

    assert not bookmarks_path(folder).exists()
    explorer.setPlainText("a\nb\nc")
    assert explorer.bookmarked_lines() == []


def test_the_xsd_editors_stay_session_only(qtbot, tmp_path):
    """`_bookmark_file_path` names FOUR session-only families, and the test above
    covers only two. The Edit XSD / Edit AutoXSD buffer is the third: its schema
    file lives in the **app-level schema storage directory**, not under any
    project, so `relative_key` could not key it even if it were offered. Asserted
    with a project open, which is the only state in which it could go wrong."""
    window = _window(qtbot, tmp_path)
    folder, document = _project(tmp_path)
    _open_project(window, folder, document)
    # `setPlainText` marks the XSD tab dirty, so the teardown close would reach a
    # real modal; silence it through the same seam the List-All-Bookmarks tests
    # use (CLAUDE.md testing policy).
    window._xsd_ui.confirm_close = lambda: "discard"
    xsd_editor = window.center_stage.xsd_editor
    xsd_editor.setPlainText("<xs:schema/>\n<xs:element/>\n")

    assert window._bookmark_file_path(xsd_editor) is None
    xsd_editor.toggle_bookmark(1)
    window._flush_bookmark_writes()

    assert not bookmarks_path(folder).exists()
    # ...and it keeps the session-only status quo: a document load wipes it.
    xsd_editor.setPlainText("<xs:schema/>\n<xs:element/>\n")
    assert xsd_editor.bookmarked_lines() == []


def test_an_editor_the_host_does_not_own_has_no_bookmark_key(qtbot, tmp_path):
    """The fourth session-only family is the `Edit code…` dialog's editor -- a
    modal over an event body inside the XML, which `_bookmark_file_path`'s
    docstring calls "not reachable from here". Rather than enter that modal, this
    asserts the general rule the dialog relies on: an editor that is not one of
    the host's known surfaces keys to None and is therefore never written."""
    window = _window(qtbot, tmp_path)
    folder, document = _project(tmp_path)
    _open_project(window, folder, document)
    from pgtp_editor.ui.xml_editor import XmlEditor

    stranger = XmlEditor()
    qtbot.addWidget(stranger)
    stranger.setPlainText("BEGIN\n  PERFORM 1;\nEND\n")

    assert window._bookmark_file_path(stranger) is None
    assert window._bookmark_store_target(stranger) is None
    stranger.toggle_bookmark(1)
    window._flush_bookmark_writes()

    assert not bookmarks_path(folder).exists()


def test_a_document_outside_the_project_has_no_key(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    folder, _document = _project(tmp_path)
    outside = tmp_path / "elsewhere.pgtp"
    outside.write_text(_MINIMAL_PGTP, encoding="utf-8")
    _open_project(window, folder, outside)
    editor = window.center_stage.xml_editor
    editor.setPlainText("a\nb")

    editor.toggle_bookmark(0)
    window._flush_bookmark_writes()

    assert not bookmarks_path(folder).exists()


# --- The coarse flush points ------------------------------------------------


def test_a_project_transition_flushes_pending_writes(qtbot, tmp_path):
    """A pending write carries its OWN folder, so a project CLOSE still lands it
    in the project it belongs to."""
    window = _window(qtbot, tmp_path)
    folder, document = _project(tmp_path)
    _open_project(window, folder, document)
    editor = window.center_stage.xml_editor
    editor.setPlainText("a\nb\nc")
    editor.toggle_bookmark(1)

    window._ddl_project_ui.folder = None
    window._ddl_project_ui.project_changed.emit(None, None)

    assert _stored(folder) == {"app.pgtp": [1]}


def test_opening_a_project_restores_for_an_already_open_document(qtbot, tmp_path):
    """The `.pgtp`-first, project-second order: the document was loaded before
    the project existed, so no RESET notification will fire for it."""
    folder, document = _project(tmp_path)
    seed = _window(qtbot, tmp_path)
    _open_project(seed, folder, document)
    seed.center_stage.xml_editor.setPlainText("a\nb\nc")
    seed.center_stage.xml_editor.toggle_bookmark(2)
    seed._flush_bookmark_writes()

    window = _window(qtbot, tmp_path)
    window._doc_ui.project_path = str(document)
    window.center_stage.xml_editor.setPlainText("a\nb\nc")
    assert window.center_stage.xml_editor.bookmarked_lines() == []  # no project yet

    window._ddl_project_ui.folder = folder
    window._ddl_project_ui.project_changed.emit(folder, None)

    assert window.center_stage.xml_editor.bookmarked_lines() == [2]


def test_closing_the_window_stops_it_observing_bookmark_changes(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.close()

    assert not any(
        editor_gutter._resolve_observer(entry) == window._on_editor_bookmarks_changed
        for entry in editor_gutter._bookmark_observers
    )
