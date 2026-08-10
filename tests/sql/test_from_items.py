# tests/sql/test_from_items.py
"""Tests for `pgtp_editor.sql.from_clause.analyze_from_items` -- the span-carrying
sibling of `analyze_from_scope` that rewriting needs (spec §18.6, FQ-030 slice 1).

The one thing that breaks silently here is an offset that is off by a character
or rebased wrongly, so every span assertion below is written as a slice of the
ORIGINAL buffer compared to the expected text -- never as a bare number.
"""
import pytest

from pgtp_editor.sql.from_clause import (
    FromItems,
    TableRef,
    analyze_from_items,
    analyze_from_scope,
)


def _only(text, pos=None):
    located = analyze_from_items(text, len(text) if pos is None else pos)
    assert len(located.items) == 1, located.items
    return located.items[0]


# --- spans are exact against the original buffer ---------------------------


def test_name_span_slices_the_verbatim_table_reference():
    text = "select * from hr.jobcard jc where jc."
    item = _only(text)
    assert text[item.name_start : item.name_end] == "hr.jobcard"
    assert item.name_text(text) == "hr.jobcard"


def test_item_span_covers_the_alias_too():
    text = "select * from hr.jobcard jc where jc."
    item = _only(text)
    assert text[item.start : item.end] == "hr.jobcard jc"


def test_item_span_covers_an_as_alias():
    text = "select * from hr.jobcard as jc"
    item = _only(text)
    assert text[item.start : item.end] == "hr.jobcard as jc"


def test_introducer_span_is_the_from_keyword_verbatim():
    text = "SELECT * FROM hr.jobcard"
    item = _only(text)
    assert text[item.introducer_start : item.introducer_end] == "FROM"
    assert item.introducer == "from"


def test_join_items_carry_their_own_join_keyword():
    text = "select * from hr.a a left join hr.b b on a.id = b.a_id"
    located = analyze_from_items(text, len(text))
    kinds = [item.introducer for item in located.items]
    assert kinds == ["from", "join"]
    joined = located.items[1]
    assert text[joined.introducer_start : joined.introducer_end] == "join"
    assert text[joined.name_start : joined.name_end] == "hr.b"


def test_update_items_carry_the_update_keyword():
    text = "update hr.jobcard jc set x = 1"
    item = _only(text)
    assert item.introducer == "update"
    assert text[item.name_start : item.name_end] == "hr.jobcard"


def test_spans_survive_a_leading_statement_offset():
    """Offsets are absolute in the buffer, not relative to the statement."""
    text = "select 1; select * from hr.jobcard jc"
    item = _only(text)
    assert item.start > text.index(";")
    assert text[item.name_start : item.name_end] == "hr.jobcard"


def test_spans_are_rebased_out_of_a_dollar_quoted_body():
    text = (
        "create function f() returns int language plpgsql as $$\n"
        "begin\n"
        "  select * from hr.jobcard jc;\n"
        "end;\n"
        "$$"
    )
    caret = text.index("jc;") + 2
    item = _only(text, caret)
    assert text[item.name_start : item.name_end] == "hr.jobcard"
    assert text[item.start : item.end] == "hr.jobcard jc"


def test_quoted_identifiers_are_sliced_with_their_quotes():
    text = 'select * from "HR"."Job Card" jc'
    item = _only(text)
    assert text[item.name_start : item.name_end] == '"HR"."Job Card"'
    # ...while the parsed ref stays unquoted, as it always did.
    assert item.ref == TableRef(
        schema="HR", table="Job Card", alias="jc", name="jc"
    )


def test_spaces_around_the_dot_are_preserved_by_the_span():
    text = "select * from hr . jobcard"
    item = _only(text)
    assert text[item.name_start : item.name_end] == "hr . jobcard"
    assert item.ref.qualified == "hr.jobcard"


def test_a_derived_item_spans_its_group():
    text = "select * from (select 1) sub"
    item = _only(text)
    assert item.ref.is_derived
    assert text[item.name_start : item.name_end] == "(select 1)"
    assert text[item.start : item.end] == "(select 1) sub"


