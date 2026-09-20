"""Unit tests for the SQL/plpgsql selection formatter (spec §18.4). Pure, no Qt.

The load-bearing invariants -- token preservation, idempotence, verbatim text on
refusal -- are asserted for every sample in `SAMPLES` as well as individually.
"""
from __future__ import annotations

import unicodedata

import pytest

from pgtp_editor.sql import FormatConfig, FormatResult, Issue, format_selection
from pgtp_editor.sql.tokenizer import tokenize


def code(text):
    """Non-whitespace token texts, in order -- the formatter must not touch these."""
    return [tok.text for tok in tokenize(text) if not tok.is_trivia]


def fmt(text, **kwargs):
    result = format_selection(text, **kwargs)
    assert result.ok, [issue.message for issue in result.issues]
    assert result.issues == []
    return result.text


#: Every one of these must format, preserve tokens and be idempotent.
SAMPLES = [
    "select a, b from t where a = 1;",
    "select a from t join u on u.id = t.id left outer join v on v.id = t.id;",
    "select a from (select b from c where b > 0) s;",
    "insert into t (a, b) values (1, -2) returning id;",
    "select x, count(*) from t group by x having count(*) > 1 union all select y, 1 from u;",
    "update t set a = 1, b = 2 where id = $1;",
    "begin\nx := 1;\nend;",
    "begin\nif a then x := 1; elsif b then x := 2; else x := 3; end if;\nend;",
    "begin transaction;\nupdate t set a = 1;\ncommit;",
    "begin work;\nupdate t set a = 1;\nend;",
    "for i in 1..10 loop perform f(i); end loop;",
    "while more loop exit when done; end loop;",
    "select case when a then 'x' else 'y' end from t;",
    "case a when 1 then perform f(); else perform g(); end case;",
    "declare\nx int;\nbegin\nx := 1;\nexception when others then raise;\nend;",
    "-- head\nselect a /* mid */, b -- tail\nfrom t;",
    "create function f() returns void as $$\nbegin\n  perform 1;\nend;\n$$ language plpgsql;",
    "where a = 1",
    "drop table if exists t;",
    "select 'a''b', e'a\\'b', \"Col\", 1.5, a::text from t;",
    "select ügyfél.árvíztűrő from közös.tábla where szám = 1;",  # accented identifiers
]


@pytest.mark.parametrize("text", SAMPLES)
def test_samples_format_preserve_tokens_and_are_idempotent(text):
    once = fmt(text)
    assert code(once) == code(text)
    assert fmt(once) == once


# --------------------------------------------------------------------------
# Plain SQL structure
# --------------------------------------------------------------------------


def test_plain_select_is_broken_at_clause_keywords():
    assert fmt("select a, b from t where a = 1 and b = 2 order by a;") == (
        "select a, b\nfrom t\nwhere a = 1 and b = 2\norder by a;"
    )


def test_clause_continuation_lines_get_one_extra_level():
    assert fmt("select a,\nb\nfrom t") == "select a,\n    b\nfrom t"


def test_join_family_breaks_once_before_the_join_phrase():
    formatted = fmt("select a from t inner join u on u.id = t.id")
    assert formatted == "select a\nfrom t\ninner join u\non u.id = t.id"


def test_subquery_body_is_indented_by_paren_depth():
    assert fmt("select a from (select b from c) s;") == (
        "select a\nfrom (\n    select b\n    from c) s;"
    )


def test_keyword_and_identifier_casing_are_never_changed():
    text = "SeLeCt Foo, BAR fRoM MyTable"
    assert code(fmt(text)) == ["SeLeCt", "Foo", ",", "BAR", "fRoM", "MyTable"]


