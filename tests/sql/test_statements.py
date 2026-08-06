"""§18.5 D4's statement splitter and classifier (`pgtp_editor/sql/statements.py`).

The splitter is where correctness is load-bearing: a `;` inside a routine body,
a string or a comment must never split a statement, and the offsets/lines must
survive a multi-line dollar-quoted body -- that is what lets the console say
*which* statement aborted a Run.
"""
from __future__ import annotations

import pytest

from pgtp_editor.db.apply import line_of_position
from pgtp_editor.sql.statements import (
    CHANGES_OBJECTS,
    Statement,
    classify_statement,
    split_statements,
)


def texts(sql: str) -> list[str]:
    return [stmt.text for stmt in split_statements(sql)]


# --------------------------------------------------------------------------
# split_statements -- the basics
# --------------------------------------------------------------------------

def test_two_plain_statements_split_on_the_semicolon():
    assert texts("select 1; select 2;") == ["select 1", "select 2"]


@pytest.mark.parametrize("sql", ["", "   ", "\n\n\t", ";", ";;\n;"])
def test_blank_and_semicolon_only_input_yields_nothing(sql):
    assert split_statements(sql) == []


def test_comment_only_fragments_are_dropped():
    sql = "-- header\nselect 1;\n-- trailing note\n/* and a block */\n"
    stmts = split_statements(sql)
    assert [s.text for s in stmts] == ["-- header\nselect 1"]
    assert stmts[0].terminated is True


def test_trailing_statement_without_a_semicolon_is_returned_unterminated():
    stmts = split_statements("select 1;\nselect 2")
    assert [s.text for s in stmts] == ["select 1", "select 2"]
    assert [s.terminated for s in stmts] == [True, False]


def test_terminated_is_a_fact_not_inferred_from_being_last():
    (only,) = split_statements("select 1;\n")
    assert only.terminated is True


# --------------------------------------------------------------------------
# split_statements -- semicolons that must not split
# --------------------------------------------------------------------------

def test_semicolon_inside_a_single_quoted_string_does_not_split():
    assert texts("select 'a;b';") == ["select 'a;b'"]


def test_doubled_quote_escape_inside_a_string_does_not_end_it_early():
    assert texts("select 'it''s; fine' , 2;") == ["select 'it''s; fine' , 2"]


def test_semicolon_inside_an_escape_string_does_not_split():
    # E'...' honors backslash escapes: the \' is not a terminator, so the ; is
    # still inside the literal.
    assert texts(r"select E'a\';b'; select 2;") == [r"select E'a\';b'", "select 2"]


def test_semicolon_inside_a_double_quoted_identifier_does_not_split():
    assert texts('select 1 as "we;ird";') == ['select 1 as "we;ird"']


def test_semicolon_in_a_line_comment_does_not_split():
    sql = "select 1 -- and now; a comment\n, 2;"
    assert texts(sql) == ["select 1 -- and now; a comment\n, 2"]


def test_semicolon_in_a_nested_block_comment_does_not_split():
    sql = "select /* outer; /* inner; */ still outer; */ 1; select 2;"
    assert texts(sql) == ["select /* outer; /* inner; */ still outer; */ 1", "select 2"]


PLPGSQL_BODY = """\
create or replace function public.f(a int) returns int as $$
declare
    total int := 0;
begin
    total := a + 1;
    if total > 10 then
        raise notice 'big: %', total;
    end if;
    return total;
end;
$$ language plpgsql;
select 2;
"""


def test_a_plpgsql_body_in_dollar_quotes_stays_one_statement():
    stmts = split_statements(PLPGSQL_BODY)
    assert len(stmts) == 2
    assert stmts[0].text.startswith("create or replace function")
    assert stmts[0].text.endswith("$$ language plpgsql")
    assert stmts[0].text.count(";") == 6  # every internal semicolon preserved
    assert stmts[1].text == "select 2"


