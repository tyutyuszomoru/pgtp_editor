"""The formatter under a non-default `FormatConfig` (spec §18.4 A+B). Pure, no Qt.

Three things are being pinned here, and only the first is "does the knob work":

1. keyword casing changes **keyword tokens and nothing else** -- identifiers,
   built-in types/functions, literals and every opaque region are byte-exact;
2. the headline invariant in FQ-033's exact form -- the output's non-whitespace
   tokens are the input's, identical **except keyword casing**, and byte-exact
   under the default;
3. **idempotence for every reachable config**, casing included, because a
   formatter whose output is not a fixed point of its own rules does its damage
   on the second invocation.

Plus the negative half: the rules §18.4 fixes on purpose stay fixed, and no
config reaches the refusal gate.
"""
from __future__ import annotations

import pytest

from pgtp_editor.sql import DEFAULT_FORMAT_CONFIG, FormatConfig, format_selection
from pgtp_editor.sql.format_config import CLAUSE_STARTERS, ClauseRule, KeywordCase
from pgtp_editor.sql.tokenizer import tokenize

TRIGGER_FUNCTION = """
create or replace function audit.log_change() returns trigger language plpgsql as $$
declare
v_user text := current_user;
begin
if tg_op = 'DELETE' then
insert into audit.log (who, what, "Old") values (v_user, tg_table_name, old.id);
elsif tg_op = 'UPDATE' then
insert into audit.log (who, what) values (v_user, tg_table_name);
else
raise notice 'ignored %', tg_op;
end if;
return null;
exception
when others then
raise warning 'audit failed: %', sqlerrm;
return null;
end;
$$;
"""

SELECT_STATEMENT = (
    "select t.id, t.name, count(*) as n from public.thing t "
    "left outer join public.other o on o.thing_id = t.id "
    "where t.name like 'Select%' group by t.id, t.name having count(*) > 1 "
    "order by t.name limit 10;"
)

LOOP_BODY = """
begin
for r in select id from t loop
if r.id % 2 = 0 then
continue;
end if;
perform do_thing(r.id);
end loop;
end;
"""

CORPUS = [TRIGGER_FUNCTION, SELECT_STATEMENT, LOOP_BODY, "where a = 1", ", b, c", ";"]

#: A representative spread of the reachable config space -- casing on both ways,
#: a tab unit, breaks switched off, indents pushed to the maximum, and the JOIN
#: phrase flag both ways.
CONFIGS = [
    DEFAULT_FORMAT_CONFIG,
    FormatConfig(keyword_case=KeywordCase.UPPER),
    FormatConfig(keyword_case=KeywordCase.LOWER),
    FormatConfig(indent_unit="\t", keyword_case=KeywordCase.UPPER),
    FormatConfig(indent_unit="  ", clause_rules={"on": ClauseRule(break_before=False)}),
    FormatConfig(clause_rules={key: ClauseRule(break_before=False) for key in CLAUSE_STARTERS}),
    FormatConfig(clause_rules={key: ClauseRule(indent_levels=4) for key in CLAUSE_STARTERS}),
    FormatConfig(join_phrase_break=False, keyword_case=KeywordCase.UPPER),
    FormatConfig(
        indent_unit="  ",
        keyword_case=KeywordCase.LOWER,
        clause_rules={"where": ClauseRule(indent_levels=1), "join": ClauseRule(break_before=False)},
        join_phrase_break=False,
    ),
]


def significant(text):
    return [tok for tok in tokenize(text) if not tok.is_trivia]


def token_texts(text):
    return [tok.text for tok in significant(text)]


def fmt(text, config=DEFAULT_FORMAT_CONFIG):
    result = format_selection(text, config=config)
    assert result.ok, [issue.message for issue in result.issues]
    return result.text


# --------------------------------------------------------------------------
# A. Keyword casing
# --------------------------------------------------------------------------


def test_as_is_is_byte_identical_to_the_engines_default():
    for text in CORPUS:
        assert fmt(text) == fmt(text, FormatConfig(keyword_case=KeywordCase.AS_IS))


@pytest.mark.parametrize("case", [KeywordCase.UPPER, KeywordCase.LOWER])
def test_casing_touches_keyword_tokens_and_nothing_else(case):
    """The machine-checkable form of FQ-033's headline invariant."""
    for text in CORPUS:
        out = fmt(text, FormatConfig(keyword_case=case))
        before, after = significant(text), significant(out)
        assert len(before) == len(after)
        for old, new in zip(before, after):
            assert old.kind == new.kind
            if old.keyword is not None:
                assert new.text == (old.text.upper() if case is KeywordCase.UPPER else old.text.lower())
                assert new.keyword == old.keyword  # still the same keyword
            else:
                assert new.text == old.text, (old.kind, old.text, new.text)