def test_operator_and_call_spacing_never_changes_meaning():
    # Glued constructs stay glued -- a space here would change the SQL, not
    # just its layout.
    # `::`, `.`, `%TYPE` and `$1` must stay glued (a space there is a different
    # statement); binary operators like `->>` may be spaced out freely.
    assert fmt("select a::text, x:=1, a->>'k', t.c%type, $1 from t") == (
        "select a::text, x := 1, a ->> 'k', t.c%type, $1\nfrom t"
    )
    assert fmt("select count(*), f(1), array[1, 2][1], a[i] from t") == (
        "select count(*), f(1), array[1, 2][1], a[i]\nfrom t"
    )
    assert fmt("select a % b, a - 1, -1, count(*) - 1 from t") == (
        "select a % b, a - 1, -1, count(*) - 1\nfrom t"
    )


def test_binary_minus_before_a_comment_or_sign_keeps_its_space():
    # The safe side of the unary-sign rule: with a value in front, the space
    # survives, so no `--` is ever manufactured.
    assert fmt("select 5 - -1 from t") == "select 5 - -1\nfrom t"
    assert fmt("select a - -- subtract\n b from t") == (
        "select a - -- subtract\n    b\nfrom t"
    )
    assert code(fmt("select a - -1 from t")) == code("select a - -1 from t")


def test_unary_minus_before_a_block_comment_does_not_change_the_tokens():
    text = "select -/* c */1 from t"
    assert code(fmt(text)) == code(text)


def test_double_unary_minus_is_not_glued_into_a_line_comment():
    # Regression: gluing `- -1` into `--1` made a line comment that swallowed
    # the rest of the line (`and b = 2` silently commented out, with ok=True).
    for text in ("select - -1, b from t", "where a = - -1 and b = 2", "select (- -1) from t"):
        assert code(fmt(text)) == code(text), text


def test_unary_sign_before_a_line_comment_keeps_its_space():
    # Regression: `- ` + `-- c` glued to `--- c` absorbed the sign into the
    # comment, so the statement silently lost it.
    text = "v := - -- flip sign\n  v;"
    assert code(fmt(text)) == code(text)


def test_adjacent_unary_plus_signs_keep_their_space():
    # Regression: `+ +1` glued to `++1`. Our tokenizer splits `++`, so the
    # token-stream invariant misses this one -- but Postgres lexes `++` as a
    # single (undefined) operator, so the glued output no longer parses.
    assert "+ +1" in fmt("select + +1 from t")


def test_literal_values_are_never_changed():
    text = "select 'Some  Text', 0.50 from t"
    assert "'Some  Text'" in fmt(text)
    assert "0.50" in fmt(text)


# --------------------------------------------------------------------------
# plpgsql block structure
# --------------------------------------------------------------------------


def test_bare_begin_end_fragment_indents_its_body():
    assert fmt("begin x := 1; y := 2; end;") == "begin\n    x := 1;\n    y := 2;\nend;"


def test_nested_if_elsif_else_end_if():
    text = "begin if a then if b then x := 1; end if; elsif c then y := 2; else z := 3; end if; end;"
    assert fmt(text) == (
        "begin\n"
        "    if a then\n"
        "        if b then\n"
        "            x := 1;\n"
        "        end if;\n"
        "    elsif c then\n"
        "        y := 2;\n"
        "    else\n"
        "        z := 3;\n"
        "    end if;\n"
        "end;"
    )


def test_loop_forms_open_a_block_but_headers_stay_on_one_line():
    assert fmt("for i in 1..3 loop perform f(i); end loop;") == (
        "for i in 1..3 loop\n    perform f(i);\nend loop;"
    )
    assert fmt("loop exit when done; end loop;") == "loop\n    exit when done;\nend loop;"


def test_declare_section_indents_its_declarations():
    assert fmt("declare\nx int;\ny text;\nbegin\nx := 1;\nend;") == (
        "declare\n    x int;\n    y text;\nbegin\n    x := 1;\nend;"
    )


def test_declare_cursor_statement_is_not_a_declare_section():
    # Inline `DECLARE c CURSOR FOR ...` is a statement: no block indent.
    assert fmt("declare c cursor for select 1;") == "declare c cursor for\nselect 1;"


def test_exception_part_dedents_and_does_not_open_a_block():
    assert fmt("begin perform f(); exception when others then raise; end;") == (
        "begin\n    perform f();\nexception\n    when others then\n        raise;\nend;"
    )


