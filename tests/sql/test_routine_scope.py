# tests/sql/test_routine_scope.py
"""Tests for pgtp_editor.sql.routine_scope -- the Qt-free plpgsql local-scope
analyzer behind local-variable / parameter / %ROWTYPE completion (spec §18.6,
FQ-030 slice 3)."""
from pgtp_editor.sql.routine_scope import (
    ALIAS,
    CURSOR,
    LOOP_VARIABLE,
    PARAMETER,
    TRIGGER_VARIABLES,
    VARIABLE,
    analyze_routine_scope,
    trigger_variable_names,
)


def _pos(text: str, marker: str) -> int:
    """The 0-based offset right after `marker` in `text` (test convenience:
    mirrors where a caret sits right after typing `marker`)."""
    index = text.index(marker)
    return index + len(marker)


#: A realistic `pg_get_functiondef` result -- the exact shape the DDL object
#: editor's buffer holds, body and all.
FUNCTIONDEF = """CREATE OR REPLACE FUNCTION hr.touch_jobcard(p_id integer, INOUT p_note text DEFAULT 'x')
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
  rec      hr.jobcard%ROWTYPE;
  card_id  hr.jobcard.id%TYPE;
  msg      CONSTANT text := 'changed';
  total    numeric(12,2) NOT NULL DEFAULT 0;
  legacy   ALIAS FOR $1;
  cur      CURSOR (a integer) FOR SELECT 1;
BEGIN
  -- marker: outer body
  RETURN NEW;
END
$function$
"""


# --- the routine header ----------------------------------------------------


def test_header_identity_and_trigger_return():
    scope = analyze_routine_scope(FUNCTIONDEF, _pos(FUNCTIONDEF, "-- marker: outer body"))
    assert (scope.routine_kind, scope.schema, scope.name) == ("function", "hr", "touch_jobcard")
    assert scope.returns == "trigger"
    assert scope.is_trigger is True
    assert scope.in_body is True


def test_named_parameters_with_modes_and_defaults():
    scope = analyze_routine_scope(FUNCTIONDEF, _pos(FUNCTIONDEF, "-- marker: outer body"))
    params = scope.parameters
    assert [p.name for p in params] == ["p_id", "p_note"]
    assert [p.type_text for p in params] == ["integer", "text"]
    assert [p.mode for p in params] == [None, "inout"]
    assert all(p.kind == PARAMETER for p in params)


def test_unnamed_parameters_declare_no_local_name():
    text = "create function hr.f(integer, character varying, numeric(12,2)) returns int as $$ begin $$"
    scope = analyze_routine_scope(text, _pos(text, "begin"))
    assert scope.parameters == ()
    assert scope.is_trigger is False


def test_procedure_without_returns():
    text = "create procedure hr.p(a int) language plpgsql as $$ begin $$"
    scope = analyze_routine_scope(text, _pos(text, "begin"))
    assert scope.routine_kind == "procedure"
    assert scope.returns is None
    assert scope.names == ("a",)


def test_returns_table_is_read_whole():
    text = "create function hr.f() returns table(a int, b int) language plpgsql as $$ begin $$"
    scope = analyze_routine_scope(text, _pos(text, "begin"))
    assert scope.returns == "table(a int, b int)"
    assert scope.is_trigger is False


def test_event_trigger_counts_as_a_trigger_function():
    text = "create function hr.f() returns event_trigger as $$ begin $$"
    assert analyze_routine_scope(text, _pos(text, "begin")).is_trigger is True


# --- DECLARE variables -----------------------------------------------------


def test_declare_variables_are_visible_in_the_body():
    scope = analyze_routine_scope(FUNCTIONDEF, _pos(FUNCTIONDEF, "-- marker: outer body"))
    assert scope.names == ("p_id", "p_note", "rec", "card_id", "msg", "total", "legacy", "cur")
    assert bool(scope) is True
    assert len(scope) == 8


