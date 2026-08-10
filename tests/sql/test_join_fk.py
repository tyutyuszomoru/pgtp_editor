"""JOIN-on-FK (`pgtp_editor/sql/join_fk.py`) -- FQ-030 slice 3.

The layer decides *what the join should look like*; the caller injects *what
the foreign keys are*. These tests therefore never build a schema: they hand
`ForeignKey` values in, exactly as the UI pass will from `ColumnInfo.fk_target`.
"""
from __future__ import annotations

import pytest

from pgtp_editor.sql.join_fk import (
    INCOMING,
    OUTGOING,
    ForeignKey,
    JoinCandidate,
    find_join_site,
    foreign_keys_from_targets,
    join_candidates,
    render_join,
)

DEPT_FK = ForeignKey("hr.jobcard", "dept_id", "hr.department", "id")


def _caret(text: str, marker: str = "|") -> tuple[str, int]:
    """Split a `|`-marked fixture into `(text, caret_offset)`."""
    pos = text.index(marker)
    return text[:pos] + text[pos + 1 :], pos


def _expand(text: str, pos: int, keys=(DEPT_FK,), pick: int = 0) -> str:
    site = find_join_site(text, pos)
    options = join_candidates(site, keys)
    expansion = render_join(site, options.candidates[pick])
    assert expansion, expansion.reason
    return expansion.apply(text)


# --- the single unambiguous FK --------------------------------------------


def test_a_single_foreign_key_renders_the_whole_join_clause():
    text, pos = _caret("SELECT * FROM hr.jobcard j|")
    assert _expand(text, pos) == (
        "SELECT * FROM hr.jobcard j JOIN hr.department d ON j.dept_id = d.id"
    )


def test_the_expansion_is_a_pure_insertion_at_the_end_of_the_from_item():
    text, pos = _caret("SELECT * FROM hr.jobcard j| WHERE j.id = 1")
    site = find_join_site(text, pos)
    expansion = render_join(site, join_candidates(site, [DEPT_FK]).only)
    assert expansion.start == expansion.end == site.insert_at
    assert expansion.apply(text) == (
        "SELECT * FROM hr.jobcard j JOIN hr.department d ON j.dept_id = d.id"
        " WHERE j.id = 1"
    )


def test_the_join_is_appended_after_the_from_item_even_with_a_caret_earlier():
    text, pos = _caret("SELECT j.|x FROM hr.jobcard j WHERE j.id = 1")
    assert _expand(text, pos).startswith(
        "SELECT j.x FROM hr.jobcard j JOIN hr.department d ON j.dept_id = d.id"
    )


def test_a_join_keyword_already_typed_is_kept_and_not_written_twice():
    text, pos = _caret("SELECT * FROM hr.jobcard j LEFT JOIN |")
    site = find_join_site(text, pos)
    assert site.keyword_written is True
    assert site.insert_at == pos
    assert _expand(text, pos) == (
        "SELECT * FROM hr.jobcard j LEFT JOIN hr.department d ON j.dept_id = d.id"
    )


def test_an_unaliased_table_is_referred_to_by_its_own_name():
    text, pos = _caret("SELECT * FROM hr.jobcard|")
    assert _expand(text, pos).endswith("ON jobcard.dept_id = d.id")


def test_lowercase_keywords_generate_lowercase_join_and_on():
    text, pos = _caret("select * from hr.jobcard j|")
    assert _expand(text, pos).endswith("join hr.department d on j.dept_id = d.id")


def test_an_incoming_foreign_key_still_reads_source_first():
    text, pos = _caret("SELECT * FROM hr.department d|")
    candidate = join_candidates(find_join_site(text, pos), [DEPT_FK]).only
    assert candidate is not None
    assert candidate.direction == INCOMING
    assert candidate.target_qualified == "hr.jobcard"
    assert _expand(text, pos).endswith("JOIN hr.jobcard j ON d.id = j.dept_id")


def test_an_outgoing_key_is_labelled_outgoing():
    text, pos = _caret("SELECT * FROM hr.jobcard j|")
    assert join_candidates(find_join_site(text, pos), [DEPT_FK]).only.direction == (
        OUTGOING
    )


