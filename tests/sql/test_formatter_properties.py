"""Contract-level invariants of `format_selection` (spec §18.4). Pure, no Qt.

`test_formatter.py` pins down *what* the layout looks like for specific inputs.
This module hardens the four promises the feature makes regardless of input,
over a wide corpus of realistic SQL/plpgsql plus deliberately adversarial text:

1. **Token preservation** -- the output's non-whitespace token stream is the
   input's, in order: no casing, comma-style or literal change, ever.
2. **Idempotence / determinism** -- `format(format(x)) == format(x)`, and the
   same input always yields the same output.
3. **Refusal is verbatim** -- `ok=False` hands back the input unchanged with
   every `Issue` fatal and spanning the actual offending construct.
4. **Never crashes, never hangs** -- adversarial selections (half-selected
   literals, lone closers, deep nesting, a 200 KB body, CRLF/lone-CR, unicode)
   return a `FormatResult` instead of raising.
"""
from __future__ import annotations

import random
import time

import pytest

from pgtp_editor.sql import FormatConfig, FormatResult, format_selection
from pgtp_editor.sql.tokenizer import tokenize


def code(text):
    """Non-whitespace token texts, in order -- the part the formatter may not touch."""
    return [tok.text for tok in tokenize(text) if not tok.is_trivia]


# --------------------------------------------------------------------------
# Corpus: realistic selections a DDL editor would hand over. Every entry must
# format, preserve tokens, and be idempotent.
# --------------------------------------------------------------------------

TRIGGER_FUNCTION = (
    "CREATE OR REPLACE FUNCTION public.stamp_row() RETURNS trigger LANGUAGE plpgsql AS $$\n"
    "BEGIN\n"
    "    IF TG_OP = 'INSERT' THEN\n"
    "        NEW.created_at := now();\n"
    "    ELSIF TG_OP = 'UPDATE' THEN\n"
    "        NEW.updated_at := now();\n"
    "    END IF;\n"
    "    RETURN NEW;\n"
    "END;\n"
    "$$;"
)

TRIGGER_BODY = (
    "IF TG_OP = 'INSERT' THEN\n"
    "NEW.created_at := now();\n"
    "ELSIF TG_OP = 'UPDATE' THEN\n"
    "NEW.updated_at := now();\n"
    "ELSE\n"
    "RETURN OLD;\n"
    "END IF;\n"
    "RETURN NEW;"
)