def test_a_tagged_dollar_quoted_body_stays_one_statement():
    sql = (
        "create function g() returns void as $body$\n"
        "begin\n  perform 1;\n  perform 2;\nend;\n"
        "$body$ language plpgsql;\nselect 3;"
    )
    stmts = split_statements(sql)
    assert len(stmts) == 2
    assert "$body$" in stmts[0].text and stmts[0].text.count(";") == 3
    assert stmts[1].text == "select 3"


def test_nested_differently_tagged_dollar_quotes_nest_correctly():
    sql = (
        "create function h() returns void as $outer$\n"
        "begin\n"
        "  execute $inner$ select 1; select 2; $inner$;\n"
        "end;\n"
        "$outer$ language plpgsql;\n"
        "select 'after';"
    )
    stmts = split_statements(sql)
    assert len(stmts) == 2
    assert stmts[0].text.startswith("create function h()")
    assert "$inner$ select 1; select 2; $inner$" in stmts[0].text
    assert stmts[1].text == "select 'after'"


def test_an_unterminated_dollar_quote_is_never_split_in_half():
    sql = "create function broken() as $$\nbegin\n  perform 1;\n"
    stmts = split_statements(sql)
    assert len(stmts) == 1
    # The unterminated region runs to the end of the buffer, trailing newline
    # included -- that newline is inside the opaque token, not around it.
    assert stmts[0].text.endswith("perform 1;\n")
    assert stmts[0].terminated is False


def test_a_bare_dollar_parameter_is_not_a_dollar_quote_opener():
    assert texts("select $1; select $2;") == ["select $1", "select $2"]


# --------------------------------------------------------------------------
# split_statements -- offsets and lines
# --------------------------------------------------------------------------

def test_offsets_and_lines_are_correct_after_a_multiline_dollar_body():
    stmts = split_statements(PLPGSQL_BODY)
    first, second = stmts

    assert first.start == 0
    assert first.start_line == 1
    assert first.start_col == 1
    assert PLPGSQL_BODY[first.start : first.end] == first.text

    # `select 2;` is the 12th line of the buffer (11 lines of function above it).
    assert second.start_line == 12
    assert second.start_col == 1
    assert PLPGSQL_BODY[second.start : second.end] == second.text
    assert PLPGSQL_BODY[second.end] == ";"


def test_start_col_points_at_the_first_character_of_an_indented_statement():
    sql = "select 1;\n    select 2;"
    _, second = split_statements(sql)
    assert (second.start, second.start_line, second.start_col) == (14, 2, 5)


def test_slices_round_trip_for_every_statement():
    sql = PLPGSQL_BODY + "\n-- tail\nupdate t set a = 'x;y' where b = 1;\nselect 9"
    for stmt in split_statements(sql):
        assert sql[stmt.start : stmt.end] == stmt.text


def test_line_offset_composes_with_apply_line_of_position():
    """A failure position inside statement N maps back to the buffer's line."""
    stmts = split_statements(PLPGSQL_BODY)
    second = stmts[1]
    # position 1 = first character of the statement we sent.
    assert line_of_position(second.text, 1) == 1
    assert second.line_offset + line_of_position(second.text, 1) == 12

    first = stmts[0]
    inner = first.text.index("raise notice") + 1  # 1-based position
    assert first.line_offset + line_of_position(first.text, inner) == 7


def test_statement_texts_feed_apply_ddl_shaped_sequences():
    """The documented adapter: index alignment with ApplyOutcome.statement_index."""
    stmts = split_statements(PLPGSQL_BODY + "update t set a = 1;")
    sequence = [s.text for s in stmts]
    assert all(isinstance(text, str) for text in sequence)

    # A hypothetical ApplyOutcome(statement_index=2) attributes back by index.
    failed_index = 2
    assert sequence[failed_index] == stmts[failed_index].text
    assert stmts[failed_index].text.startswith("update t")
    assert stmts[failed_index].start_line == 13


def test_statement_is_immutable_pure_data():
    (only,) = split_statements("select 1")
    assert isinstance(only, Statement)
    with pytest.raises(Exception):
        only.text = "nope"  # type: ignore[misc]