def test_a_mixed_case_table_name_is_quoted_in_the_generated_clause():
    text, pos = _caret("SELECT * FROM hr.jobcard j|")
    key = ForeignKey("hr.jobcard", "dept_id", "HR.Department", "Id")
    assert _expand(text, pos, [key]).endswith(
        'JOIN "HR"."Department" d ON j.dept_id = d."Id"'
    )


# --- alias derivation ------------------------------------------------------


def test_the_alias_avoids_one_already_written_in_the_statement():
    text, pos = _caret("SELECT * FROM hr.jobcard j, hr.driver d|")
    key = ForeignKey("hr.driver", "dept_id", "hr.department", "id")
    assert _expand(text, pos, [key]).endswith(
        "JOIN hr.department d2 ON d.dept_id = d2.id"
    )


def test_a_derived_items_name_counts_as_taken_even_though_it_is_no_source():
    text, pos = _caret("SELECT * FROM hr.jobcard j, (SELECT 1) d|")
    site = find_join_site(text, pos)
    assert [item.ref.name for item in site.items] == ["j"]
    assert "d" in site.taken
    assert _expand(text, pos).endswith("JOIN hr.department d2 ON j.dept_id = d2.id")


# --- ambiguity: a list, never a guess and never a refusal ------------------


def test_two_keys_to_the_same_table_are_two_candidates_in_a_stable_order():
    text, pos = _caret("SELECT * FROM hr.jobcard j|")
    keys = [
        ForeignKey("hr.jobcard", "created_by", "hr.person", "id"),
        ForeignKey("hr.jobcard", "approved_by", "hr.person", "id"),
    ]
    options = join_candidates(find_join_site(text, pos), keys)
    assert len(options) == 2
    assert options.only is None  # ambiguous: the caller must offer a choice
    assert [candidate.source_column for candidate in options] == [
        "approved_by",
        "created_by",
    ]
    assert _expand(text, pos, keys, pick=1).endswith(
        "JOIN hr.person p ON j.created_by = p.id"
    )


def test_a_self_referencing_key_is_a_candidate_with_a_distinct_alias():
    text, pos = _caret("SELECT * FROM hr.employee e|")
    key = ForeignKey("hr.employee", "manager_id", "hr.employee", "id")
    candidate = join_candidates(find_join_site(text, pos), [key]).only
    assert candidate is not None
    assert candidate.is_self_join is True
    assert _expand(text, pos, [key]).endswith(
        "JOIN hr.employee e2 ON e.manager_id = e2.id"
    )


def test_a_table_not_yet_in_the_statement_is_offered_before_one_already_there():
    text, pos = _caret("SELECT * FROM hr.jobcard j, hr.department d|")
    keys = [
        ForeignKey("hr.jobcard", "dept_id", "hr.department", "id"),
        ForeignKey("hr.jobcard", "driver_id", "hr.driver", "id"),
    ]
    options = join_candidates(find_join_site(text, pos), keys)
    # `hr.department` and `hr.jobcard` are both already written, so a second
    # reference to either is offered -- last, and never suppressed: a second
    # role for the same table is legitimate SQL and refusing it would be a
    # guess about intent.
    assert [candidate.target_qualified for candidate in options] == [
        "hr.driver",
        "hr.department",
        "hr.jobcard",
    ]


def test_a_composite_key_named_by_its_constraint_becomes_one_and_clause():
    text, pos = _caret("SELECT * FROM hr.jobcard j|")
    keys = [
        ForeignKey("hr.jobcard", "co", "hr.line", "co", constraint="jobcard_line_fk"),
        ForeignKey("hr.jobcard", "no", "hr.line", "no", constraint="jobcard_line_fk"),
    ]
    options = join_candidates(find_join_site(text, pos), keys)
    assert len(options) == 1
    assert _expand(text, pos, keys).endswith(
        "JOIN hr.line l ON j.co = l.co AND j.no = l.no"
    )


def test_the_same_key_injected_twice_is_offered_once():
    text, pos = _caret("SELECT * FROM hr.jobcard j|")
    options = join_candidates(find_join_site(text, pos), [DEPT_FK, DEPT_FK])
    assert len(options) == 1


