# tests/sql/test_expand_select.py
"""Tests for `pgtp_editor.sql.expand_select` -- expanding a bare
`SELECT FROM hr.jobcard` into a column-listed skeleton (spec §18.6, FQ-030 slice 1).
"""
import pytest

from pgtp_editor.sql.expand_select import (
    derive_alias,
    find_expand_select_site,
    quote_identifier,
    render_expand_select,
)

COLUMNS = ("id", "job", "card")


def _expand(text, pos=None, columns=COLUMNS):
    site = find_expand_select_site(text, len(text) if pos is None else pos)
    return site, render_expand_select(site, columns)


# --- the headline case FQ-030 spells out -----------------------------------


def test_the_worked_example_from_the_queue_entry():
    text = "SELECT FROM hr.jobcard"
    site, exp = _expand(text, pos=7)
    assert site.ok
    result = exp.apply(text)
    assert result == "SELECT j.id, j.job, j.card FROM hr.jobcard j WHERE "
    assert result[: exp.caret] == result  # caret one space after WHERE, at the end


def test_the_final_caret_is_the_only_tab_stop():
    _, exp = _expand("SELECT FROM hr.jobcard")
    assert [stop.number for stop in exp.stops] == [0]
    assert exp.stops[0].start == exp.stops[0].end == exp.caret


def test_expansion_replaces_only_the_region_between_select_and_the_item():
    text = "-- a note\nselect from hr.jobcard;\nselect 2;"
    site, exp = _expand(text, pos=text.index("from"))
    assert text[exp.start : exp.end] == " from hr.jobcard"
    assert exp.apply(text) == (
        "-- a note\nselect j.id, j.job, j.card from hr.jobcard j where ;\nselect 2;"
    )


# --- the typed schema is preserved, never rewritten ------------------------


def test_the_typed_schema_is_re_emitted_verbatim_even_when_it_is_a_typo():
    """FQ-030: `pr.jobcard` stays `pr.jobcard` -- the typo is the user's to see."""
    text = "select from pr.jobcard"
    site, exp = _expand(text)
    assert site.qualified == "pr.jobcard"
    assert exp.apply(text) == "select j.id, j.job, j.card from pr.jobcard j where "


def test_quoting_and_casing_of_the_table_reference_survive():
    text = 'select from "HR"."Job Card"'
    site, exp = _expand(text, columns=("id",))
    assert site.qualified == "HR.Job Card"
    assert exp.apply(text) == 'select j.id from "HR"."Job Card" j where '


def test_spaces_around_the_dot_survive():
    text = "select from hr . jobcard"
    _, exp = _expand(text, columns=("id",))
    assert exp.apply(text) == "select j.id from hr . jobcard j where "


def test_a_bare_table_has_no_index_key_but_still_expands():
    text = "select from jobcard"
    site, exp = _expand(text, columns=("id",))
    assert site.qualified is None  # no schema is ever guessed
    assert exp.apply(text) == "select j.id from jobcard j where "


# --- keyword casing follows what the author typed --------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("SELECT FROM hr.jobcard", "SELECT j.id FROM hr.jobcard j WHERE "),
        ("select from hr.jobcard", "select j.id from hr.jobcard j where "),
        ("Select From hr.jobcard", "Select j.id From hr.jobcard j where "),
    ],
)
def test_generated_where_matches_the_case_of_the_typed_from(text, expected):
    _, exp = _expand(text, columns=("id",))
    assert exp.apply(text) == expected


# --- aliases ---------------------------------------------------------------


def test_an_alias_the_user_already_wrote_is_reused_not_replaced():
    text = "select from hr.jobcard jc"
    site, exp = _expand(text, columns=("id",))
    assert site.alias == "jc" and not site.alias_derived
    assert exp.apply(text) == "select jc.id from hr.jobcard jc where "


def test_an_as_alias_is_reused_with_its_as():
    text = "select from hr.jobcard as jc"
    _, exp = _expand(text, columns=("id",))
    assert exp.apply(text) == "select jc.id from hr.jobcard as jc where "


# --- the alias-collision scheme --------------------------------------------


def test_alias_is_the_first_letter_lowercased():
    assert derive_alias("jobcard") == "j"
    assert derive_alias("Orders") == "o"
    assert derive_alias("job_card") == "j"  # first letter, not an initialism


def test_a_collision_takes_the_next_free_number():
    assert derive_alias("jobcard", ["j"]) == "j2"


def test_the_three_way_collision_keeps_counting():
    assert derive_alias("jobcard", ["j", "j2"]) == "j3"
    assert derive_alias("jobcard", ["j", "j2", "j3"]) == "j4"


def test_collision_matching_is_case_insensitive():
    assert derive_alias("jobcard", ["J"]) == "j2"


def test_gaps_in_the_taken_numbers_are_filled():
    assert derive_alias("jobcard", ["j", "j3"]) == "j2"


