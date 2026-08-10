"""Persistence for the autoformatter config (spec §18.4 part D).

Every test here injects its own temp-file `QSettings`: a test that wrote to the
developer's real config would be a defect, and `use_settings` exists for exactly
that reason. (`conftest.py`'s `_isolated_qsettings` already redirects the default
store per test, so the two `current_*()` cases below are safe too.)
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings

from pgtp_editor.sql import DEFAULT_FORMAT_CONFIG, FormatConfig
from pgtp_editor.sql.format_config import ClauseRule, KeywordCase
from pgtp_editor.ui import format_settings
from pgtp_editor.xmlfmt import DEFAULT_XML_FORMAT_CONFIG, XmlFormatConfig


@pytest.fixture
def store(tmp_path):
    settings = QSettings(str(tmp_path / "autoformat.ini"), QSettings.Format.IniFormat)
    yield settings
    settings.sync()


@pytest.fixture
def injected(store):
    """`store` installed as the module's active store, released afterwards."""
    format_settings.use_settings(store)
    yield store
    format_settings.use_settings(None)


def test_an_empty_store_yields_the_shipped_defaults(store):
    assert format_settings.load_sql_config(store) == DEFAULT_FORMAT_CONFIG
    assert format_settings.load_xml_config(store) == DEFAULT_XML_FORMAT_CONFIG


def test_round_trip_of_every_settable_value(store):
    config = FormatConfig(
        indent_unit="  ",
        keyword_case=KeywordCase.UPPER,
        clause_rules={
            "join": ClauseRule(break_before=False),
            "where": ClauseRule(indent_levels=2),
        },
        join_phrase_break=False,
    )
    xml_config = XmlFormatConfig(indent_unit="    ")

    format_settings.save_configs(config, xml_config, store)

    assert format_settings.load_sql_config(store) == config.sanitized()
    assert format_settings.load_xml_config(store) == xml_config


def test_a_tab_indent_survives_the_round_trip(store):
    format_settings.save_configs(
        FormatConfig(indent_unit="\t"), DEFAULT_XML_FORMAT_CONFIG, store
    )
    assert format_settings.load_sql_config(store).indent_unit == "\t"


def test_the_stored_grid_stays_sparse(store):
    # Saving a grid where one keyword differs must not write the other 17: the
    # sparse shape is what lets a clause starter be ADDED to the engine later
    # without migrating anybody's settings.
    format_settings.save_configs(
        FormatConfig(clause_rules={"on": ClauseRule(break_before=False)}),
        DEFAULT_XML_FORMAT_CONFIG,
        store,
    )
    store.beginGroup("autoformatter/clause")
    try:
        assert store.childGroups() == ["on"]
    finally:
        store.endGroup()


def test_resetting_a_rule_removes_it_from_the_file(store):
    format_settings.save_configs(
        FormatConfig(clause_rules={"on": ClauseRule(break_before=False)}),
        DEFAULT_XML_FORMAT_CONFIG,
        store,
    )
    format_settings.save_configs(DEFAULT_FORMAT_CONFIG, DEFAULT_XML_FORMAT_CONFIG, store)
    assert format_settings.load_sql_config(store).clause_rules == {}
    store.beginGroup("autoformatter/clause")
    try:
        assert store.childGroups() == []
    finally:
        store.endGroup()


def test_a_hand_edited_file_with_junk_loads_the_defaults_and_never_raises(store):
    # §18.4 B, consequence 2: unknown keys and out-of-range values are dropped or
    # clamped SILENTLY, because nothing can be lost -- the dialog re-derives the
    # whole config in ten seconds.
    store.setValue("autoformatter/keywordCase", "MiXeD")
    store.setValue("autoformatter/indentWidth", "not a number")
    store.setValue("autoformatter/xmlIndentWidth", 999)
    store.setValue("autoformatter/joinPhraseBreak", "maybe")
    store.setValue("autoformatter/clause/mumble/break", False)
    store.setValue("autoformatter/clause/where/indent", 99)

    config = format_settings.load_sql_config(store)

    assert config.keyword_case is KeywordCase.AS_IS
    assert config.indent_unit == DEFAULT_FORMAT_CONFIG.indent_unit
    assert "mumble" not in config.clause_rules  # not a clause starter: dropped
    assert config.rule_for("where").indent_levels == 4  # clamped to the maximum
    assert format_settings.load_xml_config(store) == DEFAULT_XML_FORMAT_CONFIG


def test_out_of_range_indent_widths_fall_back_rather_than_producing_no_indent(store):
    store.setValue("autoformatter/indentWidth", 0)
    assert format_settings.load_sql_config(store).indent_unit == (
        DEFAULT_FORMAT_CONFIG.indent_unit
    )
    store.setValue("autoformatter/indentWidth", 99)
    assert format_settings.load_sql_config(store).indent_unit == (
        DEFAULT_FORMAT_CONFIG.indent_unit
    )


def test_use_settings_is_the_injection_seam(injected):
    format_settings.save_configs(
        FormatConfig(keyword_case=KeywordCase.LOWER), DEFAULT_XML_FORMAT_CONFIG
    )
    assert format_settings.current_sql_config().keyword_case is KeywordCase.LOWER
    format_settings.use_settings(None)
    # Released: the module is back on the app's (per-test isolated) default store.
    assert format_settings.settings() is not injected


def test_current_configs_read_the_store_at_call_time(injected):
    assert format_settings.current_sql_config() == DEFAULT_FORMAT_CONFIG
    format_settings.save_configs(
        FormatConfig(indent_unit="  "), XmlFormatConfig(indent_unit="    ")
    )
    # No notification plumbing: the next gesture simply sees the new values.
    assert format_settings.current_sql_config().indent_unit == "  "
    assert format_settings.current_xml_config().indent_unit == "    "


def test_the_group_name_is_the_documented_one():
    # Beside `lightTheme` / `toolbarIds` / `shortcutOverrides` in the same ini.
    assert format_settings.AUTOFORMAT_SETTINGS_KEY == "autoformatter"


def test_the_default_store_is_the_apps_own(qtbot):
    # Same IniFormat/UserScope/"MDS"/"PGTP Editor" quadruple MainWindow uses, so
    # a `QSettings.setPath` redirection (conftest, or a packaged install) applies
    # to the formatter config too.
    expected = QSettings(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, "MDS", "PGTP Editor"
    ).fileName()
    assert format_settings.default_settings().fileName() == expected