CORPUS = [
    # -- plain SQL ---------------------------------------------------------
    "select 1",
    "select a, b, c from t",
    "select * from t where a = 1 and b <> 2 order by a desc limit 10 offset 5;",
    "select t.a, u.b from t left outer join u on u.id = t.id where t.a is not null;",
    "with recent as (select id from orders where total > 0) select * from recent;",
    "insert into t (a, b) values (1, -2), (3, 4) returning id, a;",
    "update t set a = 1, b = default where id = $1 returning *;",
    "delete from t where id in (select id from u where flag);",
    "select coalesce(a, 0) + 1, count(*) filter (where b) from t group by a having count(*) > 1;",
    "create table t (id serial primary key, name text not null default 'x', ref int references u (id));",
    "create index if not exists t_name_idx on t using btree (lower(name));",
    "alter table t add column extra jsonb, alter column name set not null;",
    "comment on function f(int) is 'does a thing';",
    "grant select, insert on table t to app_user;",
    # -- plpgsql fragments -------------------------------------------------
    "begin x := 1; end;",
    "begin\n  perform f();\nend;",
    TRIGGER_BODY,
    "IF a THEN x := 1; ELSIF b THEN x := 2; ELSE x := 3; END IF;",
    "FOR rec IN SELECT id, name FROM customers WHERE active LOOP\nPERFORM audit(rec.id);\nEND LOOP;",
    "FOR i IN 1..10 LOOP\nCONTINUE WHEN i % 2 = 0;\nPERFORM f(i);\nEND LOOP;",
    "WHILE cnt > 0 LOOP cnt := cnt - 1; END LOOP;",
    "LOOP EXIT WHEN done; PERFORM step(); END LOOP;",
    "x := CASE WHEN a THEN 1 WHEN b THEN 2 ELSE 3 END;",
    "CASE x WHEN 1 THEN PERFORM a(); WHEN 2 THEN PERFORM b(); ELSE PERFORM c(); END CASE;",
    "DECLARE\nv_id int;\nv_name text := 'x';\nBEGIN\nv_id := 1;\nEND;",
    "BEGIN\nPERFORM risky();\nEXCEPTION\nWHEN unique_violation THEN\nRAISE NOTICE 'dup';\n"
    "WHEN others THEN\nRAISE;\nEND;",
    "begin\nif a then\nfor i in 1..3 loop\nperform f(i);\nend loop;\nend if;\nend;",
    "declare c cursor for select 1;",
    "raise exception 'bad value: %', v using hint = 'check input';",
    "select f(a := 1, b := 2);",
    # -- whole routines ----------------------------------------------------
    TRIGGER_FUNCTION,
    "create function f() returns void as $body$ begin perform 1; end; $body$ language plpgsql;",
    "CREATE OR REPLACE FUNCTION f(p int) RETURNS int LANGUAGE sql IMMUTABLE STRICT AS $$\n"
    "  SELECT p + 1;\n$$;",
    # -- transaction control ----------------------------------------------
    "BEGIN;\nUPDATE t SET a = 1;\nEND;",
    "begin; select 1; commit;",
    # Every spelling of the same statement, because for a long time only the bare
    # `BEGIN;` one worked and the rest were refused outright (BUG-260810194657).
    "BEGIN TRANSACTION;\nUPDATE t SET a = 1;\nCOMMIT;",
    "BEGIN WORK;\nUPDATE t SET a = 1;\nEND;",
    "BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;\nUPDATE t SET a = 1;\nROLLBACK;",
    "begin read only;\nselect 1;\ncommit;",
    "BEGIN TRANSACTION;\nCREATE FUNCTION f() RETURNS int AS $$ BEGIN RETURN 1; END $$"
    " LANGUAGE plpgsql;\nCOMMIT;",
    # ... and the block that merely *looks* like one of those spellings.
    "BEGIN\nwork := 1;\nEND;",
    # -- comments and opaque regions --------------------------------------
    "-- leading note\nselect a from t; -- trailing note",
    "select a /* inline */, b from t;",
    "/* one\n   two */\nselect 1;",
    "select '$$ not a dollar quote', $$ -- not a comment $$ from t;",
    "select 'a''b', \"C\"\"D\", e'x\\'y', U&'z' from t;",
    "select $$$$ as empty_dollar, '' as empty_string, \"\" as empty_ident;",
    # -- fragments / mid-token selections ---------------------------------
    "where a = 1",
    "order by a, b",
    ", b, c",
    "OM customers WHERE id = 1",  # selection started mid-token
    "select a from tabl",  # selection ended mid-token
    ";",
    ",",
    "-- only a comment",
    "/* only a comment */",
    # -- line endings ------------------------------------------------------
    "select a\r\nfrom t\r\nwhere b = 1\r\n",
    "BEGIN\r\nIF a THEN\r\nx := 1;\r\nEND IF;\r\nEND;\r\n",
    "select a\rfrom t\rwhere b = 1",  # lone-CR (classic Mac) line endings
    "select a\rfrom t\nwhere b = 1\r\norder by a",  # all three in one selection
    "begin\rx := 1;\ny := 2;\r\nend;",
    "\tselect a from t",
    "        select a, b from t",
    # -- non-ASCII identifiers (Hungarian schemas, non-BMP letters) ---------
    "select ügyfél.árvíztűrő from közös.tábla where szám = 1;",
    "declare\nv tábla.ár%TYPE;\nbegin\nv := függ(tábla.ár[1])::szöveg;\nend;",
    "create function számol() returns void as $$\nbegin\n  update tábla set ár = 1;\nend\n$$ language plpgsql;",
    "create function f() returns int as $tág$ begin return 1; end $tág$ language plpgsql;",
    "select \U00010330_col, \U00020000col from t where \U00010330_col = 1",
]