def test_case_expression_ends_with_a_bare_end():
    assert fmt("select case when a then 1 when b then 2 else 3 end as c from t;") == (
        "select case\n    when a then 1\n    when b then 2\n    else 3\nend as c\nfrom t;"
    )


def test_case_statement_ends_with_end_case():
    assert fmt("case x when 1 then perform f(); when 2 then perform g(); end case;") == (
        "case x\n    when 1 then perform f();\n    when 2 then perform g();\nend case;"
    )


def test_if_exists_modifier_is_not_a_block_opener():
    assert format_selection("drop table if exists t;").ok
    assert format_selection("create table if not exists t (id int);").ok


def test_transaction_begin_end_is_not_a_block():
    assert fmt("begin; update t set a = 1; end;") == "begin;\nupdate t\nset a = 1;\nend;"


def test_begin_transaction_commit_is_accepted_and_not_indented_as_a_body():
    """BUG-260810194657: this used to be *refused* as an unmatched BEGIN.

    `BEGIN TRANSACTION` opened a plpgsql frame that `COMMIT` cannot close, so
    Format Selection handed the text back with a bogus fatal issue -- while the
    bare-`BEGIN;` spelling of the very same statement (above) formatted fine.
    """
    assert fmt("BEGIN TRANSACTION;\nUPDATE t SET a = 1;\nCOMMIT;") == (
        "BEGIN TRANSACTION;\nUPDATE t\nSET a = 1;\nCOMMIT;"
    )


@pytest.mark.parametrize(
    "header",
    [
        "begin transaction",
        "begin work",
        "begin transaction isolation level serializable",
        "begin transaction read only",
        "begin isolation level serializable",  # the noise word may be omitted
        "begin read only",
        "begin not deferrable",
    ],
)
def test_every_transaction_begin_spelling_keeps_its_header_on_one_line(header):
    """The header is a statement, not a block opener -- so nothing breaks after it.

    Before the fix `_breaks_after` saw a `begin` frame on top and split the phrase
    (`BEGIN\\n    TRANSACTION;`) on the spellings that were accepted at all.
    """
    once = fmt(f"{header};\nupdate t set a = 1;\ncommit;")
    assert once == f"{header};\nupdate t\nset a = 1;\ncommit;"
    assert fmt(once) == once


def test_a_transaction_closed_with_end_is_not_indented_as_a_routine_body():
    """`END` is a `COMMIT` synonym, so this is transaction control end to end.

    It used to be accepted but misformatted -- phrase split, body indented one
    level as if it were a routine body. The `END;` is now taken by the formatter's
    `_saw_transaction_begin` path, which the `TRANSACTION`/`WORK` spellings could
    never reach before.
    """
    assert fmt("BEGIN TRANSACTION;\nUPDATE t SET a = 1;\nEND;") == (
        "BEGIN TRANSACTION;\nUPDATE t\nSET a = 1;\nEND;"
    )
    assert fmt("begin work;\nupdate t set a = 1;\nend;") == (
        "begin work;\nupdate t\nset a = 1;\nend;"
    )


def test_a_transaction_wrapping_a_routine_definition_is_not_refused():
    """The mixed selection: the wrapper used to refuse the whole thing."""
    text = (
        "BEGIN TRANSACTION;\n"
        "CREATE FUNCTION f() RETURNS int AS $$ BEGIN RETURN 1; END $$ LANGUAGE plpgsql;\n"
        "COMMIT;"
    )
    once = fmt(text)
    assert code(once) == code(text)
    assert once.startswith("BEGIN TRANSACTION;\n")
    assert "$$ BEGIN RETURN 1; END $$" in once  # the body stays opaque


@pytest.mark.parametrize("name", ["work", "transaction", "read", "isolation"])
def test_a_block_assigning_to_a_transaction_phrase_word_is_still_a_block(name):
    """The regression the fix could have introduced, and must not.

    Matching the phrase on `Token.lowered` alone would read `BEGIN work := 1;` as
    transaction control and then swallow the real `END;` as a `COMMIT` synonym --
    silently losing a block frame. The phrase is only believed when a `;`, the end
    of the input, or a transaction mode word follows it.
    """
    assert fmt(f"begin\n{name} := 1;\nend;") == f"begin\n    {name} := 1;\nend;"


