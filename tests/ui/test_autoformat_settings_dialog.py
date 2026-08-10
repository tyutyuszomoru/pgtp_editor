"""The "Autoformatter settings…" dialog (spec §18.4 part D).

Two things carry the weight here: the dialog is **shown non-modally** (no test
ever meets a live `exec`), and **every control is bounded** -- there is no
free-text rule entry, which is how §18.4's bounded config space is enforced at
the UI as well as in the loader.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialogButtonBox, QLineEdit, QSpinBox

from pgtp_editor.sql import DEFAULT_FORMAT_CONFIG, FormatConfig
from pgtp_editor.sql.format_config import (
    CLAUSE_STARTERS,
    MAX_CLAUSE_INDENT_LEVELS,
    MAX_INDENT_WIDTH,
    MIN_INDENT_WIDTH,
    ClauseRule,
    KeywordCase,
)
from pgtp_editor.ui import format_settings
from pgtp_editor.ui.autoformat_settings_dialog import (
    MENU_LABEL,
    AutoformatSettingsDialog,
    open_autoformat_settings,
)
from pgtp_editor.xmlfmt import DEFAULT_XML_FORMAT_CONFIG, XmlFormatConfig


@pytest.fixture
def store(tmp_path):
    return QSettings(str(tmp_path / "autoformat.ini"), QSettings.Format.IniFormat)


def _dialog(qtbot, store):
    dialog = AutoformatSettingsDialog(settings=store)
    qtbot.addWidget(dialog)
    return dialog


def test_it_opens_on_the_stored_config(qtbot, store):
    format_settings.save_configs(
        FormatConfig(
            indent_unit="  ",
            keyword_case=KeywordCase.UPPER,
            clause_rules={"join": ClauseRule(break_before=False, indent_levels=2)},
            join_phrase_break=False,
        ),
        XmlFormatConfig(indent_unit="    "),
        store,
    )

    dialog = _dialog(qtbot, store)

    config = dialog.sql_config()
    assert config.indent_unit == "  "
    assert config.keyword_case is KeywordCase.UPPER
    assert config.rule_for("join") == ClauseRule(break_before=False, indent_levels=2)
    assert config.join_phrase_break is False
    assert dialog.xml_config() == XmlFormatConfig(indent_unit="    ")


def test_an_empty_store_shows_the_shipped_defaults(qtbot, store):
    dialog = _dialog(qtbot, store)
    assert dialog.sql_config() == DEFAULT_FORMAT_CONFIG
    assert dialog.xml_config() == DEFAULT_XML_FORMAT_CONFIG


def test_ok_saves_and_the_next_load_sees_it(qtbot, store):
    dialog = _dialog(qtbot, store)
    dialog.set_keyword_case(KeywordCase.LOWER)
    dialog.set_clause_rule("where", break_before=False, indent_levels=3)

    dialog._buttons.button(QDialogButtonBox.StandardButton.Ok).click()

    saved = format_settings.load_sql_config(store)
    assert saved.keyword_case is KeywordCase.LOWER
    assert saved.rule_for("where") == ClauseRule(break_before=False, indent_levels=3)
    assert dialog.isVisible() is False


def test_cancel_writes_nothing(qtbot, store):
    dialog = _dialog(qtbot, store)
    dialog.set_keyword_case(KeywordCase.UPPER)

    dialog._buttons.button(QDialogButtonBox.StandardButton.Cancel).click()

    assert format_settings.load_sql_config(store) == DEFAULT_FORMAT_CONFIG


def test_restore_defaults_goes_back_to_as_is_and_the_shipped_grid(qtbot, store):
    dialog = _dialog(qtbot, store)
    dialog.set_keyword_case(KeywordCase.UPPER)
    dialog.set_clause_rule("from", break_before=False, indent_levels=4)

    dialog._buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).click()

    assert dialog.sql_config() == DEFAULT_FORMAT_CONFIG
    assert dialog.xml_config() == DEFAULT_XML_FORMAT_CONFIG


def test_the_config_it_reports_is_sparse(qtbot, store):
    dialog = _dialog(qtbot, store)
    dialog.set_clause_rule("on", break_before=False, indent_levels=0)
    assert set(dialog.sql_config().clause_rules) == {"on"}


def test_every_clause_starter_has_a_row(qtbot, store):
    dialog = _dialog(qtbot, store)
    assert set(dialog._clause_breaks) == set(CLAUSE_STARTERS)
    assert set(dialog._clause_indents) == set(CLAUSE_STARTERS)


def test_every_control_is_bounded_and_none_is_free_text(qtbot, store):
    dialog = _dialog(qtbot, store)
    # No free-text field anywhere: a rule the engine could not prove idempotent
    # must not even be EXPRESSIBLE (§18.4 part D). The only `QLineEdit`s in the
    # tree are the ones QSpinBox builds for itself, and those are bounded by
    # their spin box's range.
    for edit in dialog.findChildren(QLineEdit):
        assert isinstance(edit.parent(), QSpinBox), edit
    for spin in dialog.findChildren(QSpinBox):
        assert spin.minimum() >= 0 and spin.maximum() <= max(
            MAX_INDENT_WIDTH, MAX_CLAUSE_INDENT_LEVELS
        )
    assert dialog._indent_width.minimum() == MIN_INDENT_WIDTH
    assert dialog._indent_width.maximum() == MAX_INDENT_WIDTH
    for spin in dialog._clause_indents.values():
        assert (spin.minimum(), spin.maximum()) == (0, MAX_CLAUSE_INDENT_LEVELS)
    assert dialog._xml_indent_width.maximum() == MAX_INDENT_WIDTH
    # And the two choices that are not numbers are closed combos.
    assert isinstance(dialog._case_combo, QComboBox)
    assert isinstance(dialog._indent_kind, QComboBox)
    assert isinstance(dialog._join_phrase_break, QCheckBox)


def test_as_is_is_the_first_casing_choice(qtbot, store):
    dialog = _dialog(qtbot, store)
    # (Item data is the enum's string value -- Qt round-trips a str Enum through
    # QVariant as a plain string.)
    assert KeywordCase.parse(dialog._case_combo.itemData(0)) is KeywordCase.AS_IS


def test_choosing_tab_disables_the_width_spin_box(qtbot, store):
    dialog = _dialog(qtbot, store)
    dialog._indent_kind.setCurrentIndex(1)  # Tab
    assert dialog._indent_width.isEnabled() is False
    assert dialog.sql_config().indent_unit == "\t"
    dialog._indent_kind.setCurrentIndex(0)  # Spaces
    assert dialog._indent_width.isEnabled() is True


def test_the_public_entry_point_shows_it_non_modally(qtbot, store):
    dialog = open_autoformat_settings(None, settings=store)
    qtbot.addWidget(dialog)
    assert isinstance(dialog, AutoformatSettingsDialog)
    assert dialog.isVisible() is True
    assert dialog.isModal() is False


def test_the_entry_point_defaults_to_the_apps_own_store(qtbot):
    # No `settings=`: the module's default store (redirected per test by
    # conftest's `_isolated_qsettings`), so the menu wiring can be one line.
    dialog = open_autoformat_settings(None)
    qtbot.addWidget(dialog)
    assert dialog.sql_config() == DEFAULT_FORMAT_CONFIG
    dialog.close()


def test_the_menu_label_is_the_specified_one():
    assert MENU_LABEL == "Autoformatter settings…"
