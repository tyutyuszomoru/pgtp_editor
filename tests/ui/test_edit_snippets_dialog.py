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
"""`ui/edit_snippets_dialog.py` — the Maintenance-mode snippet table (FQ-030).

The dialog never touches the store and never opens a modal, so nothing here
needs a patch: the set goes in, the set comes out. `.exec()` is never called
(the dialog is a non-modal `show()` by design), which is what keeps these tests
inside CLAUDE.md's no-un-patched-modal rule.
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialogButtonBox

from pgtp_editor.sql.templates import DEFAULT_SNIPPETS, Snippet
from pgtp_editor.ui.edit_snippets_dialog import (
    COLUMN_ORIGIN,
    COLUMN_PREFIX,
    COLUMN_TITLE,
    EditSnippetsDialog,
)

MINE = Snippet("upd", "an update", "UPDATE {{1:t}} SET {{0}};")


@pytest.fixture
def dialog(qtbot):
    def build(snippets=DEFAULT_SNIPPETS, **kwargs):
        widget = EditSnippetsDialog(snippets, **kwargs)
        qtbot.addWidget(widget)
        return widget

    return build


def _cell(widget, row, column):
    item = widget.table.item(row, column)
    return None if item is None else item.text()


# -- the table shows the set, and says whose each row is ----------------------


def test_every_snippet_gets_a_row(dialog):
    widget = dialog()
    assert widget.table.rowCount() == len(DEFAULT_SNIPPETS)
    assert _cell(widget, 0, COLUMN_PREFIX) == DEFAULT_SNIPPETS[0].prefix
    assert _cell(widget, 0, COLUMN_TITLE) == DEFAULT_SNIPPETS[0].title


def test_the_origin_column_separates_built_ins_from_the_users_own(dialog):
    widget = dialog((DEFAULT_SNIPPETS[0], MINE))
    assert _cell(widget, 0, COLUMN_ORIGIN) == "built-in"
    assert _cell(widget, 1, COLUMN_ORIGIN) == "yours"


def test_editing_a_built_in_body_re_labels_it_immediately(dialog):
    widget = dialog((DEFAULT_SNIPPETS[0],))
    widget.table.setCurrentCell(0, COLUMN_PREFIX)
    widget.set_body("SOMETHING ELSE")
    assert _cell(widget, 0, COLUMN_ORIGIN) == "built-in, edited"
    assert widget.result_snippets()[0].template == "SOMETHING ELSE"


def test_selecting_a_row_shows_that_snippets_body(dialog):
    widget = dialog((DEFAULT_SNIPPETS[0], MINE))
    widget.table.setCurrentCell(1, COLUMN_PREFIX)
    assert widget.body.toPlainText() == MINE.template


def test_typing_in_the_body_pane_updates_the_selected_row(dialog):
    widget = dialog((DEFAULT_SNIPPETS[0], MINE))
    widget.table.setCurrentCell(1, COLUMN_PREFIX)
    widget.body.setPlainText("DELETE FROM {{0}};")
    assert widget.result_snippets()[1].template == "DELETE FROM {{0}};"
    assert widget.result_snippets()[0] == DEFAULT_SNIPPETS[0]


def test_editing_a_table_cell_updates_the_set(dialog):
    widget = dialog((MINE,))
    widget.table.item(0, COLUMN_PREFIX).setText("  ins  ")
    widget.table.item(0, COLUMN_TITLE).setText("an insert")
    assert widget.result_snippets() == (
        Snippet("ins", "an insert", MINE.template),
    )


# -- add / delete / restore ---------------------------------------------------


def test_add_appends_a_typeable_row_and_selects_it(dialog):
    widget = dialog(())
    row = widget.add_snippet()
    assert row == 0 and widget.table.currentRow() == 0
    assert widget.result_snippets()[0].prefix
    assert widget.validation_error() is None


def test_a_second_add_does_not_collide_with_the_first(dialog):
    widget = dialog(())
    widget.add_snippet()
    widget.add_snippet()
    assert widget.validation_error() is None


def test_delete_removes_the_row_including_a_built_in(dialog):
    widget = dialog(DEFAULT_SNIPPETS)
    widget.table.setCurrentCell(0, COLUMN_PREFIX)
    assert widget.remove_selected() is True
    assert len(widget.result_snippets()) == len(DEFAULT_SNIPPETS) - 1
    assert DEFAULT_SNIPPETS[0] not in widget.result_snippets()


def test_restore_built_ins_appends_only_what_is_missing(dialog):
    widget = dialog((MINE, DEFAULT_SNIPPETS[0]))
    restored = widget.restore_missing_defaults()
    assert set(restored) == set(DEFAULT_SNIPPETS[1:])
    assert widget.result_snippets()[:2] == (MINE, DEFAULT_SNIPPETS[0])


def test_restore_never_reverts_an_edited_built_in(dialog):
    """An edited built-in is the user's snippet now — silently putting ours
    back is the overwrite the whole feature refuses to do."""
    edited = Snippet(DEFAULT_SNIPPETS[0].prefix, "mine now", "MY BODY")
    widget = dialog((edited,))
    widget.restore_missing_defaults()
    assert widget.result_snippets()[0] == edited
    assert widget.result_snippets().count(DEFAULT_SNIPPETS[0]) == 0


def test_restore_says_so_when_there_is_nothing_to_restore(dialog):
    widget = dialog(DEFAULT_SNIPPETS)
    assert widget.restore_missing_defaults() == ()
    assert "already here" in widget.message()


# -- validation ---------------------------------------------------------------


def test_a_blank_trigger_word_blocks_ok_and_says_why(dialog):
    widget = dialog((MINE,))
    widget.table.item(0, COLUMN_PREFIX).setText("")
    widget.button_box.button(QDialogButtonBox.StandardButton.Ok).click()
    assert widget.result() != EditSnippetsDialog.DialogCode.Accepted
    assert "trigger word" in widget.message()


def test_a_duplicate_trigger_word_blocks_ok(dialog):
    widget = dialog((MINE, Snippet("other", "", "x")))
    widget.table.item(1, COLUMN_PREFIX).setText("UPD")
    assert widget.validation_error() is not None
    widget.button_box.button(QDialogButtonBox.StandardButton.Ok).click()
    assert widget.isVisible() is False or widget.result() != (
        EditSnippetsDialog.DialogCode.Accepted
    )


def test_an_unfinished_body_is_never_a_reason_to_refuse(dialog):
    widget = dialog((Snippet("x", "", ""),))
    assert widget.validation_error() is None


def test_ok_accepts_a_valid_set(qtbot, dialog):
    widget = dialog((MINE,))
    with qtbot.waitSignal(widget.accepted, timeout=1000):
        widget.button_box.button(QDialogButtonBox.StandardButton.Ok).click()
    assert widget.result_snippets() == (MINE,)


# -- read-only (the store failed to load) -------------------------------------


def test_read_only_disables_every_mutation_and_saving(dialog):
    widget = dialog(DEFAULT_SNIPPETS, read_only=True, note="broken")
    assert widget.note() == "broken"
    assert widget.button_box.button(
        QDialogButtonBox.StandardButton.Ok
    ).isEnabled() is False
    assert widget.add_button.isEnabled() is False
    assert widget.delete_button.isEnabled() is False
    assert widget.import_button.isEnabled() is False
    assert widget.add_snippet() == -1
    assert widget.remove_row(0) is False
    assert widget.set_body("x", 0) is False
    assert widget.result_snippets() == DEFAULT_SNIPPETS


def test_read_only_still_allows_export(dialog):
    """Sending someone the set that is actually in force is harmless, and is
    sometimes exactly how a user rescues a broken file."""
    widget = dialog(DEFAULT_SNIPPETS, read_only=True)
    assert widget.export_button.isEnabled() is True


# -- the export/import buttons only ANNOUNCE -----------------------------------


def test_export_and_import_buttons_emit_rather_than_act(qtbot, dialog):
    widget = dialog((MINE,))
    with qtbot.waitSignal(widget.export_requested, timeout=1000):
        widget.export_button.click()
    with qtbot.waitSignal(widget.import_requested, timeout=1000):
        widget.import_button.click()
    assert widget.result_snippets() == (MINE,)