def test_full_create_function_body_stays_opaque():
    text = (
        "create or replace function f(a int) returns void as $$\n"
        "begin\n"
        "      raise notice '%', a;\n"
        "end;\n"
        "$$ language plpgsql;"
    )
    formatted = fmt(text)
    body = text[text.index("$$") : text.rindex("$$") + 2]
    assert body in formatted  # dollar-quoted body reindented in no way at all
    assert code(formatted) == code(text)


# --------------------------------------------------------------------------
# Comments and opaque regions
# --------------------------------------------------------------------------


def test_line_comment_keeps_its_position_and_forces_a_break_after():
    assert fmt("select a -- why\nfrom t;") == "select a -- why\nfrom t;"
    assert fmt("-- lead\nselect a;") == "-- lead\nselect a;"


def test_block_comment_interior_is_never_reindented():
    text = "/* one\n     two */\nselect a;"
    assert fmt(text) == "/* one\n     two */\nselect a;"


def test_dollar_quote_with_tag_is_opaque():
    text = "select $tag$ if a then\nnot code $tag$ as x;"
    assert "$tag$ if a then\nnot code $tag$" in fmt(text)


def test_string_interior_is_never_reindented():
    text = "select 'select   a\n  from t' as s;"
    assert "'select   a\n  from t'" in fmt(text)


# --------------------------------------------------------------------------
# Non-ASCII identifiers (Hungarian schemas): never split, never respaced
# --------------------------------------------------------------------------


def test_accented_identifiers_round_trip_unsplit():
    text = "select ügyfél.árvíztűrő, tükörfúrógép from közös.tábla where ügyfél.szám = 1;"
    out = fmt(text)
    assert code(out) == code(text)
    assert out == (
        "select ügyfél.árvíztűrő, tükörfúrógép\n"
        "from közös.tábla\n"
        "where ügyfél.szám = 1;"
    )


def test_accented_identifier_is_not_broken_up_inside_a_plpgsql_body():
    text = "begin\nif ügyfél_száma > 0 then perform számol(ügyfél_száma); end if;\nend;"
    out = fmt(text)
    assert code(out) == code(text)
    assert "ügyfél_száma" in out
    assert "számol(ügyfél_száma)" in out


def test_accented_identifiers_stay_glued_to_cast_dot_and_type_operators():
    # The glue rules key off token kinds, so an identifier that fragmented would
    # show up here as `á :: szöveg` / `séma . tábla`.
    assert fmt("select á::szöveg from tábla") == "select á::szöveg\nfrom tábla"
    assert fmt("select séma.tábla.á from séma.tábla") == (
        "select séma.tábla.á\nfrom séma.tábla"
    )
    assert fmt("declare\nv tábla.á%TYPE;\nbegin\nnull;\nend") == (
        "declare\n    v tábla.á%TYPE;\nbegin\n    null;\nend"
    )
    assert fmt("select függ(tábla.á[1]) from tábla") == (
        "select függ(tábla.á[1])\nfrom tábla"
    )


def test_accented_identifiers_survive_a_dollar_quoted_body_verbatim():
    text = (
        "create function számol() returns void as $$\n"
        "begin\n"
        "  update tábla set ár = 1;\n"
        "end\n"
        "$$ language plpgsql;"
    )
    out = fmt(text)
    body = text[text.index("$$") : text.rindex("$$") + 2]
    assert body in out
    assert code(out) == code(text)


def test_accented_dollar_quote_tag_body_is_opaque():
    text = "create function f() returns int as $tág$ begin return 1; end $tág$ language plpgsql"
    out = fmt(text)
    assert "$tág$ begin return 1; end $tág$" in out
    assert code(out) == code(text)