# --------------------------------------------------------------------------
# classify_statement
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "sql",
    [
        "select 1",
        "SELECT * FROM t",
        "values (1), (2)",
        "table public.t",
        "show search_path",
        "explain select * from t",
        "explain (costs off) delete from t",  # plans only, never executes
    ],
)
def test_read_statements(sql):
    assert classify_statement(sql) == "read"


@pytest.mark.parametrize(
    "sql",
    [
        "insert into t values (1)",
        "UPDATE t SET a = 1",
        "delete from t where a = 1",
        "merge into t using s on t.a = s.a when matched then do nothing",
        "truncate t",
    ],
)
def test_write_statements(sql):
    assert classify_statement(sql) == "write"


@pytest.mark.parametrize(
    "sql",
    [
        "create table t (a int)",
        "CREATE OR REPLACE FUNCTION f() RETURNS void AS $$ begin end $$ LANGUAGE plpgsql",
        "alter table t add column b int",
        "drop function f()",
        "grant select on t to someone",
        "revoke select on t from someone",
        "comment on table t is 'hi'",
        "security label for selinux on table t is 'x'",
        "refresh materialized view mv",
    ],
)
def test_ddl_statements(sql):
    assert classify_statement(sql) == "ddl"


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "   \n\t",
        "-- only a comment",
        "/* only a block comment */",
        "do $$ begin perform 1; end $$",
        "DO LANGUAGE plpgsql $$ begin end $$",
        "call my_proc(1)",
        "copy t from stdin",
        "vacuum analyze t",
        "analyze t",
        "lock table t",
        "set search_path to public",
        "(select 1) union (select 2)",  # opens with punctuation
        "'a string'",
        "wibble something",  # not a recognized leader
    ],
)
def test_unknown_statements(sql):
    assert classify_statement(sql) == "unknown"


def test_with_ending_in_select_is_a_read():
    assert classify_statement("with x as (select 1 as a) select * from x") == "read"


def test_with_recursive_select_is_a_read():
    sql = "WITH RECURSIVE r AS (select 1 union all select 2) SELECT * FROM r"
    assert classify_statement(sql) == "read"


def test_with_ending_in_delete_is_not_a_read():
    sql = "with x as (select id from t) delete from u where id in (select id from x)"
    assert classify_statement(sql) == "write"


def test_with_a_data_modifying_cte_is_a_write():
    sql = "with moved as (delete from t returning *) insert into u select * from moved"
    assert classify_statement(sql) == "write"


@pytest.mark.parametrize(
    "sql",
    [
        "explain analyze select * from t",
        "EXPLAIN ANALYSE SELECT * FROM t",
        "explain (analyze, buffers) delete from t",
    ],
)
def test_explain_analyze_actually_executes_so_it_is_unknown(sql):
    assert classify_statement(sql) == "unknown"


def test_leading_comments_are_skipped_before_the_keyword():
    sql = "-- a note\n/* and a block; */\n  select 1"
    assert classify_statement(sql) == "read"


def test_a_statement_from_the_splitter_keeps_its_leading_comment_classifiable():
    (only,) = split_statements("-- header\ncreate table t (a int);")
    assert only.text.startswith("-- header")
    assert classify_statement(only.text) == "ddl"


def test_classification_never_guesses_toward_read():
    """Anything unplaceable lands in the set that gates the confirmation."""
    for sql in ["do $$ begin end $$", "call p()", "", "explain analyze select 1"]:
        assert classify_statement(sql) in CHANGES_OBJECTS


def test_changes_objects_is_ddl_and_unknown():
    assert CHANGES_OBJECTS == {"ddl", "unknown"}


def test_run_gate_over_a_mixed_buffer():
    """The console's actual question: does this Run change objects?"""
    buffer = "select 1;\nupdate t set a = 2;\ncreate index i on t (a);"
    kinds = [classify_statement(s.text) for s in split_statements(buffer)]
    assert kinds == ["read", "write", "ddl"]
    assert any(kind in CHANGES_OBJECTS for kind in kinds)

    harmless = "select 1;\ninsert into t values (1);"
    kinds = [classify_statement(s.text) for s in split_statements(harmless)]
    assert not any(kind in CHANGES_OBJECTS for kind in kinds)