def test_rowtype_resolves_to_a_known_columns_key():
    scope = analyze_routine_scope(FUNCTIONDEF, _pos(FUNCTIONDEF, "-- marker: outer body"))
    rec = scope.resolve("rec")
    assert (rec.kind, rec.type_text) == (VARIABLE, "hr.jobcard%ROWTYPE")
    assert rec.rowtype == "hr.jobcard"
    assert rec.rowtype_qualified == "hr.jobcard"  # the SchemaIndex.known_columns key


def test_bare_rowtype_has_no_qualified_key_and_no_schema_is_guessed():
    text = "create function f() returns int as $$\ndeclare r jobcard%ROWTYPE;\nbegin\nr.\n"
    scope = analyze_routine_scope(text, _pos(text, "r."))
    assert scope.resolve("r").rowtype == "jobcard"
    assert scope.resolve("r").rowtype_qualified is None


def test_typeof_is_recorded_but_not_dereferenced():
    scope = analyze_routine_scope(FUNCTIONDEF, _pos(FUNCTIONDEF, "-- marker: outer body"))
    card_id = scope.resolve("card_id")
    assert card_id.typeof == "hr.jobcard.id"
    assert card_id.rowtype is None
    assert card_id.rowtype_qualified is None


def test_constant_and_initialiser_are_not_part_of_the_type():
    scope = analyze_routine_scope(FUNCTIONDEF, _pos(FUNCTIONDEF, "-- marker: outer body"))
    msg = scope.resolve("msg")
    assert (msg.is_constant, msg.type_text) == (True, "text")


def test_not_null_and_default_are_stepped_over():
    scope = analyze_routine_scope(FUNCTIONDEF, _pos(FUNCTIONDEF, "-- marker: outer body"))
    assert scope.resolve("total").type_text == "numeric(12,2)"


def test_alias_for_records_its_target():
    scope = analyze_routine_scope(FUNCTIONDEF, _pos(FUNCTIONDEF, "-- marker: outer body"))
    legacy = scope.resolve("legacy")
    assert (legacy.kind, legacy.alias_for) == (ALIAS, "$1")


def test_cursor_declaration():
    scope = analyze_routine_scope(FUNCTIONDEF, _pos(FUNCTIONDEF, "-- marker: outer body"))
    assert scope.resolve("cur").kind == CURSOR


def test_resolve_is_case_insensitive_and_unknown_names_are_none():
    scope = analyze_routine_scope(FUNCTIONDEF, _pos(FUNCTIONDEF, "-- marker: outer body"))
    assert scope.resolve("REC").rowtype == "hr.jobcard"
    assert scope.resolve("nope") is None
    assert scope.resolve("") is None


def test_quoted_identifiers_are_unwrapped():
    text = 'create function f() returns int as $$\ndeclare "My Var" hr."Job Card"%ROWTYPE;\nbegin\nx\n'
    scope = analyze_routine_scope(text, _pos(text, "\nx"))
    symbol = scope.resolve("My Var")
    assert symbol is not None
    assert symbol.rowtype_qualified == "hr.Job Card"


# --- loop variables --------------------------------------------------------


def test_for_loop_variable_is_offered_by_name_only():
    text = (
        "create function f() returns int as $$\nbegin\n"
        "  for rec in select * from hr.jobcard loop\n    rec.\n  end loop;\nend\n$$"
    )
    scope = analyze_routine_scope(text, _pos(text, "rec."))
    rec = scope.resolve("rec")
    assert (rec.kind, rec.rowtype_qualified, rec.type_text) == (LOOP_VARIABLE, None, None)


def test_foreach_loop_variable():
    text = (
        "create function f() returns int as $$\nbegin\n"
        "  foreach x in array $1 loop\n    x\n  end loop;\nend\n$$"
    )
    assert analyze_routine_scope(text, _pos(text, "\n    x")).names == ("x",)


def test_for_update_is_not_a_loop_variable():
    text = "create function f() returns int as $$\nbegin\n  select 1 from t for update;\n  x\nend\n$$"
    assert analyze_routine_scope(text, _pos(text, "\n  x")).names == ()