def test_non_bmp_identifiers_round_trip_unsplit():
    ident = "\U00010330_col"  # Gothic letter + ASCII tail
    text = f"select {ident}, \U00020000col from t where {ident} = 1"
    out = fmt(text)
    assert code(out) == code(text)
    assert out == f"select {ident}, \U00020000col\nfrom t\nwhere {ident} = 1"


# --------------------------------------------------------------------------
# Decomposed (NFD) accented text -- what a macOS clipboard or a PDF copy hands
# over. Regression: a combining mark is not isalnum(), so the identifier was
# shredded and respaced, silently wrong with ok=True.
# --------------------------------------------------------------------------


def test_decomposed_nfd_identifier_is_never_respaced():
    nfd = unicodedata.normalize("NFD", "tábla")
    text = f"select * from {nfd}"
    out = fmt(text)
    assert nfd in out


def test_decomposed_nfd_dollar_quote_tag_body_is_opaque():
    # Regression: an unrecognized NFD tag meant the body was reindented as
    # code instead of staying opaque, and the tag itself gained spaces.
    tag = unicodedata.normalize("NFD", "tág")
    text = f"create function f() as ${tag}$\nbegin\n  return 1;\nend\n${tag}$ language plpgsql;"
    out = fmt(text)
    body = text[text.index(f"${tag}$") : text.rindex(f"${tag}$") + len(tag) + 2]
    assert body in out


# --------------------------------------------------------------------------
# Layout preservation: base indent, EOL, trailing newline, blank lines
# --------------------------------------------------------------------------


def test_base_indentation_is_preserved_on_every_line():
    assert fmt("        select a, b from t") == "        select a, b\n        from t"


def test_tab_base_indentation_is_preserved():
    assert fmt("\tselect a from t").splitlines() == ["\tselect a", "\tfrom t"]


def test_crlf_line_endings_are_preserved():
    assert fmt("select a\r\nfrom t") == "select a\r\nfrom t"


def test_lf_stays_lf():
    assert "\r" not in fmt("select a\nfrom t\nwhere b = 1")


def test_lone_cr_line_endings_are_preserved():
    assert fmt("select a\rfrom t") == "select a\rfrom t"
    assert fmt("select a from t\rwhere b = 1\r") == "select a\rfrom t\rwhere b = 1\r"


def test_mixed_line_endings_normalize_to_the_dominant_one():
    # A selection with more than one convention gets the majority ending on
    # every line -- deterministic, and never a stray half of a CRLF.
    assert fmt("select a\r\nfrom t\r\nwhere b = 1\norder by a") == (
        "select a\r\nfrom t\r\nwhere b = 1\r\norder by a"
    )
    assert fmt("select a\rfrom t\rwhere b = 1\norder by a") == (
        "select a\rfrom t\rwhere b = 1\rorder by a"
    )
    # LF majority, and a tie falls back to LF.
    assert fmt("select a\nfrom t\nwhere b = 1\r\norder by a") == (
        "select a\nfrom t\nwhere b = 1\norder by a"
    )
    assert fmt("select a\rfrom t\nwhere b = 1") == "select a\nfrom t\nwhere b = 1"


def test_all_three_line_endings_in_one_selection_still_format():
    result = format_selection("begin\rx := 1;\ny := 2;\r\nend;")
    assert result.ok, [issue.message for issue in result.issues]
    assert code(result.text) == code("begin\rx := 1;\ny := 2;\r\nend;")
    assert format_selection(result.text).text == result.text


def test_trailing_newline_is_preserved_and_absence_too():
    assert fmt("select a from t\n").endswith("from t\n")
    assert not fmt("select a from t").endswith("\n")


def test_blank_lines_between_statements_are_kept_but_capped():
    assert fmt("select 1;\n\n\n\nselect 2;") == "select 1;\n\nselect 2;"


def test_whitespace_only_selection_is_returned_untouched():
    for text in ("", "   ", "\n\n", "\t\r\n"):
        result = format_selection(text)
        assert result.ok
        assert result.text == text
        assert result.issues == []


def test_indent_unit_is_configurable():
    # FQ-033: `indent_unit=` is gone -- the value moved into `FormatConfig`, so
    # there is exactly one way to set it.
    assert (
        fmt("begin x := 1; end;", config=FormatConfig(indent_unit="  "))
        == "begin\n  x := 1;\nend;"
    )


