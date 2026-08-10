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

# tests/ui/test_editor_gutter_body_numbers.py
"""FQ-031: the gutter's optional body-relative (AS-anchored) second column.

Two things are being protected here, and the second one matters more than the
first. The first is that the column is *right*: the numbers it paints are the
ones `plpgsql_check` and PostgreSQL print, which is the whole point of showing
them. The second is that the column is **absent** — in width, in geometry and
pixel for pixel — for every editor that never asks for it, because
`GutterBookmarkFoldMixin` is shared by the Raw XML editor, the PHP tabs, the SQL
console and the DDL Explorer buffer, and none of them has a routine body.
"""
from __future__ import annotations

import pytest

from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication, QPlainTextEdit

from pgtp_editor.db.ddl_check import body_line_offset, map_lineno
from pgtp_editor.ui.editor_gutter import (
    _BODY_COLUMN_GAP,
    _BOOKMARK_STRIP_WIDTH,
    _FOLD_GLYPH_WIDTH,
    GutterBookmarkFoldMixin,
)


class _Host(GutterBookmarkFoldMixin, QPlainTextEdit):
    """The smallest possible carrier of the shared mixin — deliberately not
    `CodeEditor`/`XmlEditor`, so what is asserted below is the mixin's own
    behavior and not some host's."""

    def __init__(self) -> None:
        super().__init__()
        self._init_gutter_bookmarks_folding()


#: `pg_get_functiondef`-shaped output: three header lines, the `AS $function$`
#: opener on line 4, and a body under it.
FUNCTIONDEF = (
    "CREATE OR REPLACE FUNCTION pr.bump(a integer)\n"
    " RETURNS integer\n"
    " LANGUAGE plpgsql\n"
    "AS $function$\n"
    "BEGIN\n"
    "  RETURN a + 1;\n"
    "END\n"
    "$function$\n"
)


def _editor(qtbot, text: str = "") -> _Host:
    editor = _Host()
    qtbot.addWidget(editor)
    if text:
        editor.setPlainText(text)
    editor.resize(400, 300)
    # Force the layout pass, so the gutter widget has its real geometry before
    # anything below compares painted images.
    editor.show()
    QApplication.processEvents()
    return editor


def _baseline_width(editor: _Host) -> int:
    """The gutter width formula as it stood BEFORE FQ-031 — re-derived here on
    purpose, so a change to the enabled path that leaked into the disabled one
    fails loudly instead of being re-baselined."""
    digits = len(str(max(1, editor.blockCount())))
    return (
        digits * editor.fontMetrics().horizontalAdvance("9")
        + _BOOKMARK_STRIP_WIDTH
        + _FOLD_GLYPH_WIDTH
        + 6
    )


