"""Signature help (`pgtp_editor/sql/signature_help.py`) -- FQ-030 slice 3.

A query, not an insertion: these tests assert on the reported argument index
and the matched parameter, never on inserted text. Signatures are injected the
way the UI pass will inject them -- from `RoutineInfo.args` pairs.
"""
from __future__ import annotations

import pytest

from pgtp_editor.sql.signature_help import (
    Parameter,
    RoutineSignature,
    find_call_site,
    routine_signature,
    signature_help,
)

CALC = routine_signature(
    "hr.calc", [("amount", "numeric"), ("rate", "numeric"), ("label", "text")], "numeric"
)


def _caret(text: str, marker: str = "|") -> tuple[str, int]:
    pos = text.index(marker)
    return text[:pos] + text[pos + 1 :], pos


def _at(fixture: str, signatures=(CALC,)):
    text, pos = _caret(fixture)
    return signature_help(find_call_site(text, pos), signatures)


# --- which argument the caret is on ---------------------------------------


@pytest.mark.parametrize(
    "fixture,index",
    [
        ("SELECT hr.calc(|)", 0),
        ("SELECT hr.calc(1|)", 0),
        ("SELECT hr.calc(1,|)", 1),
        ("SELECT hr.calc(1, 2|)", 1),
        ("SELECT hr.calc(1, 2, |)", 2),
        ("SELECT hr.calc(1, 2, 'x'|)", 2),
        ("SELECT hr.calc(1, 2, 'x')|", None),
    ],
)
def test_the_active_parameter_follows_the_caret_across_the_argument_list(
    fixture, index
):
    help_ = _at(fixture)
    if index is None:
        assert not help_  # past the closing paren: no longer inside the call
        return
    assert help_
    assert help_.active_parameter == index
    assert help_.parameter == CALC.parameters[index]


def test_the_active_parameter_reports_its_name_and_type():
    help_ = _at("SELECT hr.calc(1, |")
    assert help_.parameter == Parameter(name="rate", type_text="numeric")
    assert help_.parameter.label == "rate numeric"
    assert help_.label == (
        "hr.calc(amount numeric, rate numeric, label text) RETURNS numeric"
    )


def test_an_unqualified_call_matches_a_qualified_signature():
    assert _at("SELECT calc(1, |2)").signature is CALC


def test_a_call_qualified_with_another_schema_does_not_match():
    help_ = _at("SELECT sales.calc(1, |2)")
    assert not help_
    assert "sales.calc" in help_.reason


def test_a_call_naming_nothing_known_says_so_without_raising():
    help_ = _at("SELECT hr.unknown(|)")
    assert not help_
    assert help_.reason
    assert help_.parameter is None


# --- nested calls ----------------------------------------------------------


INNER = routine_signature("hr.helper", [("a", "int"), ("b", "int")])


def test_a_nested_call_reports_the_inner_routine_and_its_own_index():
    help_ = _at("SELECT hr.calc(1, hr.helper(7, |", (CALC, INNER))
    assert help_.signature is INNER
    assert help_.active_parameter == 1


def test_the_outer_call_resumes_after_the_nested_one_closes():
    help_ = _at("SELECT hr.calc(1, hr.helper(7, 8), |", (CALC, INNER))
    assert help_.signature is CALC
    assert help_.active_parameter == 2


def test_commas_inside_a_nested_call_do_not_advance_the_outer_index():
    site = find_call_site(*_caret("SELECT hr.calc(1, hr.helper(7, 8|)"))
    assert site.name == "helper"
    assert site.argument_index == 1


def test_a_grouping_paren_is_not_mistaken_for_a_call():
    help_ = _at("SELECT hr.calc(1, (2 + 3)|")
    assert help_.signature is CALC
    assert help_.active_parameter == 1


def test_a_comma_inside_a_type_modifier_belongs_to_that_paren():
    help_ = _at("SELECT hr.calc(1, cast(x as numeric(12,2))|")
    assert help_.active_parameter == 1


def test_a_bare_paren_group_with_no_callee_is_not_a_call():
    site = find_call_site(*_caret("SELECT (1, |2)"))
    assert not site
    assert site.reason


def test_a_keyword_is_never_a_callee():
    for fixture in ("SELECT * FROM t WHERE a IN (1, |2)", "INSERT INTO t VALUES (1, |2)"):
        assert not find_call_site(*_caret(fixture))


# --- a caret inside a string argument -------------------------------------


def test_a_caret_inside_a_string_argument_stays_on_that_argument():
    help_ = _at("SELECT hr.calc(1, 2, 'a, b, c|')")
    assert help_.active_parameter == 2
    assert help_.parameter.name == "label"


def test_a_comma_inside_a_string_never_advances_the_index():
    help_ = _at("SELECT hr.calc('a, b, c', |")
    assert help_.active_parameter == 1


def test_the_literal_flag_is_reported_for_a_caret_inside_a_string():
    site = find_call_site(*_caret("SELECT hr.calc(1, 'x|y')"))
    assert site.in_literal is True
    assert find_call_site(*_caret("SELECT hr.calc(1, x|y)")).in_literal is False