# --------------------------------------------------------------------------
# Refusal gate
# --------------------------------------------------------------------------


def refusal(text):
    result = format_selection(text)
    assert not result.ok, result.text
    assert result.text == text  # verbatim, so an `ok`-ignoring caller is safe
    assert result.issues
    assert all(issue.fatal for issue in result.issues)
    return result


def test_refusal_returns_a_format_result_dataclass():
    result = refusal("select 'abc")
    assert isinstance(result, FormatResult)
    assert isinstance(result.issues[0], Issue)


@pytest.mark.parametrize(
    "text,needle,offending",
    [
        ("select 'abc", "Unterminated single-quoted string literal", "'abc"),
        ('select "abc', "Unterminated double-quoted identifier", '"abc'),
        ("select $$abc", "Unterminated dollar-quoted string ($$)", "$$abc"),
        ("select $t$abc", "Unterminated dollar-quoted string ($t$)", "$t$abc"),
        ("select /* abc", "Unterminated block comment", "/* abc"),
    ],
)
def test_split_opaque_region_refuses_with_the_construct_span(text, needle, offending):
    result = refusal(text)
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert needle in issue.message
    assert text[issue.start : issue.end] == offending


def test_cr_only_text_refuses_with_spans_on_the_right_line():
    result = refusal("select a\rfrom t\rwhere f(a = 1")
    issue = result.issues[0]
    assert "Unmatched '('" in issue.message
    assert result.text[issue.start : issue.end] == "("
    assert (issue.start_line, issue.start_col) == (3, 8)
    assert "line 3, column 8" in issue.message


def test_cr_only_text_reports_a_block_span_on_a_later_line():
    result = refusal("begin\r  x := 1;\r  if a then\r    y := 2;\rend;")
    issue = next(i for i in result.issues if i.message.startswith("Unmatched IF"))
    assert result.text[issue.start : issue.end] == "if"
    assert (issue.start_line, issue.start_col) == (3, 3)
    assert "line 3, column 3" in issue.message


@pytest.mark.parametrize(
    "opaque",
    ["$$a\rb$$", "$$a\r\nb$$", "$tag$a\rb$tag$", "/* a\rb */", "/* a\r\nb */", "'a\rb'"],
)
def test_refusal_span_is_right_after_a_multi_line_opaque_token(opaque):
    # Line counting has to run *through* an opaque region: each parametrized
    # region carries exactly one internal break (CR or CRLF), so the stray ')'
    # is on line 4 -- and would be reported on line 3 if that break were missed.
    text = f"select {opaque}\nfrom t\n)"
    result = refusal(text)
    issue = result.issues[0]
    assert "Unmatched ')'" in issue.message
    assert text[issue.start : issue.end] == ")"
    assert (issue.start_line, issue.start_col) == (4, 1)
    assert "line 4, column 1" in issue.message


def test_all_three_line_endings_before_an_unbalanced_paren():
    result = refusal("select a\rfrom t\nwhere b = 1\r\nand f(c = 2")
    issue = result.issues[0]
    assert "Unmatched '('" in issue.message
    assert (issue.start_line, issue.start_col) == (4, 6)


def test_unbalanced_open_paren_refuses_with_the_paren_span():
    result = refusal("select f(a, b")
    issue = result.issues[0]
    assert "Unmatched '('" in issue.message
    assert result.text[issue.start : issue.end] == "("
    assert (issue.start_line, issue.start_col) == (1, 9)


def test_stray_close_paren_refuses_with_the_paren_span():
    result = refusal("select a from t) x")
    issue = result.issues[0]
    assert "Unmatched ')'" in issue.message
    assert result.text[issue.start : issue.end] == ")"


def test_unbalanced_brackets_refuse():
    assert not format_selection("select a[1").ok
    result = refusal("select a1] from t")
    assert "Unmatched ']'" in result.issues[0].message