def _gutter_image(editor: _Host) -> QImage:
    image = QImage(editor._gutter.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    editor._gutter.render(image)
    return image


def _painted_numbers(editor: _Host, monkeypatch) -> list[str]:
    """Every string the gutter's paint pass draws, in paint order."""
    drawn: list[str] = []
    original = QPainter.drawText

    def spy(self, *args):
        if args and isinstance(args[-1], str):
            drawn.append(args[-1])
        return original(self, *args)

    monkeypatch.setattr(QPainter, "drawText", spy)
    image = QImage(editor._gutter.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    editor._gutter.render(image)
    return drawn


# --- Off by default, and costing nothing ----------------------------------

def test_body_column_is_off_by_default(qtbot):
    editor = _editor(qtbot, FUNCTIONDEF)
    assert editor.body_line_anchor() is None
    assert editor._body_number_column_width() == 0
    assert all(editor.body_relative_line(n) is None for n in range(editor.blockCount()))


def test_disabled_gutter_width_is_the_pre_feature_width(qtbot):
    """No anchor, not one pixel wider — the Raw XML / PHP / console guarantee."""
    for text in ("", "one line", FUNCTIONDEF, "x\n" * 500):
        editor = _editor(qtbot, text)
        assert editor._gutter_width() == _baseline_width(editor)
        assert editor.viewportMargins().left() == _baseline_width(editor)


def test_disabled_gutter_paints_only_absolute_numbers(qtbot, monkeypatch):
    editor = _editor(qtbot, FUNCTIONDEF)
    assert _painted_numbers(editor, monkeypatch) == [
        str(n) for n in range(1, editor.blockCount() + 1)
    ]


def test_enabling_then_clearing_restores_the_gutter_pixel_for_pixel(qtbot):
    editor = _editor(qtbot, FUNCTIONDEF)
    before = _gutter_image(editor)
    editor.set_body_line_anchor(4)
    editor.set_body_line_anchor(None)
    assert editor._gutter_width() == _baseline_width(editor)
    assert _gutter_image(editor) == before


def test_a_new_document_turns_the_column_back_off(qtbot):
    """A stale anchor would misnumber every line, which is worse than no
    column at all — so `setPlainText` clears it and the host re-sets it."""
    editor = _editor(qtbot, FUNCTIONDEF)
    editor.set_body_line_anchor(4)
    assert editor.body_line_anchor() == 4
    editor.setPlainText("SELECT 1;\n")
    assert editor.body_line_anchor() is None
    assert editor._gutter_width() == _baseline_width(editor)


# --- The anchor convention -------------------------------------------------

def test_anchor_is_body_line_offsets_own_number(qtbot):
    """The seam passes `body_line_offset`'s value straight through — no
    arithmetic at the call site, and line `L` reads body-relative 1."""
    editor = _editor(qtbot, FUNCTIONDEF)
    editor.set_body_line_anchor_from_text(FUNCTIONDEF)
    anchor = body_line_offset(FUNCTIONDEF)
    assert anchor == 4
    assert editor.body_line_anchor() == anchor
    # 0-based block `anchor - 1` is absolute line `anchor`, and it is body 1.
    assert editor.body_relative_line(anchor - 1) == 1


def test_body_numbers_are_the_inverse_of_map_lineno(qtbot):
    """The number shown beside a line is exactly the number plpgsql would print
    for it: `map_lineno` maps back onto the same absolute line."""
    editor = _editor(qtbot, FUNCTIONDEF)
    editor.set_body_line_anchor_from_text(FUNCTIONDEF)
    real_lines = len(FUNCTIONDEF.splitlines())
    for block in range(real_lines):
        relative = editor.body_relative_line(block)
        if relative is None:
            continue
        assert map_lineno(FUNCTIONDEF, relative) == block + 1


def test_header_lines_have_no_body_number(qtbot, monkeypatch):
    """Blank, never a dash or a 0: anything printed there would read as a line
    number plpgsql could name, and no line above `AS` has one."""
    editor = _editor(qtbot, FUNCTIONDEF)
    editor.set_body_line_anchor_from_text(FUNCTIONDEF)
    assert [editor.body_relative_line(n) for n in range(3)] == [None, None, None]
    # The trailing newline of `pg_get_functiondef` output gives a 9th, empty
    # block; it is under the anchor, so it is numbered like any other body line.
    painted = _painted_numbers(editor, monkeypatch)
    assert painted == [
        "1", "2", "3",
        "4", "1",
        "5", "2",
        "6", "3",
        "7", "4",
        "8", "5",
        "9", "6",
    ]


def test_no_locatable_opener_leaves_the_column_off(qtbot):
    """A `LANGUAGE sql` body, a table, a plain SQL buffer: `body_line_offset`
    answers None and nothing is guessed."""
    text = "CREATE FUNCTION pr.one() RETURNS integer\n LANGUAGE sql\n RETURN 1;\n"
    editor = _editor(qtbot, text)
    editor.set_body_line_anchor_from_text(text)
    assert body_line_offset(text) is None
    assert editor.body_line_anchor() is None
    assert editor._gutter_width() == _baseline_width(editor)


@pytest.mark.parametrize("anchor", [0, -3, None, True])
def test_a_nonsense_anchor_is_refused_rather_than_renumbering(qtbot, anchor):
    editor = _editor(qtbot, FUNCTIONDEF)
    editor.set_body_line_anchor(anchor)
    assert editor.body_line_anchor() is None


# --- Shapes the real world produces ---------------------------------------

def test_one_line_body(qtbot, monkeypatch):
    text = (
        "CREATE OR REPLACE FUNCTION pr.nothing()\n"
        " RETURNS void\n"
        " LANGUAGE plpgsql\n"
        "AS $$BEGIN END$$\n"
    )
    editor = _editor(qtbot, text)
    editor.set_body_line_anchor_from_text(text)
    assert editor.body_line_anchor() == 4
    assert editor.body_relative_line(3) == 1
    assert _painted_numbers(editor, monkeypatch) == [
        "1", "2", "3", "4", "1", "5", "2",
    ]


def test_unterminated_body_still_numbers_to_the_end(qtbot):
    """A routine being typed: the closing `$$` is not there yet. The anchor is
    the OPENER, so the numbering is complete without it."""
    text = (
        "CREATE OR REPLACE FUNCTION pr.wip()\n"
        " RETURNS void\n"
        " LANGUAGE plpgsql\n"
        "AS $$\n"
        "BEGIN\n"
        "  RAISE NOTICE 'hi';\n"
    )
    editor = _editor(qtbot, text)
    editor.set_body_line_anchor_from_text(text)
    assert editor.body_line_anchor() == 4
    last = editor.blockCount() - 1
    assert editor.body_relative_line(last) == editor.blockCount() - 3


def test_a_dollar_quote_inside_a_line_comment_is_not_the_anchor(qtbot):
    """`body_line_offset` strips line comments; the gutter inherits that rather
    than re-deciding where a body starts."""
    text = (
        "CREATE OR REPLACE FUNCTION pr.c()\n"
        "-- a $$ in a comment is not the body\n"
        " LANGUAGE plpgsql\n"
        "AS $$\n"
        "BEGIN END\n"
        "$$\n"
    )
    editor = _editor(qtbot, text)
    editor.set_body_line_anchor_from_text(text)
    assert editor.body_line_anchor() == body_line_offset(text) == 4


# --- Enabled geometry ------------------------------------------------------

def test_enabled_gutter_grows_by_exactly_the_body_column_plus_the_gap(qtbot):
    editor = _editor(qtbot, FUNCTIONDEF)
    baseline = _baseline_width(editor)
    editor.set_body_line_anchor(4)
    digit = editor.fontMetrics().horizontalAdvance("9")
    # 9 blocks, anchor 4 -> largest body number is 6: one digit.
    assert editor._body_number_column_width() == digit
    assert editor._gutter_width() == baseline + digit + _BODY_COLUMN_GAP
    assert editor.viewportMargins().left() == editor._gutter_width()
    assert editor._gutter.width() == editor._gutter_width()


def test_body_column_is_sized_from_the_largest_body_number(qtbot):
    text = "header\n" * 3 + "AS $$\n" + "  x\n" * 120
    editor = _editor(qtbot, text)
    editor.set_body_line_anchor_from_text(text)
    digit = editor.fontMetrics().horizontalAdvance("9")
    # The body runs past 100 lines while the absolute count needs 3 digits too.
    assert editor._body_number_column_width() == 3 * digit


def test_the_body_number_is_dimmer_than_the_absolute_one(qtbot):
    """Two numbers in one column only work if one of them is visibly
    secondary."""
    editor = _editor(qtbot, FUNCTIONDEF)
    primary = editor._gutter_fg_color
    secondary = editor._body_number_color()
    assert secondary != primary
    background = editor._gutter_bg_color

    def distance(color):
        return abs(color.red() - background.red()) + abs(
            color.green() - background.green()
        ) + abs(color.blue() - background.blue())

    assert distance(secondary) < distance(primary)


def test_enabled_gutter_actually_paints_a_second_column(qtbot):
    editor = _editor(qtbot, FUNCTIONDEF)
    off = _gutter_image(editor)
    editor.set_body_line_anchor(4)
    on = _gutter_image(editor)
    assert on.size() != off.size()
    assert on != off
