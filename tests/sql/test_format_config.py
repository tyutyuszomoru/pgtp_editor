"""The formatter's bounded configuration model (spec §18.4 A+B). Pure, no Qt.

The point of these tests is the BOUND, not the plumbing: every value has a
documented domain, `sanitized()` is the single lenient gate that enforces it,
and it never raises -- because §18.4 rules that a formatter preference is
re-derivable from the dialog in ten seconds, so refusing to load would be
ceremony.
"""
from __future__ import annotations

import pytest

from pgtp_editor.sql import DEFAULT_FORMAT_CONFIG, FormatConfig
from pgtp_editor.sql.format_config import (
    CLAUSE_STARTERS,
    DEFAULT_CLAUSE_RULE,
    DEFAULT_INDENT_UNIT,
    MAX_CLAUSE_INDENT_LEVELS,
    MAX_INDENT_WIDTH,
    ClauseRule,
    KeywordCase,
    indent_unit_for,
)


def test_the_default_config_is_todays_shipped_behaviour():
    assert DEFAULT_FORMAT_CONFIG == FormatConfig()
    assert DEFAULT_FORMAT_CONFIG.indent_unit == DEFAULT_INDENT_UNIT
    assert DEFAULT_FORMAT_CONFIG.keyword_case is KeywordCase.AS_IS
    assert DEFAULT_FORMAT_CONFIG.clause_rules == {}
    assert DEFAULT_FORMAT_CONFIG.join_phrase_break is True


def test_clause_rules_are_sparse_and_absent_keys_mean_the_shipped_rule():
    config = FormatConfig(clause_rules={"join": ClauseRule(break_before=False)})
    assert config.rule_for("join") == ClauseRule(break_before=False, indent_levels=0)
    for keyword in CLAUSE_STARTERS - {"join"}:
        assert config.rule_for(keyword) == DEFAULT_CLAUSE_RULE
    # A keyword the engine has not got a rule for at all still answers.
    assert config.rule_for("mumble") == DEFAULT_CLAUSE_RULE


def test_sanitized_drops_unknown_clause_keywords():
    config = FormatConfig(
        clause_rules={"where": ClauseRule(indent_levels=1), "mumble": ClauseRule()}
    ).sanitized()
    assert set(config.clause_rules) == {"where"}


def test_sanitized_drops_entries_equal_to_the_default():
    # Sparse means sparse: an entry equal to the default carries no information
    # and would pin the keyword into saved settings for no reason.
    assert FormatConfig(clause_rules={"where": ClauseRule()}).sanitized().clause_rules == {}


@pytest.mark.parametrize("levels,expected", [(-3, 0), (0, 0), (4, 4), (9, MAX_CLAUSE_INDENT_LEVELS)])
def test_sanitized_clamps_indent_levels(levels, expected):
    config = FormatConfig(clause_rules={"from": ClauseRule(indent_levels=levels)}).sanitized()
    assert config.rule_for("from").indent_levels == expected


@pytest.mark.parametrize(
    "unit,expected",
    [
        ("  ", "  "),
        ("\t", "\t"),
        ("", DEFAULT_INDENT_UNIT),
        (" " * 40, " " * MAX_INDENT_WIDTH),
        ("xx", DEFAULT_INDENT_UNIT),
        ("\t\t", DEFAULT_INDENT_UNIT),
        (None, DEFAULT_INDENT_UNIT),
        (4, DEFAULT_INDENT_UNIT),
    ],
)
def test_sanitized_confines_the_indent_unit(unit, expected):
    assert FormatConfig(indent_unit=unit).sanitized().indent_unit == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("upper", KeywordCase.UPPER),
        ("UPPER", KeywordCase.UPPER),
        ("  lower  ", KeywordCase.LOWER),
        ("as-is", KeywordCase.AS_IS),
        ("nonsense", KeywordCase.AS_IS),
        (None, KeywordCase.AS_IS),
        (7, KeywordCase.AS_IS),
        (KeywordCase.UPPER, KeywordCase.UPPER),
    ],
)
def test_keyword_case_parses_leniently_and_never_raises(value, expected):
    assert KeywordCase.parse(value) is expected
    assert FormatConfig(keyword_case=value).sanitized().keyword_case is expected


def test_sanitized_never_raises_on_junk():
    junk = FormatConfig(
        indent_unit=object(),
        keyword_case=object(),
        clause_rules={"select": "not a rule", 7: ClauseRule()},  # type: ignore[dict-item]
        join_phrase_break="yes",
    ).sanitized()
    assert junk.indent_unit == DEFAULT_INDENT_UNIT
    assert junk.keyword_case is KeywordCase.AS_IS
    assert junk.clause_rules == {}
    assert junk.join_phrase_break is True


def test_sanitized_is_idempotent():
    config = FormatConfig(
        indent_unit=" " * 40,
        keyword_case="UPPER",
        clause_rules={"from": ClauseRule(indent_levels=9), "mumble": ClauseRule()},
    ).sanitized()
    assert config.sanitized() == config


@pytest.mark.parametrize(
    "width,use_tab,expected",
    [(1, False, " "), (4, False, "    "), (0, False, " "), (99, False, " " * 8), (2, True, "\t")],
)
def test_indent_unit_for_bounds_the_dialogs_choices(width, use_tab, expected):
    assert indent_unit_for(width, use_tab) == expected


def test_indent_width_and_uses_tab_read_back_for_the_dialog():
    assert FormatConfig(indent_unit="  ").indent_width == 2
    assert FormatConfig(indent_unit="  ").uses_tab is False
    tabbed = FormatConfig(indent_unit="\t")
    assert tabbed.uses_tab is True
    # A tab has no width; the dialog shows the default so the spin box is never
    # blank when the user switches back to spaces.
    assert tabbed.indent_width == len(DEFAULT_INDENT_UNIT)


def test_case_of_applies_only_the_configured_transform():
    assert FormatConfig().case_of("Select") == "Select"
    assert FormatConfig(keyword_case=KeywordCase.UPPER).case_of("Select") == "SELECT"
    assert FormatConfig(keyword_case=KeywordCase.LOWER).case_of("Select") == "select"


def test_keyword_case_values_are_the_persisted_tokens():
    # `ui/format_settings.py` writes these strings into the ini file; a reader
    # opening it should see words, not enum ordinals.
    assert [member.value for member in KeywordCase] == ["as-is", "upper", "lower"]