# --- the nested-scope boundary ---------------------------------------------

NESTED = """create function f() returns int as $$
declare
  outer_v int;
begin
  declare
    inner_v int;
  begin
    -- marker: inside inner
    inner_v := 1;
  end;
  -- marker: after inner
  return outer_v;
end
$$
"""


def test_inner_block_variables_are_visible_inside_that_block():
    scope = analyze_routine_scope(NESTED, _pos(NESTED, "-- marker: inside inner"))
    assert scope.names == ("outer_v", "inner_v")


def test_inner_block_variables_drop_out_after_its_end():
    scope = analyze_routine_scope(NESTED, _pos(NESTED, "-- marker: after inner"))
    assert scope.names == ("outer_v",)


def test_declarations_after_the_caret_are_not_yet_in_scope():
    text = "create function f() returns int as $$\ndeclare\n  a int;\n  b int;\nbegin\nend\n$$"
    scope = analyze_routine_scope(text, _pos(text, "  a int;"))
    assert scope.names == ("a",)


def test_an_unclosed_block_degrades_to_visible_from_its_declare_onward():
    """The normal state while typing: `END` is not written yet, and the
    variables must still complete."""
    text = "create function f() returns int as $$\ndeclare\n  a int;\nbegin\n  declare\n    b int;\n  begin\n    "
    assert analyze_routine_scope(text, len(text)).names == ("a", "b")


def test_end_if_and_end_loop_do_not_close_the_enclosing_block():
    text = (
        "create function f() returns int as $$\ndeclare a int;\nbegin\n"
        "  if a > 0 then\n    for i in 1..2 loop\n      null;\n    end loop;\n  end if;\n"
        "  -- marker\nend\n$$"
    )
    assert "a" in analyze_routine_scope(text, _pos(text, "-- marker")).names


def test_an_expression_case_end_does_not_close_the_enclosing_block():
    text = (
        "create function f() returns int as $$\ndeclare a int;\nbegin\n"
        "  a := case when true then 1 else 2 end;\n  -- marker\nend\n$$"
    )
    assert "a" in analyze_routine_scope(text, _pos(text, "-- marker")).names


def test_inner_declaration_shadows_the_outer_one():
    text = (
        "create function f() returns int as $$\ndeclare v text;\nbegin\n"
        "  declare v hr.jobcard%ROWTYPE;\n  begin\n    -- marker\n  end;\nend\n$$"
    )
    scope = analyze_routine_scope(text, _pos(text, "-- marker"))
    assert scope.resolve("v").rowtype_qualified == "hr.jobcard"


# --- opaque regions --------------------------------------------------------


def test_a_declare_inside_a_string_is_not_a_declaration():
    text = (
        "create function f() returns int as $$\nbegin\n"
        "  raise notice 'declare ghost int;';\n  -- marker\nend\n$$"
    )
    assert analyze_routine_scope(text, _pos(text, "-- marker")).names == ()


def test_a_declare_inside_a_line_comment_is_not_a_declaration():
    text = (
        "create function f() returns int as $$\nbegin\n"
        "  -- declare ghost int;\n  -- marker\nend\n$$"
    )
    assert analyze_routine_scope(text, _pos(text, "-- marker")).names == ()


def test_a_declare_inside_a_block_comment_is_not_a_declaration():
    text = (
        "create function f() returns int as $$\nbegin\n"
        "  /* declare ghost int; */\n  -- marker\nend\n$$"
    )
    assert analyze_routine_scope(text, _pos(text, "-- marker")).names == ()


def test_a_nested_dollar_body_stays_opaque_to_the_outer_body():
    text = (
        "create function f() returns int as $outer$\ndeclare a int;\nbegin\n"
        "  execute $inner$ declare ghost int; $inner$;\n  -- marker\nend\n$outer$"
    )
    assert analyze_routine_scope(text, _pos(text, "-- marker")).names == ("a",)