def test_a_function_call_item_spans_the_call():
    text = "select * from generate_series(1, 10) g"
    item = _only(text)
    assert item.ref.is_derived
    assert text[item.name_start : item.name_end] == "generate_series(1, 10)"


# --- clause landmarks ------------------------------------------------------


def test_select_and_where_landmarks_are_located():
    text = "select * from hr.jobcard jc where jc.id = 1"
    located = analyze_from_items(text, len(text))
    select = located.clause("select")
    where = located.clause("where")
    assert text[select.start : select.end] == "select"
    assert text[where.start : where.end] == "where"


def test_clause_keyword_keeps_its_verbatim_casing():
    text = "SELECT * FROM hr.jobcard"
    assert analyze_from_items(text, len(text)).clause("select").text == "SELECT"


def test_clause_after_ignores_an_earlier_occurrence():
    text = "select * from hr.jobcard jc where jc.id = 1"
    located = analyze_from_items(text, len(text))
    item = located.items[0]
    assert located.clause_after(item.end, "where") is not None
    assert located.clause_after(len(text), "where") is None


def test_a_missing_clause_is_none_not_an_error():
    text = "select * from hr.jobcard"
    assert analyze_from_items(text, len(text)).clause("where") is None


def test_an_inner_scopes_where_does_not_leak_outward():
    text = "select * from hr.a a where a.id in (select b.id from hr.b b where b.x)"
    located = analyze_from_items(text, len("select * from hr.a a "))
    # The outer caret sees the outer WHERE only; the inner one is nested deeper.
    wheres = [c for c in located.clauses if c.word == "where"]
    assert len(wheres) == 1


# --- the projection stays identical to the shipped entry point -------------


@pytest.mark.parametrize(
    "text",
    [
        "select * from hr.jobcard jc where jc.",
        "select * from hr.a a join hr.b b on a.id = b.a_id where b.",
        "update hr.jobcard jc set x = 1 where jc.",
        "select * from (select 1) sub where sub.",
        "select * from hr.a a where a.id in (select b.id from hr.b b where b.)",
        "",
        "   ",
        "select",
        "select * from",
        "select * from hr.",
    ],
)
def test_scope_projection_matches_analyze_from_scope(text):
    for pos in range(len(text) + 1):
        assert analyze_from_items(text, pos).scope == analyze_from_scope(text, pos)


def test_statement_span_locates_the_caret_statement():
    text = "select 1; select * from hr.jobcard"
    located = analyze_from_items(text, len(text))
    assert text[located.statement_start : located.statement_end] == (
        "select * from hr.jobcard"
    )


# --- degradation -----------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "",
        "select",
        "from",
        "select * from",
        "select * from hr.",
        "select * from (",
        "select * from ((((",
        "select * from 'unterminated",
        "select * from /* unterminated",
        "select * from $$ nested $$ x",
        "((((((((((",
        ";;;;;",
        "select * from hr.jobcard jc where jc." * 40,
    ],
)
def test_malformed_input_degrades_to_an_answer_never_an_exception(text):
    for pos in (0, len(text) // 2, len(text)):
        located = analyze_from_items(text, pos)
        assert isinstance(located, FromItems)


def test_out_of_range_positions_are_clamped_not_fatal():
    text = "select * from hr.jobcard"
    assert analyze_from_items(text, -50).scope is not None
    assert analyze_from_items(text, 10_000).items[0].ref.table == "jobcard"


def test_every_span_stays_inside_the_buffer():
    text = (
        "select 1;\n"
        "create function f() returns int language plpgsql as $$\n"
        "begin select * from hr.jobcard jc; end;\n"
        "$$;\n"
    )
    for pos in range(len(text) + 1):
        located = analyze_from_items(text, pos)
        for item in located.items:
            assert 0 <= item.start <= item.end <= len(text)
            assert item.start <= item.name_start <= item.name_end <= item.end
        for clause in located.clauses:
            assert 0 <= clause.start < clause.end <= len(text)
            assert text[clause.start : clause.end].lower() == clause.word