def test_begin_without_end_refuses_with_the_begin_span():
    result = refusal("begin\n  x := 1;\n  y := 2;")
    issue = result.issues[0]
    assert issue.message.startswith("Unmatched BEGIN")
    assert result.text[issue.start : issue.end] == "begin"
    assert (issue.start_line, issue.start_col, issue.end_line, issue.end_col) == (1, 1, 1, 6)
    assert issue.line == issue.start_line  # xsd_verify.Issue parity


def test_if_without_end_if_refuses_with_the_if_span():
    # The bare `END` is consumed as the IF's (wrong) closer, so the BEGIN is
    # reported unclosed too -- both are true, and the IF span is exact.
    result = refusal("begin\n  if a then\n    x := 1;\nend;")
    assert result.issues[0].message.startswith("Unmatched BEGIN")
    issue = result.issues[1]
    assert issue.message.startswith("Unmatched IF")
    assert "END IF" in issue.message
    assert result.text[issue.start : issue.end] == "if"
    assert (issue.start_line, issue.start_col) == (2, 3)


def test_loop_without_end_loop_refuses():
    result = refusal("loop\n  perform f();")
    assert result.issues[0].message.startswith("Unmatched LOOP")
    assert "END LOOP" in result.issues[0].message
    assert result.text[result.issues[0].start : result.issues[0].end] == "loop"


def test_case_without_end_refuses():
    result = refusal("select case when a then 1 from t;")
    assert result.issues[0].message.startswith("Unmatched CASE")
    assert result.text[result.issues[0].start : result.issues[0].end] == "case"


def test_stray_end_refuses():
    result = refusal("  x := 1;\nend if;")
    issue = result.issues[0]
    assert "Unmatched END" in issue.message
    assert result.text[issue.start : issue.end] == "end if"


def test_wrong_closer_refuses_once_with_the_opener_span():
    result = refusal("if a then\n  x := 1;\nend loop;")
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.message.startswith("Unmatched IF")
    assert "found END loop instead" in issue.message
    assert result.text[issue.start : issue.end] == "if"


def test_incomplete_clause_fragment_still_formats():
    # Only quoting/paren/block imbalance refuses -- clause-level incompleteness
    # is a legitimate selection.
    for text in ("where a = 1", "order by a, b", "and x = 2", ", b, c"):
        assert format_selection(text).ok, text


def test_multiple_refusals_are_reported_in_position_order():
    result = refusal("begin\n  x := 1;\nend loop;\nend case;")
    starts = [issue.start for issue in result.issues]
    assert starts == sorted(starts)
    assert len(result.issues) >= 2


def test_uppercase_blocks_are_matched_case_insensitively():
    assert format_selection("BEGIN\n  X := 1;\nEND;").ok
    assert format_selection("IF A THEN\n  X := 1;\nEND IF;").ok
    assert format_selection("CASE X WHEN 1 THEN NULL; END CASE;").ok


# --------------------------------------------------------------------------
# Whole-contract properties
# --------------------------------------------------------------------------


@pytest.mark.parametrize("text", SAMPLES)
def test_only_whitespace_differs_from_the_input(text):
    formatted = fmt(text)
    assert "".join(formatted.split()) == "".join(text.split())


def test_double_format_is_stable_for_a_realistic_function_body():
    text = (
        "DECLARE\n"
        "v_count int;\n"
        "BEGIN\n"
        "SELECT count(*) INTO v_count FROM orders o JOIN customers c ON c.id = o.customer_id "
        "WHERE o.total > 0;\n"
        "IF v_count > 0 THEN\n"
        "RAISE NOTICE 'found %', v_count;\n"
        "ELSE\n"
        "RAISE NOTICE 'none';\n"
        "END IF;\n"
        "FOR r IN SELECT * FROM orders LOOP\n"
        "PERFORM log_order(r.id);\n"
        "END LOOP;\n"
        "EXCEPTION WHEN others THEN\n"
        "RAISE;\n"
        "END;\n"
    )
    once = fmt(text)
    assert fmt(once) == once
    assert code(once) == code(text)
    assert once.endswith("\n")