def test_under_the_default_the_stricter_old_invariant_still_holds_literally():
    for text in CORPUS:
        out = fmt(text)
        assert "".join(out.split()) == "".join(text.split())


def test_opaque_regions_are_never_cased():
    text = (
        "select \"Select\" as \"From\", 'select from where' as s, $tag$ select 1 $tag$ as d "
        "-- select from\nfrom t /* select */;"
    )
    out = fmt(text, FormatConfig(keyword_case=KeywordCase.UPPER))
    assert '"Select"' in out and '"From"' in out
    assert "'select from where'" in out
    assert "$tag$ select 1 $tag$" in out
    assert "-- select from" in out
    assert "/* select */" in out


def test_identifiers_types_and_functions_are_never_cased():
    # `text` here is a built-in type and `count` a built-in function -- neither is
    # in SQL_KEYWORDS, and §18.4 A rejects casing them outright: the formatter is
    # offline, so it cannot know a bare word is not a case-sensitive quoted
    # identifier's unquoted twin.
    out = fmt("select count(Thing.Id)::text as MyName from Public.Thing;",
              FormatConfig(keyword_case=KeywordCase.UPPER))
    assert "count(Thing.Id)::text" in out
    assert "MyName" in out
    assert "Public.Thing" in out
    assert out.startswith("SELECT")


def test_casing_survives_a_keyword_spelled_every_way():
    for spelling in ("select", "SELECT", "Select", "sElEcT"):
        assert fmt(f"{spelling} 1", FormatConfig(keyword_case=KeywordCase.UPPER)) == "SELECT 1"
        assert fmt(f"{spelling} 1", FormatConfig(keyword_case=KeywordCase.LOWER)) == "select 1"


# --------------------------------------------------------------------------
# The hard constraint: idempotence for every reachable config
# --------------------------------------------------------------------------


@pytest.mark.parametrize("config", CONFIGS, ids=range(len(CONFIGS)))
def test_formatting_is_idempotent_for_every_reachable_config(config):
    for text in CORPUS:
        once = format_selection(text, config=config)
        assert once.ok, [issue.message for issue in once.issues]
        twice = format_selection(once.text, config=config)
        assert twice.ok
        assert twice.text == once.text, (config, text)


@pytest.mark.parametrize("case", [KeywordCase.UPPER, KeywordCase.LOWER])
def test_idempotence_holds_specifically_with_casing_on(case):
    config = FormatConfig(keyword_case=case)
    for text in CORPUS:
        once = fmt(text, config)
        assert fmt(once, config) == once
        # And casing is a function of set membership, not of current spelling:
        # re-casing already-cased text is a no-op even under the other setting's
        # output.
        other = KeywordCase.LOWER if case is KeywordCase.UPPER else KeywordCase.UPPER
        assert fmt(fmt(text, FormatConfig(keyword_case=other)), config) == once


@pytest.mark.parametrize("config", CONFIGS, ids=range(len(CONFIGS)))
def test_a_clause_indent_never_walks_the_block_rightwards(config):
    # The first emitted line takes no per-clause extra indent, because
    # `format_selection` re-applies the selection's first content line's
    # indentation to every output line -- so indenting it would make pass 2 read
    # that as the new base. This is the pass-3 check of that guard.
    for text in CORPUS:
        once = fmt(text, config)
        assert fmt(fmt(once, config), config) == once


# --------------------------------------------------------------------------
# B. Break / indent rules
# --------------------------------------------------------------------------


def test_a_clause_starter_with_break_off_stays_on_the_line():
    config = FormatConfig(
        clause_rules={
            "from": ClauseRule(break_before=False),
            "where": ClauseRule(break_before=False),
        }
    )
    assert fmt("select a from t where b = 1", config) == "select a from t where b = 1"
    # ...and the unconfigured starters still break.
    assert fmt("select a from t order by b", config) == "select a from t\norder by b"


def test_break_off_still_honours_an_author_newline():
    # Author line breaks are preserved wherever no rule applies, and switching a
    # rule off does not license the formatter to JOIN lines the author split.
    config = FormatConfig(clause_rules={"from": ClauseRule(break_before=False)})
    assert fmt("select a\nfrom t", config) == "select a\nfrom t"


