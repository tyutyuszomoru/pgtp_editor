# tests/sql/test_from_clause.py
"""Tests for pgtp_editor.sql.from_clause -- the Qt-free FROM-clause / alias
scope analyzer behind alias-aware completion (spec §18.6, FQ-030 slice 1)."""
from pgtp_editor.sql.from_clause import FromScope, TableRef, analyze_from_scope


def _pos(text: str, marker: str) -> int:
    """The 0-based offset right after `marker` in `text` (test convenience:
    mirrors where a caret sits right after typing `marker`)."""
    index = text.index(marker)
    return index + len(marker)


# --- alias forms -----------------------------------------------------------


def test_alias_without_as():
    text = "select * from hr.jobcard jc where jc."
    ref = analyze_from_scope(text, len(text)).resolve("jc")
    assert ref == TableRef(schema="hr", table="jobcard", alias="jc", name="jc")
    assert ref.qualified == "hr.jobcard"


def test_alias_with_as():
    text = "select * from hr.jobcard as jc where jc."
    ref = analyze_from_scope(text, len(text)).resolve("jc")
    assert ref.qualified == "hr.jobcard"
    assert ref.alias == "jc"


def test_as_keyword_is_case_insensitive():
    text = "select * from hr.jobcard AS jc where jc."
    assert analyze_from_scope(text, len(text)).resolve("jc").alias == "jc"


def test_unaliased_qualified_table_is_referenced_by_its_own_name():
    text = "select * from hr.jobcard where jobcard."
    scope = analyze_from_scope(text, len(text))
    ref = scope.resolve("jobcard")
    assert ref == TableRef(schema="hr", table="jobcard", alias=None, name="jobcard")
    assert ref.qualified == "hr.jobcard"
    assert scope.resolve("hr") is None  # the schema is not a reference


def test_bare_table_has_no_schema_and_is_never_guessed():
    text = "select * from jobcard where jobcard."
    ref = analyze_from_scope(text, len(text)).resolve("jobcard")
    assert ref.schema is None
    assert ref.table == "jobcard"
    assert ref.qualified is None


def test_bare_table_with_alias():
    text = "select * from jobcard jc where jc."
    ref = analyze_from_scope(text, len(text)).resolve("jc")
    assert (ref.schema, ref.table, ref.alias) == (None, "jobcard", "jc")


def test_alias_lookup_is_case_insensitive():
    text = "select * from hr.jobcard JC where jc."
    assert analyze_from_scope(text, len(text)).resolve("jc").qualified == "hr.jobcard"


def test_quoted_identifiers_are_unwrapped():
    text = 'select * from "HR"."Job Card" "My Alias" where x'
    ref = analyze_from_scope(text, len(text)).resolve("My Alias")
    assert (ref.schema, ref.table, ref.alias) == ("HR", "Job Card", "My Alias")
    assert ref.qualified == "HR.Job Card"


# --- multiple tables and joins ---------------------------------------------


def test_comma_separated_from_list():
    text = "select * from hr.jobcard jc, hr.dept d, staff where jc."
    scope = analyze_from_scope(text, len(text))
    assert scope.names == ("jc", "d", "staff")
    assert scope.resolve("d").qualified == "hr.dept"
    assert scope.resolve("staff").schema is None


def test_inner_join_with_on_clause():
    text = "select * from hr.jobcard jc join hr.dept d on jc.dept_id = d.id where d."
    scope = analyze_from_scope(text, len(text))
    assert scope.names == ("jc", "d")
    assert scope.resolve("d").qualified == "hr.dept"


def test_left_outer_join_and_using_clause():
    text = (
        "select * from hr.jobcard jc "
        "left outer join hr.dept as d using (dept_id) "
        "where jc."
    )
    scope = analyze_from_scope(text, len(text))
    assert scope.names == ("jc", "d")


def test_natural_join_does_not_swallow_the_word_natural_as_an_alias():
    text = "select * from hr.jobcard natural join hr.dept where x"
    scope = analyze_from_scope(text, len(text))
    assert scope.names == ("jobcard", "dept")


def test_chained_joins():
    text = (
        "select * from a.one o "
        "join b.two t on o.id = t.id "
        "inner join c.three th on t.id = th.id "
        "where th."
    )
    scope = analyze_from_scope(text, len(text))
    assert scope.names == ("o", "t", "th")
    assert scope.resolve("th").qualified == "c.three"


def test_update_statement_alias_resolves():
    text = "update hr.jobcard jc set job = 1 where jc."
    assert analyze_from_scope(text, len(text)).resolve("jc").qualified == "hr.jobcard"


def test_delete_from_only_steps_over_the_only_keyword():
    text = "delete from only hr.jobcard jc where jc."
    assert analyze_from_scope(text, len(text)).resolve("jc").qualified == "hr.jobcard"


