# tests/sql/test_caret_context.py
"""Tests for pgtp_editor.sql.caret_context -- the Qt-free caret-context
resolver behind schema-aware Ctrl+Space completion (spec §18.6)."""
from pgtp_editor.sql.caret_context import (
    DOTTED_PATH,
    ROW_VARIABLE,
    resolve_caret_context,
)


def _pos(text: str, marker: str) -> int:
    """The 0-based offset right after `marker` in `text` (test convenience:
    mirrors where a caret sits right after typing `marker`)."""
    index = text.index(marker)
    return index + len(marker)


def test_bare_identifier_prefix():
    text = "select * from equ"
    ctx = resolve_caret_context(text, _pos(text, "equ"))
    assert ctx.kind == DOTTED_PATH
    assert ctx.parts == ()
    assert ctx.prefix == "equ"


def test_caret_mid_word_uses_prefix_up_to_caret():
    text = "select * from equipment"
    pos = text.index("equipment") + 3  # caret after "equ" of "equipment"
    ctx = resolve_caret_context(text, pos)
    assert ctx.kind == DOTTED_PATH
    assert ctx.parts == ()
    assert ctx.prefix == "equ"


def test_schema_dot_no_table_yet():
    text = "select * from pr."
    ctx = resolve_caret_context(text, len(text))
    assert ctx.kind == DOTTED_PATH
    assert ctx.parts == ("pr",)
    assert ctx.prefix == ""


def test_schema_dot_partial_table():
    text = "select * from pr.equ"
    ctx = resolve_caret_context(text, len(text))
    assert ctx.kind == DOTTED_PATH
    assert ctx.parts == ("pr",)
    assert ctx.prefix == "equ"


def test_schema_table_dot_column_prefix():
    text = "select pr.equipment.ta"
    ctx = resolve_caret_context(text, len(text))
    assert ctx.kind == DOTTED_PATH
    assert ctx.parts == ("pr", "equipment")
    assert ctx.prefix == "ta"


def test_new_dot_prefix_is_row_variable_context():
    text = "begin\n  new.na"
    ctx = resolve_caret_context(text, len(text))
    assert ctx.kind == ROW_VARIABLE
    assert ctx.row_variable == "NEW"
    assert ctx.prefix == "na"


def test_new_dot_no_prefix_yet():
    text = "begin\n  new."
    ctx = resolve_caret_context(text, len(text))
    assert ctx.kind == ROW_VARIABLE
    assert ctx.row_variable == "NEW"
    assert ctx.prefix == ""


def test_old_dot_prefix_is_row_variable_context():
    text = "if old.status"
    pos = text.index("status") + 3
    ctx = resolve_caret_context(text, pos)
    assert ctx.kind == ROW_VARIABLE
    assert ctx.row_variable == "OLD"
    assert ctx.prefix == "sta"


def test_row_variable_match_is_case_insensitive():
    text = "New."
    ctx = resolve_caret_context(text, len(text))
    assert ctx.kind == ROW_VARIABLE
    assert ctx.row_variable == "NEW"


def test_caret_inside_string_literal_is_unresolvable():
    text = "select 'abc' "
    pos = text.index("abc") + 1
    assert resolve_caret_context(text, pos) is None


def test_caret_inside_dollar_quoted_body_is_unresolvable():
    text = "$$body text here$$"
    pos = text.index("body")
    assert resolve_caret_context(text, pos) is None


def test_caret_inside_line_comment_is_unresolvable():
    text = "-- a comment\n"
    pos = text.index("comment")
    assert resolve_caret_context(text, pos) is None


def test_caret_right_after_whitespace_offers_bare_context():
    text = "select * from "
    ctx = resolve_caret_context(text, len(text))
    assert ctx.kind == DOTTED_PATH
    assert ctx.parts == ()
    assert ctx.prefix == ""


def test_three_part_path_does_not_treat_middle_as_row_variable():
    """Only a lone NEW/OLD segment triggers row-variable context -- a
    schema literally named `new` qualifying a real table is still a dotted
    path (defensive: real caller data always keys NEW/OLD alone)."""
    text = "select new.equipment.co"
    ctx = resolve_caret_context(text, len(text))
    assert ctx.kind == DOTTED_PATH
    assert ctx.parts == ("new", "equipment")
    assert ctx.prefix == "co"