@pytest.mark.parametrize("text", CORPUS, ids=range(len(CORPUS)))
def test_corpus_entries_format_without_refusing(text):
    result = format_selection(text)
    assert result.ok, [issue.message for issue in result.issues]
    assert result.issues == []


@pytest.mark.parametrize("text", CORPUS, ids=range(len(CORPUS)))
def test_corpus_entries_preserve_the_token_stream(text):
    formatted = format_selection(text).text
    assert code(formatted) == code(text)


@pytest.mark.parametrize("text", CORPUS, ids=range(len(CORPUS)))
def test_corpus_entries_are_idempotent(text):
    once = format_selection(text)
    twice = format_selection(once.text)
    assert twice.ok, [issue.message for issue in twice.issues]
    assert twice.text == once.text
    thrice = format_selection(twice.text)
    assert thrice.text == once.text


@pytest.mark.parametrize("text", CORPUS, ids=range(len(CORPUS)))
def test_corpus_entries_differ_from_the_input_in_whitespace_only(text):
    formatted = format_selection(text).text
    assert "".join(formatted.split()) == "".join(text.split())


@pytest.mark.parametrize("text", CORPUS, ids=range(len(CORPUS)))
def test_formatting_is_deterministic(text):
    first = format_selection(text)
    second = format_selection(text)
    assert (first.ok, first.text) == (second.ok, second.text)


def test_indent_unit_choice_does_not_change_the_token_stream():
    # FQ-033: the unit is carried by `FormatConfig` now. `""` is no longer a
    # *reachable* value (`FormatConfig.sanitized()` is the loader's gate and
    # replaces it), but the engine is still handed it raw here, because "the unit
    # never changes the token stream" must hold for whatever it is given.
    for unit in ("    ", "  ", "\t", ""):
        config = FormatConfig(indent_unit=unit)
        for text in (TRIGGER_BODY, TRIGGER_FUNCTION, "begin if a then x := 1; end if; end;"):
            result = format_selection(text, config=config)
            assert result.ok, [issue.message for issue in result.issues]
            assert code(result.text) == code(text)
            assert format_selection(result.text, config=config).text == result.text


# --------------------------------------------------------------------------
# Adversarial input: never raise, never hang, always honor the contract.
# --------------------------------------------------------------------------

ADVERSARIAL = {
    "empty": "",
    "spaces": "   ",
    "newlines_only": "\n\n",
    "mixed_blank": "\t\r\n \r ",
    "lone_close_paren": ")",
    "lone_open_paren": "(",
    "lone_close_bracket": "]",
    "lone_end": "END",
    "lone_end_semicolon": "end;",
    "lone_end_if": "end if;",
    "lone_begin": "begin",
    "lone_begin_transaction": "begin transaction",  # phrase at the very end of the input
    "begin_half_mode_list": "begin transaction isolation",
    "begin_mode_head_only": "begin read",
    "deep_parens": "select " + "(" * 80 + "1" + ")" * 80 + " from t",
    "deep_blocks": "begin\n" * 40 + "x := 1;\n" + "end;\n" * 40,
    "unbalanced_deep_blocks": "begin\n" * 40 + "x := 1;\n" + "end;\n" * 39,
    "half_string": "select 'abc",
    "half_ident": 'select "abc',
    "half_dollar": "select $$abc",
    "half_tagged_dollar": "select $body$abc",
    "half_block_comment": "select /* abc",
    "nested_half_block_comment": "/* a /* b */ select 1;",
    "closing_half_of_dollar_body": "  raise notice 'x';\nend;\n$$ language plpgsql;",
    "mid_string_start": "abc' as x from t",
    "dollar_inside_line_comment": "select a -- $$ not a quote\nfrom t;",
    "dashdash_inside_string": "select 'a -- b' from t;",
    "quote_escapes": "select 'a''b', \"C\"\"D\" from t;",
    "nested_block_comment": "/* a /* b */ c */ select 1;",
    "unicode_string_literal": "select 'Ünnep' from t;",
    "vertical_tab": "select \x0b a from t",
    "only_operators": ":: := ->> <> % -",
    "keyword_soup": "end else elsif when then loop case begin",
    "many_semicolons": ";;;;;;;;;;",
    "crlf_and_lf_mixed": "select a\r\nfrom t\nwhere b = 1\r\n",
    "all_three_endings_mixed": "select a\rfrom t\nwhere b = 1\r\n",
    "cr_only_unbalanced_begin": "begin\rif a then\rx := 1;\r",
    "cr_inside_dollar_body": "select $$a\rb$$ from t;",
    "crlf_inside_block_comment": "/* a\r\nb */ select 1;",
    "accented_identifiers": "select ügyfél.szám::text from közös.tábla;",
    "accented_dollar_tag": "$tág$ begin return 1; end $tág$",
    "half_accented_dollar_tag": "$tág$ begin return 1;",
    "non_bmp_identifier": "select \U00010330_col from t",
    # A combining mark alone / inside an identifier must still not crash. Written
    # with an explicit escape so no editor can silently re-normalize it. (That an
    # NFD identifier gets *respaced* is a separate known bug, pinned by the
    # strict-xfail tests in test_formatter.py -- it is not condoned here.)
    "combining_mark_identifier": "select * from ta\u0301bla",
    "lone_combining_mark": "\u0301",
}