# --- caret placement inside its scope --------------------------------------


def test_caret_in_the_select_list_before_the_from_clause_still_sees_it():
    """The scope is the whole statement, not "what was typed so far" -- going
    back to fill in `select jc.<caret> from hr.jobcard jc` is the main case."""
    text = "select jc. from hr.jobcard jc"
    scope = analyze_from_scope(text, _pos(text, "select jc."))
    assert scope.resolve("jc").qualified == "hr.jobcard"


def test_caret_in_trailing_whitespace_after_the_statement_keeps_the_scope():
    text = "select * from hr.jobcard jc where jc.   "
    assert analyze_from_scope(text, len(text)).resolve("jc") is not None


# --- statement boundaries ---------------------------------------------------


def test_caret_in_the_second_statement_does_not_see_the_first():
    text = "select * from hr.jobcard jc;\nselect * from hr.dept d where d."
    scope = analyze_from_scope(text, len(text))
    assert scope.names == ("d",)
    assert scope.resolve("jc") is None


def test_caret_in_the_third_of_three_statements_sees_only_its_own():
    text = (
        "select * from a.one o;\n"
        "select * from b.two t;\n"
        "select * from c.three th where th."
    )
    scope = analyze_from_scope(text, len(text))
    assert scope.names == ("th",)


def test_caret_in_the_first_statement_does_not_see_a_later_one():
    text = "select * from a.one o where o.;\nselect * from b.two t"
    scope = analyze_from_scope(text, _pos(text, "where o."))
    assert scope.names == ("o",)


def test_caret_before_any_statement_has_no_scope():
    text = "   \nselect * from hr.jobcard jc"
    assert analyze_from_scope(text, 2) == FromScope()


def test_statement_with_no_from_clause_has_no_scope():
    scope = analyze_from_scope("select 1 + 1", 5)
    assert not scope
    assert scope.names == ()


def test_semicolon_inside_a_string_does_not_split_the_statement():
    text = "select ';' as sep from hr.jobcard jc where jc."
    assert analyze_from_scope(text, len(text)).resolve("jc").qualified == "hr.jobcard"


# --- opaque regions ---------------------------------------------------------


def test_from_inside_a_string_literal_is_not_a_from_clause():
    text = "select 'from hr.secret s' as note, x"
    assert analyze_from_scope(text, len(text)) == FromScope()


def test_from_inside_a_line_comment_is_not_a_from_clause():
    text = "select 1 -- from hr.secret s\n, 2"
    assert analyze_from_scope(text, len(text)) == FromScope()


def test_from_inside_a_block_comment_is_not_a_from_clause():
    text = "select 1 /* from hr.secret s */ , 2"
    assert analyze_from_scope(text, len(text)) == FromScope()


def test_from_inside_a_dollar_quoted_body_is_invisible_to_the_outer_statement():
    text = (
        "create function f() returns int language plpgsql as $$\n"
        "begin\n"
        "  select * from hr.secret s;\n"
        "end;\n"
        "$$;\n"
        "select * from hr.dept d where d."
    )
    scope = analyze_from_scope(text, len(text))
    assert scope.names == ("d",)
    assert scope.resolve("s") is None


def test_from_inside_a_dollar_quoted_body_is_visible_to_a_caret_inside_it():
    """The body is opaque to the *enclosing* statement (previous test) but is
    its own scope for a caret within it -- both from the same opaque token."""
    text = (
        "create function f() returns int language plpgsql as $$\n"
        "begin\n"
        "  select * from hr.secret s where s.;\n"
        "end;\n"
        "$$;\n"
    )
    scope = analyze_from_scope(text, _pos(text, "where s."))
    assert scope.resolve("s").qualified == "hr.secret"


def test_tagged_dollar_quoted_body_body_is_handled_like_a_bare_one():
    text = (
        "create function f() returns int as $function$\n"
        "  select * from hr.secret s where s.\n"
        "$function$ language sql"
    )
    scope = analyze_from_scope(text, _pos(text, "where s."))
    assert scope.resolve("s").qualified == "hr.secret"


def test_from_inside_a_quoted_identifier_is_not_a_from_clause():
    text = 'select "from hr.secret s" from hr.dept d where d.'
    scope = analyze_from_scope(text, len(text))
    assert scope.names == ("d",)


def test_extract_from_is_argument_syntax_not_a_clause():
    text = "select extract(year from ts) from hr.jobcard jc where jc."
    scope = analyze_from_scope(text, len(text))
    assert scope.names == ("jc",)


# --- subqueries and CTEs ----------------------------------------------------