# --- refusals: falsy, with a reason ---------------------------------------


@pytest.mark.parametrize(
    "fixture",
    [
        "|",
        "SELECT 1|",
        "SELECT * FROM (SELECT 1) x|",
    ],
)
def test_a_site_without_a_qualified_table_refuses_with_a_reason(fixture):
    text, pos = _caret(fixture)
    site = find_join_site(text, pos)
    assert not site
    assert site.reason


def test_a_bare_table_is_not_a_join_source_because_no_schema_is_guessed():
    text, pos = _caret("SELECT * FROM jobcard j|")
    site = find_join_site(text, pos)
    assert not site
    assert "schema-qualified" in site.reason


def test_no_relevant_foreign_key_is_an_empty_option_list_with_a_reason():
    text, pos = _caret("SELECT * FROM hr.jobcard j|")
    options = join_candidates(
        find_join_site(text, pos),
        [ForeignKey("other.thing", "a", "other.other", "b")],
    )
    assert not options
    assert options.reason
    assert list(options) == []


def test_no_foreign_keys_at_all_is_a_reason_not_an_exception():
    text, pos = _caret("SELECT * FROM hr.jobcard j|")
    assert join_candidates(find_join_site(text, pos), []).reason


def test_rendering_a_refused_site_carries_the_sites_reason():
    site = find_join_site("SELECT 1", 8)
    expansion = render_join(site, None)
    assert not expansion
    assert expansion.reason == site.reason


def test_rendering_without_a_candidate_never_raises():
    text, pos = _caret("SELECT * FROM hr.jobcard j|")
    assert not render_join(find_join_site(text, pos), None)


# --- malformed input degrades ---------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "SELECT * FROM hr.jobcard j JOIN",
        "SELECT * FROM hr.'unterminated",
        "SELECT * FROM hr.jobcard j /* unclosed",
        "SELECT * FROM hr.jobcard j WHERE (((",
        "$$ SELECT * FROM hr.jobcard j",
        ",,,,",
    ],
)
def test_malformed_input_never_raises_at_any_caret(text):
    for pos in range(len(text) + 1):
        site = find_join_site(text, pos)
        options = join_candidates(site, [DEPT_FK])
        for candidate in options:
            assert isinstance(candidate, JoinCandidate)
            render_join(site, candidate)


def test_a_caret_inside_a_routine_body_joins_the_bodys_own_from_clause():
    text, pos = _caret(
        "CREATE FUNCTION f() RETURNS int LANGUAGE plpgsql AS $$\n"
        "BEGIN\n"
        "  SELECT * FROM hr.jobcard j|;\n"
        "END;\n"
        "$$;"
    )
    assert "JOIN hr.department d ON j.dept_id = d.id;" in _expand(text, pos)


# --- the fk_target adapter -------------------------------------------------


def test_fk_targets_are_parsed_into_keys_and_unusable_ones_are_skipped():
    keys = foreign_keys_from_targets(
        "hr.jobcard",
        [
            ("dept_id", "hr.department.id"),
            ("name", None),
            ("bad", "department.id"),  # two segments: no schema, not guessed
            ("worse", "a.b.c.d"),
            ("", "hr.department.id"),
        ],
    )
    assert keys == (ForeignKey("hr.jobcard", "dept_id", "hr.department", "id"),)


def test_the_adapter_output_drives_the_gesture_end_to_end():
    text, pos = _caret("SELECT * FROM hr.jobcard j|")
    keys = foreign_keys_from_targets("hr.jobcard", [("dept_id", "hr.department.id")])
    assert _expand(text, pos, keys).endswith("ON j.dept_id = d.id")


def test_candidate_display_and_key_are_stable_for_a_popup():
    text, pos = _caret("SELECT * FROM hr.jobcard j|")
    candidate = join_candidates(find_join_site(text, pos), [DEPT_FK]).only
    assert candidate.key == "hr.department:j.dept_id"
    assert candidate.display == "hr.department d ON j.dept_id = d.id"