@pytest.mark.parametrize("name", sorted(ADVERSARIAL), ids=sorted(ADVERSARIAL))
def test_adversarial_input_returns_a_result_and_honors_the_contract(name):
    text = ADVERSARIAL[name]
    started = time.monotonic()
    result = format_selection(text)
    assert time.monotonic() - started < 5.0, "formatting should not stall"
    assert isinstance(result, FormatResult)
    if result.ok:
        assert result.issues == []
        assert code(result.text) == code(text)
        assert format_selection(result.text).text == result.text
    else:
        assert result.text == text, "a refusal must return the selection verbatim"
        assert result.issues
        assert all(issue.fatal for issue in result.issues)
        for issue in result.issues:
            assert 0 <= issue.start < issue.end <= len(text)
            assert issue.start_line >= 1 and issue.start_col >= 1


def test_a_200kb_body_formats_in_reasonable_time():
    text = "begin\nif a then\nx := 1;\nend if;\nend;\n" * 6000
    assert len(text) > 200_000
    started = time.monotonic()
    result = format_selection(text)
    elapsed = time.monotonic() - started
    assert result.ok, [issue.message for issue in result.issues]
    assert elapsed < 20.0, f"200 KB selection took {elapsed:.1f}s"
    assert code(result.text) == code(text)


def test_deeply_nested_input_does_not_recurse_to_death():
    # An implementation that recursed per nesting level would blow the stack.
    text = "select " + "(" * 400 + "1" + ")" * 400
    result = format_selection(text)
    assert result.ok, [issue.message for issue in result.issues]
    assert code(result.text) == code(text)


# --------------------------------------------------------------------------
# Seeded fuzz: random token soup must satisfy the same contract.
# --------------------------------------------------------------------------

_FUZZ_PIECES = [
    "select", "from", "where", "begin", "end", "if", "then", "else", "elsif",
    "end if", "loop", "end loop", "case", "when", "end case", "declare",
    "exception", ";", ",", "(", ")", "[", "]", "'s'", '"i"', "$$b$$", "-- c\n",
    "/* c */", "x", "1", "::", ":=", "\n", "  ", "\t", "$1", "%", "-", "+",
    "$tag$ y $tag$", "'a''b'", "\r\n", "\r", "/* a /* b */ c */", "e'q\\'r'",
]


@pytest.mark.parametrize("seed", [20260801, 7, 99])
def test_fuzzed_token_soup_never_breaks_the_contract(seed):
    rng = random.Random(seed)
    for _ in range(400):
        text = "".join(rng.choice(_FUZZ_PIECES) for _ in range(rng.randint(0, 14)))
        result = format_selection(text)  # must not raise
        if not result.ok:
            assert result.text == text, repr(text)
            assert result.issues and all(issue.fatal for issue in result.issues), repr(text)
            continue
        assert code(result.text) == code(text), repr(text)
        again = format_selection(result.text)
        assert again.ok, (repr(text), [i.message for i in again.issues])
        assert again.text == result.text, repr(text)