def test_a_caret_inside_a_nested_dollar_body_sees_that_body():
    text = (
        "create function f() returns int as $outer$\ndeclare a int;\nbegin\n"
        "  execute $inner$ declare ghost int; begin ghost\n"
    )
    assert analyze_routine_scope(text, _pos(text, "begin ghost")).names == ("ghost",)


def test_other_statements_in_the_buffer_do_not_leak_in():
    text = (
        "create function hr.a() returns int as $$ declare v_a int; begin end $$;\n"
        "create function hr.b() returns int as $$ declare v_b int; begin \n"
    )
    scope = analyze_routine_scope(text, len(text))
    assert scope.name == "b"
    assert scope.names == ("v_b",)


def test_a_bare_do_block_still_yields_its_declarations():
    text = "do $$\ndeclare v int;\nbegin\n  v\nend\n$$"
    scope = analyze_routine_scope(text, _pos(text, "  v"))
    assert scope.names == ("v",)
    assert scope.routine_kind is None


def test_a_body_only_buffer_is_read_within_the_caret_s_statement():
    """A raw block with no `CREATE` header and no `$$` wrapper is still read --
    but scope is per statement (`sql/statements.py::statement_at`, shared with
    `sql/from_clause.py`), so its `;`-terminated declarations belong to their
    own statements. The documented limitation, not a silent wrong answer."""
    text = "declare v int"
    scope = analyze_routine_scope(text, len(text))
    assert scope.names == ("v",)
    assert scope.in_body is False
    split = "declare v int;\nbegin\n  v\nend"
    assert analyze_routine_scope(split, _pos(split, "  v")).names == ()


# --- degrading rather than raising -----------------------------------------


def test_empty_and_out_of_range_positions_are_answers_not_errors():
    assert analyze_routine_scope("", 0).names == ()
    # Out-of-range offsets are clamped into the buffer rather than refused.
    assert analyze_routine_scope(FUNCTIONDEF, -50).names == ("p_id", "p_note")
    assert analyze_routine_scope(FUNCTIONDEF, 10**6).names is not None


def test_every_prefix_of_a_typed_routine_definition_degrades_without_raising():
    """The editor calls this on every keystroke, so every intermediate state of
    typing the definition must answer rather than raise."""
    for i in range(len(FUNCTIONDEF) + 1):
        assert analyze_routine_scope(FUNCTIONDEF[:i], i) is not None
        assert analyze_routine_scope(FUNCTIONDEF, i) is not None


def test_malformed_fragments_never_raise():
    fragments = (
        "create function",
        "create function hr.",
        "create function hr.f(",
        "create function hr.f() returns",
        "create function hr.f() returns int as $$",
        "$$ declare",
        "declare ;;;",
        "declare 1 int;",
        "declare v",
        "$$ declare v int; begin end end end $$",
        "declare v alias for",
        "declare v hr.%ROWTYPE;",
        "declare v %ROWTYPE;",
        "for in loop",
    )
    for text in fragments:
        for pos in range(len(text) + 1):
            analyze_routine_scope(text, pos)  # must not raise


def test_nested_bodies_are_depth_bounded_rather_than_infinite():
    text = "declare v int; begin v"
    for tag in ("a", "b", "c", "d", "e", "f", "g", "h"):
        text = f"${tag}$ {text} ${tag}$"
    analyze_routine_scope(text, text.index("begin v"))  # must not raise or hang


# --- the trigger-variable table --------------------------------------------


def test_trigger_variables_are_the_plpgsql_set_in_offer_order():
    names = trigger_variable_names()
    assert names[:2] == ("NEW", "OLD")
    assert "TG_OP" in names and "TG_TABLE_NAME" in names and "TG_ARGV" in names
    assert len(names) == len(TRIGGER_VARIABLES) == len(set(names))
    assert dict(TRIGGER_VARIABLES)["TG_ARGV"] == "text[]"
