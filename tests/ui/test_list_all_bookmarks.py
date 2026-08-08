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
"""§8 / FQ-014 — `List All Bookmarks` → clickable `[Bookmark]` Audit rows.

The load-bearing decisions asserted here:

* the **active editor only**, like every other bookmark command;
* Find All's row grammar and two-role payload **verbatim** (a tenth grammar was
  explicitly not to be invented), with the router's own discriminator on
  `UserRole+1`;
* an editor the Audit click router has **no branch** for (the read-only DDL
  Explorer buffer, an FQ-006 draft tab) gets **roles-less, inert** rows: the
  router's fallback navigates Raw XML, and a row must never carry the user to a
  different document than the one it describes;
* the listing clears its own rows first and touches no other prefix;
* it is a **snapshot**, so the gutter's bookmark reset sweeps it -- including in
  the projectless case, where a reload still wipes the bookmarks.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem

from pgtp_editor.lint.findings import LINT_AUDIT_TARGET
from pgtp_editor.ui.ddl_object_editor import DdlObjectRef
from pgtp_editor.ui.main_window import MainWindow
from tests.ui._menu_helpers import find_action, find_top_menu

_LINE = Qt.ItemDataRole.UserRole
_TARGET = Qt.ItemDataRole.UserRole + 1
_EXTRA = Qt.ItemDataRole.UserRole + 2


def _window(qtbot, tmp_path):
    window = MainWindow(generator_config_dir=tmp_path)
    qtbot.addWidget(window)
    return window


def _rows(window):
    audit = window.audit_panel
    return [audit.item(row) for row in range(audit.count())]


def _texts(window):
    return [item.text() for item in _rows(window)]


def _list(window):
    """Trigger the real menu action, not the method, so the wiring is covered."""
    menu = find_top_menu(window, "Navigation")
    find_action(menu, "List All Bookmarks").trigger()


# --- Row grammar + payload --------------------------------------------------


def test_rows_follow_find_alls_grammar_and_carry_its_two_roles(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    editor = window.center_stage.xml_editor
    editor.setPlainText("alpha\n  beta  \ngamma")
    editor.toggle_bookmark(0)
    editor.toggle_bookmark(1)

    _list(window)

    assert _texts(window) == [
        "[Bookmark] line 1: alpha",
        "[Bookmark] line 2: beta",
        "[Bookmark] 2 bookmark(s)",
    ]
    first, second, summary = _rows(window)
    # 1-based, like `[Find]`'s rows and every `navigate_to_line` consumer.
    assert (first.data(_LINE), first.data(_TARGET)) == (1, "raw")
    assert (second.data(_LINE), second.data(_TARGET)) == (2, "raw")
    # The trailing count row is roles-less, so clicking it is a no-op.
    assert summary.data(_LINE) is None


def test_a_blank_line_renders_as_just_the_line_number(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    editor = window.center_stage.xml_editor
    editor.setPlainText("alpha\n   \ngamma")
    editor.toggle_bookmark(1)

    _list(window)

    assert _texts(window)[0] == "[Bookmark] line 2"


def test_the_empty_case_is_a_rolesless_row_and_a_status_message(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    messages = []
    window.statusBar().showMessage = lambda msg, *a, **k: messages.append(msg)
    window.center_stage.xml_editor.setPlainText("alpha\nbeta")

    _list(window)

    assert _texts(window) == ["[Bookmark] no bookmarks in Raw XML"]
    assert _rows(window)[0].data(_LINE) is None
    assert messages == ["No bookmarks in Raw XML."]


def test_a_listing_reports_its_count_in_the_status_bar(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    messages = []
    window.statusBar().showMessage = lambda msg, *a, **k: messages.append(msg)
    editor = window.center_stage.xml_editor
    editor.setPlainText("alpha\nbeta")
    editor.toggle_bookmark(0)

    _list(window)

    assert messages == ["1 bookmark(s) in Raw XML"]


# --- Scope: the active editor -----------------------------------------------


def test_it_lists_the_active_xsd_editor_with_the_xsd_discriminator(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    stage = window.center_stage
    # setPlainText below marks the XSD tab dirty; silence the teardown close
    # prompt so it never reaches a real modal (CLAUDE.md testing policy).
    window._xsd_ui.confirm_close = lambda: "discard"
    stage.show_edit_xsd()
    stage.setCurrentIndex(stage.xsd_tab_index)
    stage.xsd_editor.setPlainText("<xsd:schema/>\n<second/>")
    stage.xsd_editor.toggle_bookmark(1)
    window.center_stage.xml_editor.toggle_bookmark(0)  # the OTHER editor

    _list(window)

    # Only the active editor's bookmark, tagged for the XSD click route.
    assert _texts(window) == ["[Bookmark] line 2: <second/>", "[Bookmark] 1 bookmark(s)"]
    assert _rows(window)[0].data(_TARGET) == "xsd"


def test_a_ddl_object_tab_row_carries_its_ref_key_tuple(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    ref = DdlObjectRef(kind="function", schema="pr", name="recalc")
    panel = window.center_stage.open_ddl_object_tab(ref, "one\ntwo")
    panel.editor.toggle_bookmark(1)

    _list(window)

    row = _rows(window)[0]
    assert row.data(_TARGET) == ref.key
    assert isinstance(row.data(_TARGET), tuple)  # §18.5 D3a's routing shape
    assert row.data(_LINE) == 2


def test_a_php_tab_row_carries_the_php_target_and_its_tab_key(qtbot, tmp_path):
    """The router's PHP branch reads the tab key off `UserRole+2`; reusing "the
    discriminator the router understands" therefore means both halves, or every
    PHP row would be inert."""
    window = _window(qtbot, tmp_path)
    path = tmp_path / "hooks.php"
    path.write_text("<?php\n$a = 1;\n", encoding="utf-8")
    tab = window.center_stage.open_php_file_tab(path, "<?php\n$a = 1;\n")
    tab.editor.toggle_bookmark(1)

    _list(window)

    row = _rows(window)[0]
    assert row.data(_TARGET) == LINT_AUDIT_TARGET
    assert row.data(_EXTRA) == window.center_stage.php_file_tab_key(tab)


# --- The unroutable editors: roles-less and inert ---------------------------


def test_the_ddl_explorer_buffer_gets_rolesless_rows(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    stage = window.center_stage
    stage.show_ddl_explorer()
    stage.setCurrentIndex(stage.ddl_tab_index)
    stage.ddl_editor_panel.editor.setPlainText("one\ntwo")
    stage.ddl_editor_panel.editor.toggle_bookmark(1)

    _list(window)

    row = _rows(window)[0]
    assert row.text() == "[Bookmark] line 2: two"
    assert row.data(_LINE) is None and row.data(_TARGET) is None
    assert _texts(window)[-1] == "[Bookmark] 1 bookmark(s)"


def test_a_draft_fragment_tab_gets_rolesless_rows(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    draft = window.center_stage.open_draft_fragment_tab("trigger", "pr.equipment", "x\ny")
    draft.editor.toggle_bookmark(0)

    _list(window)

    assert _rows(window)[0].data(_LINE) is None


def test_clicking_an_unroutable_row_navigates_nothing(qtbot, tmp_path):
    """The whole point of roles-less: the router's fallback branch is Raw XML, so
    a routed row here would jump to the wrong document."""
    window = _window(qtbot, tmp_path)
    stage = window.center_stage
    stage.xml_editor.setPlainText("raw one\nraw two\nraw three")
    stage.show_ddl_explorer()
    stage.setCurrentIndex(stage.ddl_tab_index)
    stage.ddl_editor_panel.editor.setPlainText("one\ntwo\nthree")
    stage.ddl_editor_panel.editor.toggle_bookmark(2)
    _list(window)

    window._on_audit_item_clicked(_rows(window)[0])

    assert stage.currentIndex() == stage.ddl_tab_index  # never yanked to Raw XML
    assert stage.xml_editor.textCursor().blockNumber() == 0


def test_clicking_a_raw_xml_row_navigates_that_line(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    stage = window.center_stage
    stage.xml_editor.setPlainText("one\ntwo\nthree")
    stage.xml_editor.toggle_bookmark(2)
    _list(window)

    window._on_audit_item_clicked(_rows(window)[0])

    assert stage.currentIndex() == stage.raw_xml_tab_index
    assert stage.xml_editor.textCursor().blockNumber() == 2


# --- Clearing, the dock, and staleness --------------------------------------


def test_repeat_listings_replace_and_leave_other_prefixes_alone(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.audit_panel.addItem(QListWidgetItem("[Find] line 9: kept"))
    window.audit_panel.addItem(QListWidgetItem("[Validate] WARNING: kept"))
    editor = window.center_stage.xml_editor
    editor.setPlainText("one\ntwo\nthree")
    editor.toggle_bookmark(0)
    _list(window)
    editor.toggle_bookmark(2)

    _list(window)

    assert _texts(window) == [
        "[Find] line 9: kept",
        "[Validate] WARNING: kept",
        "[Bookmark] line 1: one",
        "[Bookmark] line 3: three",
        "[Bookmark] 2 bookmark(s)",
    ]


def test_listing_reveals_a_hidden_audit_dock(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    window.center_stage.xml_editor.setPlainText("one\ntwo")
    window.center_stage.xml_editor.toggle_bookmark(0)
    window.audit_dock.setVisible(False)
    assert window.audit_dock.isHidden()

    _list(window)

    assert not window.audit_dock.isHidden()


def test_a_document_load_sweeps_the_stale_rows_projectless(qtbot, tmp_path):
    """The wipe case that persistence does NOT cover: with no project open a
    reload still empties the bookmark set, so the listing must go with it."""
    window = _window(qtbot, tmp_path)
    window.audit_panel.addItem(QListWidgetItem("[Find] line 9: kept"))
    editor = window.center_stage.xml_editor
    editor.setPlainText("one\ntwo\nthree")
    editor.toggle_bookmark(1)
    _list(window)
    assert any(text.startswith("[Bookmark] ") for text in _texts(window))

    editor.setPlainText("one\ntwo\nthree")  # the reload

    assert editor.bookmarked_lines() == []
    assert _texts(window) == ["[Find] line 9: kept"]


def test_toggling_a_bookmark_does_not_resync_the_rows(qtbot, tmp_path):
    """A snapshot, deliberately -- not a live view."""
    window = _window(qtbot, tmp_path)
    editor = window.center_stage.xml_editor
    editor.setPlainText("one\ntwo")
    editor.toggle_bookmark(0)
    _list(window)

    editor.toggle_bookmark(1)

    assert _texts(window) == ["[Bookmark] line 1: one", "[Bookmark] 1 bookmark(s)"]


def test_the_command_has_no_shortcut(qtbot, tmp_path):
    """Matching Clear All Bookmarks: this produces a report, and F2 / Shift+F2
    already own stepping."""
    window = _window(qtbot, tmp_path)
    menu = find_top_menu(window, "Navigation")

    action = find_action(menu, "List All Bookmarks")

    assert action.shortcut().isEmpty()