def test_subquery_alias_does_not_leak_outward():
    text = "select * from hr.dept d where id in (select x from hr.secret s) and d."
    scope = analyze_from_scope(text, len(text))
    assert scope.names == ("d",)


def test_caret_inside_a_subquery_sees_the_inner_and_the_outer_scope():
    """Correct SQL scoping: a correlated subquery may reference the outer
    query's aliases, so both are in scope -- inner first, then outer."""
    text = "select * from hr.dept d where id in (select x from hr.secret s where s.)"
    scope = analyze_from_scope(text, _pos(text, "where s."))
    assert set(scope.names) == {"d", "s"}
    assert scope.resolve("s").qualified == "hr.secret"
    assert scope.resolve("d").qualified == "hr.dept"


def test_derived_table_alias_is_in_scope_but_backed_by_no_table():
    text = "select * from (select 1 as n) sub where sub."
    scope = analyze_from_scope(text, len(text))
    ref = scope.resolve("sub")
    assert ref.is_derived
    assert ref.qualified is None
    assert ref.table is None


def test_derived_table_does_not_hide_a_sibling_join():
    text = "select * from (select 1 as n) sub join hr.dept d on true where d."
    scope = analyze_from_scope(text, len(text))
    assert set(scope.names) == {"sub", "d"}
    assert scope.resolve("d").qualified == "hr.dept"


def test_set_returning_function_is_a_derived_reference():
    text = "select * from generate_series(1, 10) g where g."
    ref = analyze_from_scope(text, len(text)).resolve("g")
    assert ref.is_derived
    assert ref.qualified is None


def test_cte_body_is_its_own_scope():
    text = "with recent as (select * from hr.jobcard jc where jc.) select * from recent"
    scope = analyze_from_scope(text, _pos(text, "where jc."))
    assert scope.resolve("jc").qualified == "hr.jobcard"


def test_cte_name_used_in_from_is_a_bare_unresolvable_reference():
    """Documented limitation: nothing here knows `recent` is a CTE rather than
    a table, and its columns come from a query, not a catalog."""
    text = "with recent as (select 1) select * from recent r where r."
    ref = analyze_from_scope(text, len(text)).resolve("r")
    assert ref.table == "recent"
    assert ref.schema is None
    assert ref.qualified is None


def test_cte_scope_does_not_leak_into_the_main_query():
    text = "with recent as (select * from hr.jobcard jc) select * from hr.dept d where d."
    scope = analyze_from_scope(text, len(text))
    assert scope.names == ("d",)


# --- malformed input never raises -------------------------------------------


def test_from_with_nothing_after_it():
    assert analyze_from_scope("select * from ", 14) == FromScope()


def test_from_followed_by_a_keyword_is_not_a_table():
    assert analyze_from_scope("select * from where x", 21) == FromScope()


def test_half_typed_schema_qualified_name_is_not_yet_a_reference():
    """`from pr.<caret>` is a name mid-typing: recording `pr` would let the
    keystroke that types a schema turn it into an in-scope table."""
    text = "select * from pr."
    assert analyze_from_scope(text, len(text)) == FromScope()


def test_unterminated_string_does_not_raise():
    text = "select * from hr.jobcard jc where note = 'oops"
    assert analyze_from_scope(text, len(text)) is not None


def test_unterminated_dollar_quote_does_not_raise():
    text = "create function f() as $$ select * from hr.secret s"
    assert analyze_from_scope(text, len(text)) is not None


def test_unbalanced_parentheses_do_not_raise():
    text = "select * from (select * from hr.jobcard jc where jc."
    assert analyze_from_scope(text, len(text)) is not None


def test_empty_text_and_out_of_range_positions():
    assert analyze_from_scope("", 0) == FromScope()
    assert analyze_from_scope("", 99) == FromScope()
    # Out-of-range offsets clamp to the buffer rather than failing: 0 and
    # len(text) both land inside the single statement here.
    text = "select * from hr.jobcard jc"
    assert analyze_from_scope(text, -5).resolve("jc") is not None
    assert analyze_from_scope(text, 9999).resolve("jc") is not None


def test_every_prefix_of_a_typed_statement_is_analyzable():
    """An editor calls this on every keystroke: no half-typed prefix may raise
    and none may resolve an alias it has no business knowing."""
    text = "select * from hr.jobcard jc join hr.dept d on jc.dept_id = d.id where jc."
    for i in range(len(text) + 1):
        scope = analyze_from_scope(text[:i], i)
        assert isinstance(scope, FromScope)


def test_resolve_of_an_unknown_or_empty_name():
    text = "select * from hr.jobcard jc"
    scope = analyze_from_scope(text, len(text))
    assert scope.resolve("nope") is None
    assert scope.resolve("") is None