def test_per_clause_indent_pushes_the_clause_right():
    config = FormatConfig(
        clause_rules={"from": ClauseRule(indent_levels=1), "where": ClauseRule(indent_levels=2)}
    )
    assert fmt("select a from t where b = 1", config) == (
        "select a\n    from t\n        where b = 1"
    )


def test_per_clause_indent_uses_the_configured_unit():
    config = FormatConfig(indent_unit="  ", clause_rules={"from": ClauseRule(indent_levels=1)})
    assert fmt("select a from t", config) == "select a\n  from t"


def test_the_selections_first_line_is_never_pushed_right():
    config = FormatConfig(clause_rules={"select": ClauseRule(indent_levels=3)})
    out = fmt("select a from t", config)
    assert out.startswith("select a")
    assert fmt(out, config) == out


def test_join_phrase_break_off_keeps_the_whole_phrase_on_one_line():
    config = FormatConfig(join_phrase_break=False)
    assert fmt("select a from t left outer join u on u.id = t.id", config) == (
        "select a\nfrom t left outer join u\non u.id = t.id"
    )
    # On by default the phrase breaks once, at its first prefix word.
    assert fmt("select a from t left outer join u on u.id = t.id") == (
        "select a\nfrom t\nleft outer join u\non u.id = t.id"
    )


def test_a_bare_join_follows_its_own_clause_rule_not_the_phrase_flag():
    inline_join = FormatConfig(clause_rules={"join": ClauseRule(break_before=False)})
    assert fmt("select a from t join u on u.id = t.id", inline_join) == (
        "select a\nfrom t join u\non u.id = t.id"
    )


# --------------------------------------------------------------------------
# The rules §18.4 fixes ON PURPOSE stay fixed
# --------------------------------------------------------------------------

#: Everything a config can switch off, switched off at once.
ALL_BREAKS_OFF = FormatConfig(
    clause_rules={key: ClauseRule(break_before=False) for key in CLAUSE_STARTERS},
    join_phrase_break=False,
    keyword_case=KeywordCase.UPPER,
)


def test_no_config_appends_anything_to_a_line_comment():
    out = fmt("select 1 -- note\nselect 2", ALL_BREAKS_OFF)
    assert out.splitlines()[0].endswith("-- note")


def test_no_config_removes_the_break_after_a_semicolon():
    out = fmt("select 1; select 2;", ALL_BREAKS_OFF)
    assert out.splitlines() == ["SELECT 1;", "SELECT 2;"]


def test_no_config_removes_the_declare_header_break():
    # THE sharp one: the plpgsql declaration section is told from
    # `DECLARE ... CURSOR` BY LAYOUT, so a config that could join this line would
    # make pass 2 read a different construct -- and possibly refuse text the
    # formatter itself produced.
    out = fmt("declare\nx int;\nbegin\nx := 1;\nend;", ALL_BREAKS_OFF)
    assert out.splitlines()[0].strip() == "DECLARE"
    assert fmt(out, ALL_BREAKS_OFF) == out


def test_no_config_removes_the_breaks_before_block_keywords():
    out = fmt("begin if a then x := 1; else x := 2; end if; end;", ALL_BREAKS_OFF)
    assert out.splitlines() == [
        "BEGIN",
        "    IF a THEN",
        "        x := 1;",
        "    ELSE",
        "        x := 2;",
        "    END IF;",
        "END;",
    ]


@pytest.mark.parametrize("config", CONFIGS, ids=range(len(CONFIGS)))
def test_no_config_reaches_the_refusal_gate(config):
    for text in ("begin x := 1;", "select (1", "if a then x := 1; end loop;", "select 'unclosed"):
        result = format_selection(text, config=config)
        assert not result.ok, text
        assert result.text == text  # verbatim, whatever the config asked for
        assert result.issues and all(issue.fatal for issue in result.issues)


@pytest.mark.parametrize("config", CONFIGS, ids=range(len(CONFIGS)))
def test_empty_and_whitespace_only_selections_are_untouched(config):
    for text in ("", "   ", "\n\n", "\t"):
        result = format_selection(text, config=config)
        assert (result.ok, result.text, result.issues) == (True, text, [])


def test_leading_comma_style_survives_every_config():
    text = "select a\n, b\n, c\nfrom t"
    for config in CONFIGS:
        assert fmt(text, config).count(", b") == 1