def test_a_name_with_no_letter_falls_back_to_t():
    assert derive_alias("1st_try") == "s"  # the first *letter*, wherever it is
    assert derive_alias("_tmp") == "t"
    assert derive_alias("") == "t"
    assert derive_alias("123") == "t"
    assert derive_alias("_tmp", ["t"]) == "t2"


def test_an_alias_never_collides_with_a_sql_keyword():
    alias = derive_alias("as")
    assert alias != "as"
    assert alias.startswith("a")


def test_derive_alias_always_answers_for_any_taken_set():
    taken = [f"j{n}" for n in range(2, 40)] + ["j"]
    assert derive_alias("jobcard", taken) not in {name.lower() for name in taken}


# --- column rendering ------------------------------------------------------


def test_columns_needing_quotes_get_them():
    text = "select from hr.jobcard"
    _, exp = _expand(text, columns=("id", "Mixed Case", "order"))
    assert exp.apply(text) == (
        'select j.id, j."Mixed Case", j."order" from hr.jobcard j where '
    )


def test_no_known_columns_renders_a_star_rather_than_an_empty_list():
    text = "select from hr.jobcard"
    _, exp = _expand(text, columns=())
    assert exp.apply(text) == "select * from hr.jobcard j where "


def test_quote_identifier_rules():
    assert quote_identifier("id") == "id"
    assert quote_identifier("job_id2") == "job_id2"
    assert quote_identifier("Id") == '"Id"'
    assert quote_identifier("select") == '"select"'
    assert quote_identifier('we"ird') == '"we""ird"'
    assert quote_identifier("") == '""'


# --- an existing WHERE is respected ----------------------------------------


def test_an_existing_where_is_not_duplicated():
    text = "select from hr.jobcard where id = 1"
    site, exp = _expand(text, pos=7, columns=("id",))
    assert site.has_where
    assert exp.apply(text) == "select j.id from hr.jobcard j where id = 1"


def test_with_an_existing_where_the_caret_lands_after_the_alias():
    text = "select from hr.jobcard where id = 1"
    _, exp = _expand(text, pos=7, columns=("id",))
    assert exp.apply(text)[: exp.caret] == "select j.id from hr.jobcard j"


# --- refusals state their reason -------------------------------------------


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("select id, job from hr.jobcard", "already lists"),
        ("select * from hr.jobcard", "already lists"),
        ("select from hr.a a, hr.b b", "several tables"),
        ("select from hr.a a join hr.b b on a.id = b.a_id", "several tables"),
        ("select from (select 1) sub", "subquery"),
        ("select 1 + 1", "FROM"),
        ("update hr.jobcard set x = 1", "SELECT"),
        ("", "no statement"),
    ],
)
def test_a_site_that_cannot_expand_says_why(text, fragment):
    site = find_expand_select_site(text, len(text))
    assert not site
    assert fragment.lower() in site.reason.lower(), site.reason


def test_rendering_a_refused_site_is_a_refused_expansion():
    site = find_expand_select_site("select id from hr.jobcard", 25)
    exp = render_expand_select(site, COLUMNS)
    assert not exp
    assert exp.reason == site.reason
    assert exp.apply("select id from hr.jobcard") == "select id from hr.jobcard"


# --- context: bodies, several statements, degradation ----------------------


def test_it_works_inside_a_dollar_quoted_routine_body():
    text = (
        "create function f() returns void language plpgsql as $$\n"
        "begin\n"
        "  select from hr.jobcard;\n"
        "end;\n"
        "$$"
    )
    caret = text.index("select from") + len("select ")
    _, exp = _expand(text, pos=caret, columns=("id",))
    assert "select j.id from hr.jobcard j where ;" in exp.apply(text)


def test_the_right_statement_of_several_is_expanded():
    text = "select 1;\nselect from hr.jobcard;\nselect 3;"
    caret = text.index("hr.jobcard")
    _, exp = _expand(text, pos=caret, columns=("id",))
    assert exp.apply(text) == (
        "select 1;\nselect j.id from hr.jobcard j where ;\nselect 3;"
    )


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "select",
        "select from",
        "select from hr.",
        "select from (",
        "select from 'unterminated",
        "select from $$ x",
        ";;;;",
        "((((",
    ],
)
def test_malformed_input_never_raises_from_either_half(text):
    for pos in (0, len(text) // 2, len(text)):
        site = find_expand_select_site(text, pos)
        exp = render_expand_select(site, COLUMNS)
        assert exp.apply(text) == text or site.ok


def test_every_caret_position_of_a_realistic_buffer_is_safe():
    text = (
        "-- report\n"
        "select 1;\n"
        "select from hr.jobcard;\n"
        "create function f() returns int language plpgsql as $$\n"
        "begin select from hr.other; end;\n"
        "$$;\n"
    )
    for pos in range(len(text) + 1):
        site = find_expand_select_site(text, pos)
        exp = render_expand_select(site, COLUMNS)
        if exp.ok:
            assert 0 <= exp.start <= exp.end <= len(text)
            assert 0 <= exp.caret <= len(exp.apply(text))