def test_a_comma_inside_a_comment_is_not_a_separator():
    help_ = _at("SELECT hr.calc(1 /* one, two */, |")
    assert help_.active_parameter == 1


# --- argument spans and statement scoping ---------------------------------


def test_every_argument_is_reported_as_a_trimmed_span():
    text, pos = _caret("SELECT hr.calc(  1 ,  'x, y' , z|)")
    site = find_call_site(text, pos)
    assert [argument.text_in(text) for argument in site.arguments] == [
        "1",
        "'x, y'",
        "z",
    ]
    assert site.argument_count == 3
    assert text[site.name_start : site.name_end] == "hr.calc"
    assert text[site.open_paren] == "("
    assert text[site.close_paren] == ")"


def test_an_empty_argument_list_counts_no_arguments():
    site = find_call_site(*_caret("SELECT hr.calc(|)"))
    assert site.argument_count == 0
    assert site.arguments[0].start == site.arguments[0].end


def test_a_stray_open_paren_in_an_earlier_statement_cannot_reach_the_caret():
    assert not find_call_site(*_caret("SELECT f( ;\nSELECT 1|"))


def test_a_caret_inside_a_routine_body_resolves_the_bodys_own_call():
    text, pos = _caret(
        "CREATE FUNCTION f() RETURNS int LANGUAGE plpgsql AS $$\n"
        "BEGIN\n"
        "  PERFORM hr.calc(1, |2);\n"
        "END;\n"
        "$$;"
    )
    site = find_call_site(text, pos)
    assert site.qualified == "hr.calc"
    assert site.argument_index == 1
    # Offsets are rebased into the original buffer, not the body.
    assert text[site.name_start : site.name_end] == "hr.calc"


def test_a_quoted_callee_is_unwrapped_for_matching_but_kept_verbatim():
    text, pos = _caret('SELECT "HR"."Calc"(1, |2)')
    site = find_call_site(text, pos)
    assert site.schema == "HR"
    assert site.name == "Calc"
    assert site.callee == '"HR"."Calc"'
    assert signature_help(site, [routine_signature("HR.Calc", [("a", "int")])])


# --- overloads -------------------------------------------------------------


ONE = routine_signature("hr.f", [("a", "int")])
TWO = routine_signature("hr.f", [("a", "int"), ("b", "text")])


def test_every_overload_is_returned_with_the_arity_that_fits_first():
    help_ = _at("SELECT hr.f(1, |", (ONE, TWO))
    assert len(help_.signatures) == 2
    assert help_.signature is TWO
    assert help_.too_many_arguments is False


def test_a_caret_past_every_overloads_last_parameter_says_so():
    help_ = _at("SELECT hr.f(1, 2, |", (ONE, TWO))
    assert help_
    assert help_.too_many_arguments is True
    assert help_.parameter is None


def test_a_variadic_parameter_absorbs_every_further_argument():
    variadic = RoutineSignature(
        "hr.pack",
        (Parameter("head", "text"), Parameter("rest", "text", mode="variadic")),
    )
    help_ = _at("SELECT hr.pack('a', 'b', 'c', |", (variadic,))
    assert help_.too_many_arguments is False
    assert help_.parameter.name == "rest"


def test_a_variadic_mode_written_into_the_type_is_recognized():
    built = routine_signature("hr.pack", [("rest", "VARIADIC text[]")])
    assert built.parameters[0].mode == "variadic"
    assert built.parameters[0].type_text == "text[]"
    assert built.is_variadic is True


def test_a_zero_parameter_signature_renders_empty_parens():
    assert routine_signature("hr.now", [], "timestamptz").label == (
        "hr.now() RETURNS timestamptz"
    )


def test_an_unnamed_parameter_falls_back_to_its_type_alone():
    assert routine_signature("hr.f", [("", "int")]).label == "hr.f(int)"


# --- malformed input degrades ---------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "",
        "(((",
        ")))",
        "SELECT hr.calc(",
        "SELECT hr.calc('unterminated",
        "SELECT hr.calc(1, /* unclosed",
        "$$ SELECT hr.calc(1,",
        ",,,,",
        "hr.calc()",
    ],
)
def test_malformed_input_never_raises_at_any_caret(text):
    for pos in range(len(text) + 1):
        site = find_call_site(text, pos)
        help_ = signature_help(site, [CALC])
        assert isinstance(help_.reason, str)
        if site:
            assert 0 <= site.argument_index < max(1, len(site.arguments))


def test_a_caller_may_hand_over_tokens_it_already_has():
    from pgtp_editor.sql.tokenizer import tokenize

    text, pos = _caret("SELECT hr.calc(1, |2)")
    tokens = tokenize(text)
    assert find_call_site(text, pos, tokens=tokens) == find_call_site(text, pos)


def test_help_for_a_refused_site_carries_the_sites_reason():
    site = find_call_site("SELECT 1", 8)
    assert signature_help(site, [CALC]).reason == site.reason
