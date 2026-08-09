# tests/sql/test_caret_context.py
"""Tests for pgtp_editor.sql.caret_context -- the Qt-free caret-context
resolver behind schema-aware Ctrl+Space completion (spec §18.6)."""
from pgtp_editor.sql.caret_context import (
    ALIAS_REF,
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


def test_caret_inside_dollar_quoted_body_resolves_against_the_body():
    """BUG-041, the reconciliation point. This test used to assert the caret
    was *unresolvable* inside a `$$ ... $$` body -- correct for the tokenizer
    (a `FROM` in there is not the enclosing statement's FROM clause) but wrong
    for the caret, which lives in the body. The body is now re-resolved as its
    own text; `..._nested_in_a_body_...` below keeps the half this test was
    really protecting."""
    text = "$$ select * from equ $$"
    ctx = resolve_caret_context(text, _pos(text, "equ"))
    assert ctx.kind == DOTTED_PATH
    assert ctx.prefix == "equ"


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


# --- ALIAS_REF: a lone segment bound by the caret's own FROM clause ---------
# (FQ-030 slice 1; `ALIAS_REF` is a refinement of `DOTTED_PATH`, so `parts`
# stays filled and the old reading remains available as a fallback.)


def test_alias_reference_is_promoted_to_alias_ref():
    text = "select * from hr.jobcard jc where jc."
    ctx = resolve_caret_context(text, len(text))
    assert ctx.kind == ALIAS_REF
    assert ctx.table_ref.qualified == "hr.jobcard"
    assert ctx.parts == ("jc",)  # DOTTED_PATH fallback still available
    assert ctx.prefix == ""


def test_alias_reference_keeps_the_partial_column_prefix():
    text = "select * from hr.jobcard jc where jc.jo"
    ctx = resolve_caret_context(text, len(text))
    assert ctx.kind == ALIAS_REF
    assert ctx.prefix == "jo"
    assert ctx.table_ref.table == "jobcard"


def test_unaliased_table_name_is_also_an_alias_reference():
    text = "select * from hr.jobcard where jobcard."
    ctx = resolve_caret_context(text, len(text))
    assert ctx.kind == ALIAS_REF
    assert ctx.table_ref.qualified == "hr.jobcard"


def test_schema_segment_stays_a_dotted_path():
    """`hr.` is a schema, not an alias -- the FROM clause binds `jc`, not `hr`."""
    text = "select * from hr.jobcard jc where hr."
    ctx = resolve_caret_context(text, len(text))
    assert ctx.kind == DOTTED_PATH
    assert ctx.parts == ("hr",)


def test_alias_of_another_statement_is_not_promoted():
    text = "select * from hr.jobcard jc;\nselect * from hr.dept d where jc."
    ctx = resolve_caret_context(text, len(text))
    assert ctx.kind == DOTTED_PATH


def test_derived_table_alias_is_not_promoted():
    """A subquery alias has no catalog table behind it, so it stays a
    `DOTTED_PATH` and the caller's existing schema lookup applies unchanged."""
    text = "select * from (select 1 as n) sub where sub."
    ctx = resolve_caret_context(text, len(text))
    assert ctx.kind == DOTTED_PATH


def test_row_variable_still_wins_over_a_table_named_new():
    text = "select * from hr.new new where new."
    ctx = resolve_caret_context(text, len(text))
    assert ctx.kind == ROW_VARIABLE
    assert ctx.row_variable == "NEW"


def test_two_segment_path_is_never_an_alias_reference():
    text = "select * from hr.jobcard jc where hr.jobcard."
    ctx = resolve_caret_context(text, len(text))
    assert ctx.kind == DOTTED_PATH
    assert ctx.parts == ("hr", "jobcard")


def test_plain_dotted_paths_are_unaffected_when_no_from_clause_binds_them():
    text = "select * from pr."
    ctx = resolve_caret_context(text, len(text))
    assert ctx.kind == DOTTED_PATH
    assert ctx.parts == ("pr",)
    assert ctx.table_ref is None


# --- Inside a `$$ ... $$` routine body (BUG-041) ---------------------------
# The DDL object editor's buffer is a whole `pg_get_functiondef` result, so
# nearly all of it is one dollar-quoted token. Caret resolution descends into
# that body (`tokenizer.dollar_body_at`) while it stays opaque to every other
# consumer -- the two halves of one rule.

FUNCTIONDEF = (
    "CREATE OR REPLACE FUNCTION pr.jobcard_bi()\n"
    " RETURNS trigger\n"
    " LANGUAGE plpgsql\n"
    "AS $function$\n"
    "BEGIN\n"
    "  IF NEW.sta THEN\n"
    "    RAISE NOTICE '%', 'not an identifier';  -- nor is this\n"
    "  END IF;\n"
    "  SELECT jc.jo FROM hr.jobcard jc;\n"
    "  PERFORM pr.helper();\n"
    "  RETURN NEW;\n"
    "END\n"
    "$function$\n"
)


def test_row_variable_resolves_inside_a_functiondef_body():
    """The reported symptom: `NEW.` completion is what a plpgsql author types,
    and it was structurally dead because the whole body is one token."""
    ctx = resolve_caret_context(FUNCTIONDEF, _pos(FUNCTIONDEF, "NEW.sta"))
    assert ctx.kind == ROW_VARIABLE
    assert ctx.row_variable == "NEW"
    assert ctx.prefix == "sta"


def test_alias_reference_resolves_inside_a_functiondef_body():
    """The analyzer half already descended into the body; now both layers
    agree on the same caret."""
    ctx = resolve_caret_context(FUNCTIONDEF, _pos(FUNCTIONDEF, "jc.jo"))
    assert ctx.kind == ALIAS_REF
    assert ctx.table_ref.qualified == "hr.jobcard"
    assert ctx.prefix == "jo"


def test_dotted_path_resolves_inside_a_functiondef_body():
    ctx = resolve_caret_context(FUNCTIONDEF, _pos(FUNCTIONDEF, "PERFORM pr.h"))
    assert ctx.kind == DOTTED_PATH
    assert ctx.parts == ("pr",)
    assert ctx.prefix == "h"


def test_prefix_from_a_body_is_measured_in_original_buffer_coordinates():
    """What escapes the recursion must be valid against the *original* buffer:
    the UI replaces `len(prefix)` characters before the caret, so a
    body-relative answer would corrupt the outer text."""
    for marker in ("NEW.sta", "jc.jo", "PERFORM pr.h"):
        pos = _pos(FUNCTIONDEF, marker)
        ctx = resolve_caret_context(FUNCTIONDEF, pos)
        assert FUNCTIONDEF[pos - len(ctx.prefix) : pos] == ctx.prefix, marker


def test_header_line_outside_the_body_still_resolves():
    """The one place that worked before must keep working."""
    text = "CREATE OR REPLACE FUNCTION pr."
    ctx = resolve_caret_context(text, len(text))
    assert ctx.kind == DOTTED_PATH
    assert ctx.parts == ("pr",)


def test_trailing_language_clause_after_the_body_still_resolves():
    text = "create function f() as $$ begin end $$ language plpg"
    ctx = resolve_caret_context(text, len(text))
    assert ctx.kind == DOTTED_PATH
    assert ctx.prefix == "plpg"


def test_string_literal_nested_in_a_body_is_still_unresolvable():
    """The half the old `..._is_unresolvable` test was really protecting: the
    body is re-tokenized, so its own opaque regions stay opaque. Losing this
    would turn a silent no-op into a wrong popup."""
    pos = FUNCTIONDEF.index("not an identifier") + 4
    assert resolve_caret_context(FUNCTIONDEF, pos) is None


def test_line_comment_nested_in_a_body_is_still_unresolvable():
    pos = FUNCTIONDEF.index("nor is this") + 4
    assert resolve_caret_context(FUNCTIONDEF, pos) is None


def test_block_comment_nested_in_a_body_is_still_unresolvable():
    text = "create function f() as $$ begin /* hr.secret */ end $$ language plpgsql"
    pos = text.index("hr.secret") + len("hr.")
    assert resolve_caret_context(text, pos) is None


def test_quoted_identifier_nested_in_a_body_is_still_unresolvable():
    text = 'create function f() as $$ select "Odd.Name" $$ language sql'
    pos = text.index("Odd.Name") + len("Odd.")
    assert resolve_caret_context(text, pos) is None


def test_tagged_and_bare_bodies_behave_alike():
    for opener, closer in (("$$", "$$"), ("$function$", "$function$")):
        text = f"create function f() as {opener}\nbegin\n  if NEW.st then\n{closer}"
        ctx = resolve_caret_context(text, _pos(text, "NEW.st"))
        assert ctx.kind == ROW_VARIABLE, opener
        assert ctx.prefix == "st"


def test_unterminated_body_still_resolves_and_does_not_raise():
    """The normal state while typing a new routine: no closing tag yet."""
    text = "create function f() as $$\nbegin\n  if NEW.st"
    ctx = resolve_caret_context(text, len(text))
    assert ctx.kind == ROW_VARIABLE
    assert ctx.prefix == "st"


def test_caret_inside_the_closing_tag_does_not_raise():
    text = "create function f() as $function$ begin end $function$ language sql"
    pos = text.rindex("$function$") + 3
    assert resolve_caret_context(text, pos) is not None


def test_nested_bodies_are_depth_bounded_rather_than_infinite():
    """Malformed nesting must not recurse forever -- this runs per keystroke."""
    text = "NEW.st"
    for tag in ("a", "b", "c", "d", "e", "f", "g", "h"):
        text = f"${tag}$ {text} ${tag}$"
    assert resolve_caret_context(text, text.index("NEW.st") + len("NEW.")) is None


def test_a_body_nested_one_level_deep_still_resolves():
    text = "$outer$ create function f() as $inner$ if NEW.st $inner$ $outer$"
    ctx = resolve_caret_context(text, _pos(text, "NEW.st"))
    assert ctx.kind == ROW_VARIABLE
    assert ctx.prefix == "st"


def test_every_prefix_of_a_typed_routine_definition_resolves_without_raising():
    """Ctrl+Space and the popup filter both call this on half-typed text; a
    raise here would be a crash in the editor, so every intermediate state of
    typing the definition is exercised."""
    for i in range(len(FUNCTIONDEF) + 1):
        resolve_caret_context(FUNCTIONDEF[:i], i)  # must not raise
        resolve_caret_context(FUNCTIONDEF, i)  # must not raise


def test_malformed_dollar_quotes_degrade_to_no_resolution_rather_than_raising():
    for text in ("$", "$$", "$$$", "$tag$", "$tag$ $other$", "$$ $ $$", "$1 $$ x"):
        for pos in range(len(text) + 1):
            resolve_caret_context(text, pos)  # must not raise
