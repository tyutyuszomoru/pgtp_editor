# tests/sql/test_templates.py
"""Tests for `pgtp_editor.sql.templates` -- the one template/snippet engine
behind both expand-SELECT and keyword snippets (spec §18.6, FQ-030 slice 2)."""
import pytest

from pgtp_editor.sql.templates import (
    DEFAULT_SNIPPETS,
    Expansion,
    Snippet,
    expand_template,
    find_snippet,
    render,
)


# --- plain text ------------------------------------------------------------


def test_a_template_without_markup_is_inserted_verbatim():
    exp = expand_template("RETURN NEW;")
    assert exp.text == "RETURN NEW;"
    assert exp.stops == ()
    assert exp.caret == len("RETURN NEW;")


def test_an_empty_template_is_a_refusal_with_a_reason():
    exp = expand_template("")
    assert not exp
    assert exp.reason


def test_expansion_is_falsy_when_not_ok_and_apply_is_a_no_op():
    exp = Expansion(reason="nope")
    assert not exp
    assert exp.apply("select 1") == "select 1"


# --- tab stops -------------------------------------------------------------


def test_numbered_stops_are_visited_in_order_with_the_final_caret_last():
    exp = expand_template("a{{2}}b{{0}}c{{1}}")
    assert [stop.number for stop in exp.stops] == [1, 2, 0]


def test_a_stop_with_no_placeholder_is_an_empty_span_at_its_position():
    exp = expand_template("IF {{1}} THEN")
    stop = exp.stops[0]
    assert exp.text == "IF  THEN"
    assert stop.start == stop.end == len("IF ")


def test_a_placeholder_is_inserted_and_spanned_by_its_stop():
    exp = expand_template("IF {{1:condition}} THEN")
    stop = exp.stops[0]
    assert exp.text == "IF condition THEN"
    assert exp.text[stop.start : stop.end] == "condition"
    assert stop.placeholder == "condition"


def test_the_caret_lands_on_the_final_stop():
    exp = expand_template("BEGIN\n  {{0}}\nEND;")
    assert exp.text[: exp.caret] == "BEGIN\n  "


def test_without_a_final_stop_the_caret_is_at_the_end_of_the_insertion():
    exp = expand_template("IF {{1:c}} THEN")
    assert exp.caret == len(exp.text)


def test_stop_offsets_are_absolute_in_the_buffer():
    buffer = "begin\n\nend;"
    exp = expand_template("IF {{1:c}} THEN {{0}}", at=6)
    assert exp.apply(buffer) == "begin\nIF c THEN \nend;"
    assert exp.apply(buffer)[exp.stops[0].start : exp.stops[0].end] == "c"
    assert exp.apply(buffer)[: exp.caret].endswith("IF c THEN ")


def test_a_replacement_span_rewrites_rather_than_inserts():
    buffer = "select foo from t"
    exp = expand_template("{{1:bar}}", at=7, end=10)
    assert exp.apply(buffer) == "select bar from t"


def test_end_before_start_is_clamped_rather_than_inverted():
    exp = expand_template("x", at=10, end=2)
    assert exp.start == exp.end == 10


# --- value substitution ----------------------------------------------------


def test_named_values_are_substituted():
    exp = expand_template("{{greet}} {{who}}", values={"greet": "hi", "who": "you"})
    assert exp.text == "hi you"


def test_a_missing_value_falls_back_rather_than_failing():
    exp = expand_template("{{who:world}}", values={})
    assert exp.text == "world"
    assert exp.ok


def test_a_missing_value_with_no_fallback_is_empty():
    assert expand_template("[{{who}}]").text == "[]"


def test_a_value_is_never_rescanned_as_markup():
    exp = expand_template("{{cols}}", values={"cols": "{{1:not a stop}}"})
    assert exp.text == "{{1:not a stop}}"
    assert exp.stops == ()


def test_values_and_stops_coexist_and_offsets_account_for_the_values():
    exp = expand_template("{{a}} where {{0}}", values={"a": "select j.id"})
    assert exp.text == "select j.id where "
    assert exp.caret == len(exp.text)


# --- degradation -----------------------------------------------------------


def test_a_doubled_brace_escapes_a_literal_one():
    assert expand_template("{{{{1}}").text == "{{1}}"


def test_an_unclosed_marker_is_emitted_verbatim():
    exp = expand_template("select {{1:oops")
    assert exp.text == "select {{1:oops"
    assert exp.ok


def test_non_markup_between_braces_is_emitted_verbatim():
    exp = expand_template("array{{1, 2}}")
    assert exp.text == "array{{1, 2}}"
    assert exp.stops == ()


def test_dollar_quoting_passes_through_untouched():
    """The reason the syntax is `{{n}}` and not `$n` at all."""
    body = "AS $$\nBEGIN\n  RETURN $1;\nEND;\n$$;"
    assert expand_template(body).text == body


@pytest.mark.parametrize(
    "template",
    ["{{", "}}", "{{}}", "{{:}}", "{{-1}}", "{{1", "{{{{{{", "{{ 1 }}", "{{99}}"],
)
def test_odd_templates_never_raise(template):
    assert expand_template(template).ok


def test_render_is_just_the_text():
    assert render("IF {{1:c}} THEN") == "IF c THEN"


# --- the shipped snippet set -----------------------------------------------


def test_the_default_set_covers_the_constructs_fq_030_names():
    prefixes = {snippet.prefix for snippet in DEFAULT_SNIPPETS}
    assert {"case", "forloop", "if", "begin", "raise", "cursor", "trigfn"} <= prefixes


def test_every_default_snippet_expands_and_declares_a_final_caret():
    for snippet in DEFAULT_SNIPPETS:
        exp = expand_template(snippet.template)
        assert exp.ok, snippet.prefix
        assert any(stop.is_final for stop in exp.stops), snippet.prefix
        assert "{{" not in exp.text, snippet.prefix


def test_case_expands_to_a_full_case_expression():
    exp = expand_template(find_snippet("case").template)
    assert exp.text.startswith("CASE WHEN condition THEN result")
    assert exp.text.rstrip().endswith("END")


def test_the_trigger_skeleton_keeps_its_dollar_quotes():
    text = expand_template(find_snippet("trigfn").template).text
    assert "AS $$" in text and text.rstrip().endswith("$$;")


def test_snippet_lookup_is_case_insensitive():
    assert find_snippet("CASE").prefix == "case"
    assert find_snippet(" if ").prefix == "if"


def test_an_unknown_word_is_not_a_snippet():
    assert find_snippet("jobcard") is None
    assert find_snippet("") is None


def test_a_custom_snippet_set_can_be_searched_without_forking_the_engine():
    mine = (Snippet("hi", "greeting", "hello {{0}}"),)
    assert find_snippet("hi", mine).template == "hello {{0}}"
    assert find_snippet("case", mine) is None
